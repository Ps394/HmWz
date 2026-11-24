"""Compatibility adapter for publishing registration messages through the shared service."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Sequence

import discord

from hmwz.modules.managed_messages import (
    ManagedMessagesModule,
    migrate_overviews,
)
from hmwz.modules.overview import OverviewButton
from hmwz.ui.embeds import create_embed


class RegistrationManagedMessagesAdapter:
    """Keep registration content in Registration and publication in the shared service."""

    def __init__(
        self,
        *,
        guild: discord.Guild,
        managed_messages: ManagedMessagesModule,
    ) -> None:
        self.guild = guild
        self.managed_messages = managed_messages
        self._button_handlers: dict[
            str,
            Callable[[discord.Interaction], Awaitable[None]],
        ] = {}

    def register_handler(self, *, managed_id: str, button_id: str, handler) -> None:
        self._button_handlers[f"{managed_id}:{button_id}"] = handler

    def _view_for(
        self, managed_id: str, buttons: Sequence[OverviewButton]
    ) -> discord.ui.View | None:
        if not buttons:
            return None
        view = discord.ui.View(timeout=None)
        for button in buttons:
            callback = self._button_handlers.get(f"{managed_id}:{button.button_id}")
            if callback is None:
                continue
            handler = callback

            class RegistrationButton(discord.ui.Button):
                async def callback(
                    inner_self,
                    interaction: discord.Interaction,
                ) -> None:
                    await handler(interaction)

            view.add_item(
                RegistrationButton(
                    label=button.label,
                    style=button.style,
                    custom_id=f"registration:{managed_id}:{button.button_id}",
                    row=button.row,
                )
            )
        return view

    @staticmethod
    def main_id(channel_id: int) -> str:
        return f"registration-{channel_id}"

    @staticmethod
    def list_id(channel_id: int, page: int) -> str:
        return f"registration-{channel_id}-list-{page}"

    @staticmethod
    def channel_id(managed_id: str) -> int | None:
        match = re.fullmatch(r"registration-(\d+)(?:-list-\d+)?", managed_id)
        if match is None:
            return None
        return int(match.group(1))

    async def delete_channel(self, channel_id: int) -> bool:
        """Delete the main and all paginated Registration managed messages."""
        managed_ids = [
            record.managed_id
            for record in await self.managed_messages.messages.get_all(guild=self.guild)
            if self.channel_id(record.managed_id) == channel_id
        ]
        success = True
        for managed_id in managed_ids:
            success = (
                await self.managed_messages.delete(managed_id=managed_id) and success
            )
        return success

    async def adopt_legacy_messages(self, *, channel_id: int, page_count: int) -> bool:
        """Adopt matching legacy overview rows without deleting legacy data."""
        ids = [self.main_id(channel_id)]
        ids.extend(self.list_id(channel_id, page) for page in range(1, page_count + 1))
        return await migrate_overviews(
            self.managed_messages,
            self.guild,
            overview_ids=tuple(ids),
        )

    async def publish_main(
        self,
        *,
        channel_id: int,
        title: str,
        description: str,
        buttons: Sequence[OverviewButton],
    ) -> bool:
        managed_id = self.main_id(channel_id)
        await self.adopt_legacy_messages(channel_id=channel_id, page_count=0)
        embed = create_embed(title=title, description=description)
        self.managed_messages.register_managed_owner(
            owner_id="registration",
            managed_id=managed_id,
        )
        self.managed_messages.register_view_factory(
            managed_id=managed_id,
            factory=lambda _managed_id: self._view_for(managed_id, buttons),
        )
        return await self.managed_messages.publish(
            managed_id=managed_id,
            channel_id=channel_id,
            embeds=(embed,),
            view=self._view_for(managed_id, buttons),
        )

    async def publish_pages(
        self,
        *,
        channel_id: int,
        embeds: Sequence[discord.Embed],
    ) -> bool:
        managed_ids = {
            self.list_id(channel_id, page) for page in range(1, len(embeds) + 1)
        }
        await self.adopt_legacy_messages(
            channel_id=channel_id,
            page_count=len(embeds),
        )
        for page, embed in enumerate(embeds, start=1):
            managed_id = self.list_id(channel_id, page)
            self.managed_messages.register_managed_owner(
                owner_id="registration",
                managed_id=managed_id,
            )
            if not await self.managed_messages.publish(
                managed_id=managed_id,
                channel_id=channel_id,
                embeds=(embed,),
            ):
                return False

        prefix = f"{self.main_id(channel_id)}-list-"
        for record in await self.managed_messages.messages.get_all(guild=self.guild):
            if (
                record.managed_id.startswith(prefix)
                and record.managed_id not in managed_ids
            ):
                if not await self.managed_messages.delete(managed_id=record.managed_id):
                    return False
        return True

    async def get_message_id(self, managed_id: str) -> int | None:
        record = await self.managed_messages.messages.get(
            guild=self.guild,
            managed_id=managed_id,
        )
        return record.message_id if record is not None else None
