from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

import discord

from hmwz import emojis, utils
from hmwz.i18n import t
from hmwz.ui.embeds import create_embed
from hmwz.ui.messages import delete_message, edit_message, send_message

from . import models

if TYPE_CHECKING:
    from . import repositories


@dataclass(frozen=True, slots=True)
class _RegistrationListEntry:
    role_name: str
    permanent: bool
    display_name: str


class RegistrationListOverview:
    """Build and synchronize the paginated list of registered members."""

    def __init__(
        self,
        guild: discord.Guild,
        registrations: repositories.MemberRegistrationRepository,
        lists: repositories.RegistrationMessageRepository,
        module_key: str,
        max_players: int | None,
    ) -> None:
        self.guild = guild
        self.registrations = registrations
        self.lists = lists
        self.module_key = module_key
        self.max_players = max_players
        self._messages: dict[int, discord.Message] = {}

    def forget_message(self, message_id: int) -> None:
        """Drop cached message state after Discord reports its deletion."""
        self._messages.pop(message_id, None)

    async def create_embeds(
        self,
        registrations: models.Registration,
        *,
        get_color: Callable[[], discord.Color],
        get_client_avatar: Callable[[], discord.Asset | None],
    ) -> list[discord.Embed]:
        if not registrations.registrations:
            return []

        entries = await self._load_entries(registrations)
        if not entries:
            return []

        entries.sort(
            key=lambda entry: (
                not entry.permanent,
                entry.role_name.lower(),
                entry.display_name.lower(),
            )
        )
        rows = self._build_rows(entries)
        permanent_count = sum(entry.permanent for entry in entries)
        non_permanent_count = len(entries) - permanent_count

        def make_embed(page: int, content: str) -> discord.Embed:
            return self._create_embed(
                page=page,
                content=content,
                total=len(entries),
                permanent_count=permanent_count,
                non_permanent_count=non_permanent_count,
                get_color=get_color,
                get_client_avatar=get_client_avatar,
            )

        return self._paginate_rows(rows, make_embed)

    async def _load_entries(
        self,
        registrations: models.Registration,
    ) -> list[_RegistrationListEntry]:
        entries: list[_RegistrationListEntry] = []
        for registration in registrations.registrations:
            role = self.guild.get_role(registration.role.role_id)
            member = await utils.fetch_member(self.guild, registration.member_id)
            if role is not None and member is not None:
                entries.append(
                    _RegistrationListEntry(
                        role_name=role.name,
                        permanent=registration.role.permanent,
                        display_name=(
                            f"{registration.account} ({member.display_name})"
                            if registration.account
                            else member.display_name
                        ),
                    )
                )
        return entries

    @staticmethod
    def _build_rows(entries: list[_RegistrationListEntry]) -> list[str]:
        rows: list[str] = []
        last_group = ""
        for index, entry in enumerate(entries, 1):
            marker = (
                emojis.PERMA_REGISTRATION
                if entry.permanent
                else emojis.NORMAL_REGISTRATION
            )
            group = f"{entry.role_name} {marker}"
            if group != last_group:
                rows.append(f"**{group}**")
                last_group = group
            rows.append(f"{index}. {entry.display_name}")
        return rows

    def _create_embed(
        self,
        *,
        page: int,
        content: str,
        total: int,
        permanent_count: int,
        non_permanent_count: int,
        get_color: Callable[[], discord.Color],
        get_client_avatar: Callable[[], discord.Asset | None],
    ) -> discord.Embed:
        return create_embed(
            title=t(
                self.guild,
                f"{self.module_key}.overview.list.title",
                page=page,
                total=total,
                max_players=self.max_players or total,
                perma_emoji=emojis.PERMA_REGISTRATION,
                permanent_count=permanent_count,
                normal_emoji=emojis.NORMAL_REGISTRATION,
                non_permanent_count=non_permanent_count,
            ),
            description=content,
            color=get_color(),
            client_avatar=get_client_avatar(),
        )

    @staticmethod
    def _paginate_rows(
        rows: list[str],
        make_embed: Callable[[int, str], discord.Embed],
    ) -> list[discord.Embed]:
        embeds: list[discord.Embed] = []
        chunk: list[str] = []
        chunk_chars = 0
        page = 1
        for row in rows:
            line = f"{row}\n"
            if chunk and chunk_chars + len(line) > 3800:
                embeds.append(make_embed(page, "".join(chunk)))
                page += 1
                chunk = []
                chunk_chars = 0
            chunk.append(line)
            chunk_chars += len(line)

        if chunk:
            embeds.append(make_embed(page, "".join(chunk)))
        return embeds

    async def sync_messages(
        self,
        channel: discord.TextChannel,
        embeds: list[discord.Embed],
    ) -> None:
        existing_messages = await self._load_messages(channel)

        for index in range(max(len(existing_messages), len(embeds))):
            has_message = index < len(existing_messages)
            has_embed = index < len(embeds)
            if has_message and has_embed:
                await self._update_message(
                    channel,
                    existing_messages[index],
                    embeds[index],
                )
            elif has_embed:
                await self._create_message(channel, embeds[index])
            else:
                await self._delete_message(existing_messages[index])

    async def _update_message(
        self,
        channel: discord.TextChannel,
        message: discord.Message,
        embed: discord.Embed,
    ) -> None:
        if message.embeds and message.embeds[0].to_dict() == embed.to_dict():
            return
        updated_message = await edit_message(message, embed=embed)
        if updated_message is None:
            return
        await self._save_message(channel, updated_message, embed)

    async def _create_message(
        self,
        channel: discord.TextChannel,
        embed: discord.Embed,
    ) -> None:
        message = await send_message(channel, embed=embed)
        if message is None:
            return
        await self._save_message(channel, message, embed)

    async def _save_message(
        self,
        channel: discord.TextChannel,
        message: discord.Message,
        embed: discord.Embed,
    ) -> None:
        self._messages[message.id] = message
        await self.lists.add(
            guild=self.guild,
            channel=channel.id,
            message=message.id,
            title=embed.title or "",
            text=embed.description or "",
        )

    async def _delete_message(self, message: discord.Message) -> None:
        await delete_message(message)
        self._messages.pop(message.id, None)
        await self.lists.remove(guild=self.guild, message=message.id)

    async def _load_messages(
        self, channel: discord.TextChannel
    ) -> list[discord.Message]:
        records = await self.lists.get(guild=self.guild, channel=channel.id)
        if not records:
            return []

        messages: list[discord.Message] = []
        stale_ids: list[int] = []
        for record in records:
            message = self._messages.get(record.message)
            if message is not None and message.channel.id != channel.id:
                message = None
            if message is None:
                message = await utils.fetch_message(channel, record.message)
            if message is None:
                stale_ids.append(record.message)
            else:
                self._messages[record.message] = message
                messages.append(message)

        for stale_id in stale_ids:
            self._messages.pop(stale_id, None)
            await self.lists.remove(
                guild=self.guild, message=stale_id, channel=channel.id
            )
        return messages
