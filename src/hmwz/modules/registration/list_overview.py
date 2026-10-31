"""Build and synchronize paginated registration-list overview messages."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

import discord

from hmwz.emojis import emojis
from hmwz.i18n import t
from hmwz.modules.overview import OverviewModule
from hmwz.ui.embeds import create_embed
from hmwz.utils.loaders import fetch_member

from . import models

if TYPE_CHECKING:
    from .repositories import MemberRegistrationRepository


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
        registrations: MemberRegistrationRepository,
        overview_module: OverviewModule,
        overview_id: str,
        module_key: str,
        max_players: int | None,
    ) -> None:
        self.guild = guild
        self.registrations = registrations
        self.overview_module = overview_module
        self.overview_id = overview_id
        self.module_key = module_key
        self.max_players = max_players

    def forget_message(self, message_id: int) -> None:
        """Keep a compatibility hook while OverviewModule owns message state.

        Args:
            message_id: Message identifier; retained for backward compatibility.
        """
        del message_id

    async def create_embeds(
        self,
        registrations: models.Registration,
        *,
        get_color: Callable[[], discord.Color],
        get_client_avatar: Callable[[], discord.Asset | None],
    ) -> list[discord.Embed]:
        """Create paginated embeds for the current registrations.

        Args:
            registrations: Registration records to display.
            get_color: Callback that returns the embed color.
            get_client_avatar: Callback that returns the embed avatar.

        Returns:
            The registration pages, or an empty list when no entries can be shown.
        """
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
            """Create one page with totals shared across the full registration list."""
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
            member = await fetch_member(self.guild, registration.member_id)
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

    def _build_rows(self, entries: list[_RegistrationListEntry]) -> list[str]:
        rows: list[str] = []
        last_group = ""
        for index, entry in enumerate(entries, 1):
            marker = (
                emojis.get("perma_registration", self.guild)
                if entry.permanent
                else emojis.get("normal_registration", self.guild)
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
                perma_emoji=emojis.get("perma_registration", self.guild),
                permanent_count=permanent_count,
                normal_emoji=emojis.get("normal_registration", self.guild),
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
    ) -> bool:
        """Publish the current pages and remove obsolete page overviews.

        Args:
            channel: Channel that should contain the registration pages.
            embeds: Pages to publish.

        Returns:
            Whether every page was published and every obsolete page removed.
        """
        page_ids: set[str] = set()
        for page, embed in enumerate(embeds, start=1):
            overview_id = f"{self.overview_id}-list-{page}"
            page_ids.add(overview_id)
            if not await self.overview_module.publish(
                overview_id=overview_id,
                channel_id=channel.id,
                title=embed.title or f"{self.module_key} registrations",
                description=embed.description or "",
            ):
                return False

        prefix = f"{self.overview_id}-list-"
        existing_pages = await self.overview_module.overviews.get_all(guild=self.guild)
        for overview in existing_pages:
            if (
                overview.overview_id.startswith(prefix)
                and overview.overview_id not in page_ids
            ):
                if not await self.overview_module.delete(
                    overview_id=overview.overview_id
                ):
                    return False
        return True
