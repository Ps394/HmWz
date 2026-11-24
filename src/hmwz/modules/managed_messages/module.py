"""Guild-scoped infrastructure for synchronized bot-managed Discord messages."""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, cast

import discord

from hmwz import events
from hmwz.modules.module import Module
from hmwz.modules.registry import register
from hmwz.ui.messages import delete_message, edit_message, send_message
from hmwz.utils.loaders import fetch_message

from .models import ManagedMessage, ManagedTargetKind, ManagedThread
from .protocols import (
    ManagedBatchRefreshHandler,
    ManagedChannelDeleteHandler,
    ManagedMessageRefreshHandler,
    ManagedThreadDeleteHandler,
    ManagedViewFactory,
)
from .repositories import ManagedMessageRepository, ManagedThreadRepository

if TYPE_CHECKING:
    from hmwz.client import Client

_logger = logging.getLogger(__name__)
_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


@register
class ManagedMessagesModule(Module):
    """Own persistent Discord message synchronization for guild modules."""

    def __init__(self, guild: discord.Guild, client: Client) -> None:
        super().__init__(guild, client)
        if self.database is None:
            raise RuntimeError("ManagedMessagesModule requires a database.")
        self.messages = ManagedMessageRepository(self.database)
        self.threads = ManagedThreadRepository(self.database)
        self._guild_lock = asyncio.Lock()
        self._channel_locks: dict[int, asyncio.Lock] = {}
        self._view_factories: dict[str, ManagedViewFactory] = {}
        self._refresh_handlers: dict[str, ManagedMessageRefreshHandler] = {}
        self._batch_refresh_handlers: dict[str, ManagedBatchRefreshHandler] = {}
        self._channel_delete_handlers: dict[str, ManagedChannelDeleteHandler] = {}
        self._thread_delete_handlers: dict[str, ManagedThreadDeleteHandler] = {}
        self._views: dict[int, discord.ui.View] = {}
        self._pending_batches: dict[str, tuple[set[str], asyncio.Task[bool]]] = {}
        self._batch_tasks: set[asyncio.Task[bool]] = set()
        self._batch_delay_seconds = 0.25
        self._batch_force: dict[str, asyncio.Event] = {}
        self._managed_owners: dict[str, str] = {}

    async def sync(self, startup: bool = False) -> bool:
        del startup
        return (
            await self.messages.ensure_schema() and await self.threads.ensure_schema()
        )

    async def ensure(self) -> bool:
        records = await self.messages.get_all(guild=self.guild)
        return all(
            await asyncio.gather(
                *(self.restore(record.managed_id) for record in records)
            )
        )

    def register_view_factory(
        self, *, managed_id: str, factory: ManagedViewFactory
    ) -> None:
        self._validate_id(managed_id)
        self._view_factories[managed_id] = factory

    def register_refresh_handler(
        self, *, managed_id: str, handler: ManagedMessageRefreshHandler
    ) -> None:
        self._validate_id(managed_id)
        self._refresh_handlers[managed_id] = handler

    def register_batch_refresh_handler(
        self, *, owner_id: str, handler: ManagedBatchRefreshHandler
    ) -> None:
        self._validate_id(owner_id)
        self._batch_refresh_handlers[owner_id] = handler

    def register_channel_delete_handler(
        self, *, owner_id: str, handler: ManagedChannelDeleteHandler
    ) -> None:
        self._validate_id(owner_id)
        self._channel_delete_handlers[owner_id] = handler

    def register_thread_delete_handler(
        self, *, owner_id: str, handler: ManagedThreadDeleteHandler
    ) -> None:
        self._validate_id(owner_id)
        self._thread_delete_handlers[owner_id] = handler

    def register_managed_owner(self, *, owner_id: str, managed_id: str) -> None:
        self._validate_id(owner_id)
        self._validate_id(managed_id)
        self._managed_owners[managed_id] = owner_id

    def unregister(self, *, managed_id: str) -> None:
        self._validate_id(managed_id)
        self._view_factories.pop(managed_id, None)
        self._refresh_handlers.pop(managed_id, None)
        self._batch_refresh_handlers.pop(managed_id, None)
        self._channel_delete_handlers.pop(managed_id, None)
        self._thread_delete_handlers.pop(managed_id, None)

    def queue_refresh(
        self,
        owner_id: str,
        managed_id: str,
        *,
        force: bool = False,
    ) -> asyncio.Task[bool]:
        """Merge updates for one owner into a 250 ms refresh window."""
        self._validate_id(owner_id)
        self._validate_id(managed_id)
        pending = self._pending_batches.get(owner_id)
        if pending is None:
            managed_ids: set[str] = set()
            task = asyncio.create_task(self._flush_refresh(owner_id, managed_ids))
            task.add_done_callback(self._batch_tasks.discard)
            self._batch_tasks.add(task)
            pending = (managed_ids, task)
            self._pending_batches[owner_id] = pending
        pending[0].add(managed_id)
        if force:
            self._batch_force.setdefault(owner_id, asyncio.Event()).set()
        return pending[1]

    async def _flush_refresh(self, owner_id: str, managed_ids: set[str]) -> bool:
        await asyncio.sleep(self._batch_delay_seconds)
        self._pending_batches.pop(owner_id, None)
        force = self._batch_force.pop(owner_id, None)
        if force is not None:
            force.clear()
        handler = self._batch_refresh_handlers.get(owner_id)
        if handler is not None:
            return await handler(frozenset(managed_ids))
        success = True
        for managed_id in managed_ids:
            success = await self.restore(managed_id) and success
        return success

    async def close(self) -> None:
        """Drain pending refresh batches before the guild module shuts down."""
        if not self._pending_batches:
            return
        tasks = tuple(pending[1] for pending in self._pending_batches.values())
        await asyncio.gather(*tasks)

    def channel_lock(self, channel_id: int) -> asyncio.Lock:
        return self._channel_locks.setdefault(channel_id, asyncio.Lock())

    async def publish(
        self,
        *,
        managed_id: str,
        channel_id: int,
        content: str | None = None,
        embeds: Sequence[discord.Embed] = (),
        view: discord.ui.View | None = None,
        allowed_mentions: discord.AllowedMentions | None = None,
        attachments: Sequence[discord.File] = (),
        target_kind: ManagedTargetKind = "channel",
        force: bool = False,
    ) -> bool:
        """Create or update one persistent Discord message under a stable ID."""
        self._validate_id(managed_id)
        if channel_id <= 0:
            raise ValueError("channel_id must be a positive Discord ID.")
        if len(embeds) > 10:
            raise ValueError("A Discord message cannot contain more than 10 embeds.")

        embed_payload = tuple(self._embed_payload(embed) for embed in embeds)
        async with self.channel_lock(channel_id):
            previous = await self.messages.get(guild=self.guild, managed_id=managed_id)
            record = ManagedMessage(
                guild_id=self.guild.id,
                managed_id=managed_id,
                channel_id=channel_id,
                message_id=(
                    previous.message_id
                    if previous is not None and previous.channel_id == channel_id
                    else None
                ),
                content=content,
                embeds=embed_payload,
                target_kind=target_kind,
                attachment_names=tuple(
                    attachment.filename for attachment in attachments
                ),
            )
            if previous is not None:
                if previous.channel_id != channel_id:
                    if not await self._delete_record(previous):
                        return False

            if not await self.messages.save(record):
                return False
            return await self._sync_record(
                record,
                embeds=embeds,
                view=view,
                allowed_mentions=allowed_mentions,
                attachments=attachments,
                force=force,
            )

    async def publish_thread(
        self,
        *,
        managed_id: str,
        channel_id: int,
        thread_id: int,
        content: str | None = None,
        embeds: Sequence[discord.Embed] = (),
        view: discord.ui.View | None = None,
        allowed_mentions: discord.AllowedMentions | None = None,
        attachments: Sequence[discord.File] = (),
        force: bool = False,
    ) -> bool:
        """Publish or update one message in a named Discord thread."""
        del channel_id
        self._validate_id(managed_id)
        previous = await self.threads.get(
            guild=self.guild,
            managed_id=managed_id,
            thread_id=thread_id,
        )
        thread = self.guild.get_thread(thread_id)
        if thread is None:
            try:
                resolved = await self.guild.fetch_channel(thread_id)
            except discord.NotFound:
                return False
            except discord.HTTPException:
                _logger.exception(
                    "%s Failed to resolve managed thread %s.",
                    self.guild.name,
                    thread_id,
                )
                return False
            if not isinstance(resolved, discord.Thread):
                return False
            thread = resolved

        embed_payload = tuple(self._embed_payload(embed) for embed in embeds)
        record = ManagedMessage(
            guild_id=self.guild.id,
            managed_id=managed_id,
            channel_id=thread.parent_id,
            message_id=previous.message_id if previous is not None else None,
            content=content,
            embeds=embed_payload,
            target_kind="thread",
            attachment_names=tuple(attachment.filename for attachment in attachments),
        )
        if not await self.messages.save(record):
            return False

        message = await self._sync_thread_record(
            thread=thread,
            managed_id=managed_id,
            record=record,
            embeds=embeds,
            view=view,
            allowed_mentions=allowed_mentions,
            attachments=attachments,
            force=force,
        )
        if not message:
            return False
        return await self.threads.save(
            ManagedThread(
                guild_id=self.guild.id,
                managed_id=managed_id,
                thread_id=thread_id,
                message_id=message.id,
            )
        )

    async def restore(self, managed_id: str) -> bool:
        """Restore or refresh one managed message by its stable ID."""
        self._validate_id(managed_id)
        handler = self._refresh_handlers.get(managed_id)
        if handler is not None:
            return await handler(managed_id)

        record = await self.messages.get(guild=self.guild, managed_id=managed_id)
        if record is None:
            return True
        channel = await self._resolve_channel(record.channel_id)
        if channel is None:
            return False
        return await self._sync_record(
            record,
            embeds=tuple(
                discord.Embed.from_dict(dict(embed)) for embed in record.embeds
            ),
            view=(
                self._view_factories[managed_id](managed_id)
                if managed_id in self._view_factories
                else None
            ),
        )

    async def delete(self, *, managed_id: str) -> bool:
        self._validate_id(managed_id)
        record = await self.messages.get(guild=self.guild, managed_id=managed_id)
        if record is not None and not await self._delete_record(record):
            return False
        for managed_thread in await self.threads.get_all(
            guild=self.guild, managed_id=managed_id
        ):
            if not await self._delete_thread_message(managed_thread):
                return False
        if not await self.threads.remove_managed(
            guild=self.guild, managed_id=managed_id
        ):
            return False
        if not await self.messages.remove(guild=self.guild, managed_id=managed_id):
            return False
        self.unregister(managed_id=managed_id)
        return True

    async def on_guild_remove(self, guild: discord.Guild) -> bool:
        records = await self.messages.get_all(guild=guild)
        success = True
        for record in records:
            success = await self._delete_record(record) and success
        success = await self.messages.remove_guild(guild=guild) and success
        success = await self.threads.remove_guild(guild=guild) and success
        self._view_factories.clear()
        self._refresh_handlers.clear()
        self._views.clear()
        return success

    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> bool:
        """Remove managed state for one deleted channel and notify registered owners."""
        if channel.guild.id != self.guild.id:
            return True
        success = True
        owners: dict[str, set[str]] = {}
        affected: list[ManagedMessage] = []
        for record in await self.messages.get_all(guild=self.guild):
            if record.channel_id != channel.id:
                continue
            affected.append(record)
            owner_id = self._managed_owners.get(record.managed_id)
            if owner_id is not None:
                owners.setdefault(owner_id, set()).add(record.managed_id)

        for owner_id, managed_ids in owners.items():
            handler = self._channel_delete_handlers.get(owner_id)
            if handler is not None:
                success = await handler(channel.id, managed_ids) and success

        for record in affected:
            success = (
                await self.messages.remove(
                    guild=self.guild, managed_id=record.managed_id
                )
                and success
            )
            self.unregister(managed_id=record.managed_id)
        return success

    async def on_guild_join(self, guild: discord.Guild) -> bool:
        return guild.id == self.guild.id and await self.sync() and await self.ensure()

    async def on_message_create(self, message: discord.Message) -> bool:
        del message
        return True

    async def on_message_update(
        self, before: discord.Message, after: discord.Message
    ) -> bool:
        del before, after
        return True

    async def on_message_delete(self, message: discord.Message) -> bool:
        if message.guild is not None:
            return await self.restore_deleted({message.id})
        return True

    async def on_raw_message_delete(
        self, payload: events.RawMessageDeleteEvent
    ) -> bool:
        return await self.restore_deleted({payload.message_id})

    async def on_raw_thread_delete(self, payload: events.RawThreadDeleteEvent) -> bool:
        """Clear thread-owned message state and invoke the registered owner handler."""
        success = True
        owners: dict[str, set[str]] = {}
        for record in await self.messages.get_all(guild=self.guild):
            managed_threads = await self.threads.get_all(
                guild=self.guild, managed_id=record.managed_id
            )
            if not any(
                managed_thread.thread_id == payload.thread_id
                for managed_thread in managed_threads
            ):
                continue
            owner_id = self._managed_owners.get(record.managed_id)
            if owner_id is not None:
                owners.setdefault(owner_id, set()).add(record.managed_id)
            for managed_thread in managed_threads:
                if managed_thread.thread_id == payload.thread_id:
                    if managed_thread.message_id is not None:
                        self._stop_view(managed_thread.message_id)

            success = (
                await self.threads.remove(
                    guild=self.guild,
                    managed_id=record.managed_id,
                    thread_id=payload.thread_id,
                )
                and success
            )

        for owner_id, managed_ids in owners.items():
            handler = self._thread_delete_handlers.get(owner_id)
            if handler is not None:
                success = await handler(payload.thread_id, managed_ids) and success
        return success

    async def on_raw_bulk_message_delete(
        self, payload: events.RawBulkMessageDeleteEvent
    ) -> bool:
        return await self.restore_deleted(set(payload.message_ids))

    async def restore_deleted(self, message_ids: set[int]) -> bool:
        """Forget deleted managed IDs and run registered refresh handlers."""
        if not message_ids:
            return True
        success = True
        for record in await self.messages.get_all(guild=self.guild):
            if record.message_id not in message_ids:
                continue
            if not await self.messages.set_message(
                guild=self.guild,
                managed_id=record.managed_id,
                message_id=None,
            ):
                success = False
                continue
            self._stop_view(record.message_id)
            handler = self._refresh_handlers.get(record.managed_id)
            if handler is not None:
                success = await handler(record.managed_id) and success
            else:
                restored = await self.restore(record.managed_id)
                success = restored and success
        return success

    async def _sync_record(
        self,
        record: ManagedMessage,
        *,
        embeds: Sequence[discord.Embed],
        view: discord.ui.View | None = None,
        allowed_mentions: discord.AllowedMentions | None = None,
        attachments: Sequence[discord.File] = (),
        force: bool = False,
    ) -> bool:
        async with self._guild_lock:
            channel = await self._resolve_channel(record.channel_id)
            if channel is None:
                return False
            kwargs: dict[str, Any] = {}
            if record.content is not None:
                kwargs["content"] = record.content
            if embeds:
                kwargs["embeds"] = list(embeds)
            if view is not None:
                kwargs["view"] = view
            if allowed_mentions is not None:
                kwargs["allowed_mentions"] = allowed_mentions

            message: discord.Message | None = None
            if record.message_id is not None:
                try:
                    message = await fetch_message(
                        channel, record.message_id, raise_on_error=True
                    )
                except discord.NotFound:
                    if not await self.messages.set_message(
                        guild=self.guild,
                        managed_id=record.managed_id,
                        message_id=None,
                    ):
                        return False
                except discord.HTTPException:
                    _logger.exception(
                        "%s Failed to fetch managed message %s.",
                        self.guild.name,
                        record.managed_id,
                    )
                    return False

            if message is None:
                if attachments:
                    kwargs["files"] = list(attachments)
                message = await send_message(channel, **kwargs)
                if message is None:
                    return False
                if not await self.messages.set_message(
                    guild=self.guild,
                    managed_id=record.managed_id,
                    message_id=message.id,
                ):
                    await delete_message(message)
                    return False
            elif force or not self._message_matches(message, record, view):
                if attachments:
                    kwargs["attachments"] = list(attachments)
                else:
                    kwargs["attachments"] = []
                if await edit_message(message, **kwargs) is None:
                    return False

            if view is not None:
                self._stop_view(message.id)
                self.client.add_view(view, message_id=message.id)
                self._views[message.id] = view
            else:
                self._stop_view(message.id)
            return True

    async def _sync_thread_record(
        self,
        *,
        thread: discord.Thread,
        managed_id: str,
        record: ManagedMessage,
        embeds: Sequence[discord.Embed],
        view: discord.ui.View | None,
        allowed_mentions: discord.AllowedMentions | None,
        attachments: Sequence[discord.File],
        force: bool,
    ) -> discord.Message | None:
        kwargs: dict[str, Any] = {}
        if record.content is not None:
            kwargs["content"] = record.content
        if embeds:
            kwargs["embeds"] = list(embeds)
        if view is not None:
            kwargs["view"] = view
        if allowed_mentions is not None:
            kwargs["allowed_mentions"] = allowed_mentions

        message: discord.Message | None = None
        if record.message_id is not None:
            try:
                message = await fetch_message(
                    thread, record.message_id, raise_on_error=True
                )
            except discord.NotFound:
                record_message_id = None
                managed_threads = await self.threads.get_all(
                    guild=self.guild, managed_id=managed_id
                )
                for managed_thread in managed_threads:
                    if managed_thread.thread_id == thread.id:
                        await self.threads.set_message(
                            guild=self.guild,
                            managed_id=managed_id,
                            thread_id=thread.id,
                            message_id=record_message_id,
                        )
            except discord.HTTPException:
                _logger.exception(
                    "%s Failed to fetch thread message %s.",
                    self.guild.name,
                    record.message_id,
                )
                return None

        if message is None:
            if attachments:
                kwargs["files"] = list(attachments)
            message = await send_message(thread, **kwargs)
            if message is None:
                return None
        elif force or not self._message_matches(message, record, view):
            kwargs["attachments"] = list(attachments) if attachments else []
            if await edit_message(message, **kwargs) is None:
                return None

        if view is not None:
            self._stop_view(message.id)
            self.client.add_view(view, message_id=message.id)
            self._views[message.id] = view
        else:
            self._stop_view(message.id)
        return message

    async def _resolve_channel(
        self, channel_id: int
    ) -> discord.TextChannel | discord.Thread | None:
        channel = self.guild.get_channel_or_thread(channel_id)
        if isinstance(channel, (discord.TextChannel, discord.Thread)):
            return channel
        try:
            channel = await self.guild.fetch_channel(channel_id)
        except discord.NotFound:
            return None
        except discord.HTTPException:
            _logger.exception(
                "%s Failed to resolve managed message channel %s.",
                self.guild.name,
                channel_id,
            )
            return None
        return (
            channel
            if isinstance(channel, (discord.TextChannel, discord.Thread))
            else None
        )

    async def _delete_record(self, record: ManagedMessage) -> bool:
        if record.message_id is None:
            return True
        channel = await self._resolve_channel(record.channel_id)
        if channel is None:
            return True
        try:
            message = await fetch_message(
                channel, record.message_id, raise_on_error=True
            )
        except discord.NotFound:
            return True
        except discord.HTTPException:
            _logger.exception(
                "%s Failed to fetch managed message %s for deletion.",
                self.guild.name,
                record.managed_id,
            )
            return False
        self._stop_view(record.message_id)
        return await delete_message(message)

    async def _delete_thread_message(self, managed_thread: ManagedThread) -> bool:
        if managed_thread.message_id is None:
            return True
        thread = self.guild.get_thread(managed_thread.thread_id)
        if thread is None:
            try:
                channel = await self.guild.fetch_channel(managed_thread.thread_id)
            except discord.NotFound:
                return True
            except discord.HTTPException:
                _logger.exception(
                    "%s Failed to resolve managed thread %s.",
                    self.guild.name,
                    managed_thread.thread_id,
                )
                return False
            if not isinstance(channel, discord.Thread):
                return False
            thread = channel
        try:
            message = await fetch_message(
                thread, managed_thread.message_id, raise_on_error=True
            )
        except discord.NotFound:
            return True
        except discord.HTTPException:
            _logger.exception(
                "%s Failed to fetch managed thread message %s.",
                self.guild.name,
                managed_thread.message_id,
            )
            return False
        self._stop_view(managed_thread.message_id)
        return await delete_message(message)

    def _stop_view(self, message_id: int) -> None:
        view = self._views.pop(message_id, None)
        if view is not None:
            view.stop()

    @staticmethod
    def _embed_payload(embed: discord.Embed) -> dict[str, object]:
        payload = cast(dict[str, object], embed.to_dict())
        payload.pop("timestamp", None)
        return payload

    @staticmethod
    def _component_payload(component: discord.Component) -> dict[str, object]:
        payload = {
            key: value for key, value in component.to_dict().items() if key != "id"
        }
        if isinstance(component, discord.ActionRow):
            payload["components"] = [
                ManagedMessagesModule._component_payload(child)
                for child in component.children
            ]
        return payload

    @classmethod
    def _component_dict_payload(cls, component: dict[str, object]) -> dict[str, object]:
        payload = {key: value for key, value in component.items() if key != "id"}
        children = payload.get("components")
        if isinstance(children, list):
            payload["components"] = [
                cls._component_dict_payload(child)
                for child in children
                if isinstance(child, dict)
            ]
        return payload

    @classmethod
    def _message_matches(
        cls,
        message: discord.Message,
        record: ManagedMessage,
        view: discord.ui.View | None,
    ) -> bool:
        existing_embeds = tuple(cls._embed_payload(embed) for embed in message.embeds)
        if tuple(record.embeds) != existing_embeds:
            return False
        if message.content != (record.content or ""):
            return False
        existing_components = tuple(
            cls._component_payload(component) for component in message.components
        )
        desired_components = (
            tuple(
                cls._component_dict_payload(component)
                for component in view.to_components()
            )
            if view is not None
            else ()
        )
        return existing_components == desired_components

    @staticmethod
    def _validate_id(managed_id: str) -> None:
        if not _ID_PATTERN.fullmatch(managed_id):
            raise ValueError(
                "managed_id must contain only ASCII letters, numbers, "
                "underscores, or hyphens."
            )
