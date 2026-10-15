from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable

import discord
import hmEmojis
import hmUtils
from configuration import config
from hmModels.botembed import BotEmbed
from i18n import t

from . import models, recordsets

_logger = logging.getLogger(__name__)
RegistrationHandler = Callable[[discord.Interaction, discord.Role], Awaitable[None]]


class RegistrationButton(discord.ui.Button):
    """A button that delegates its registration action to the module."""

    def __init__(
        self,
        role: discord.Role,
        handler: RegistrationHandler,
        *,
        row: int,
    ) -> None:
        super().__init__(label=role.name, style=discord.ButtonStyle.primary, row=row)
        self.role = role
        self._handler = handler

    async def callback(self, interaction: discord.Interaction) -> None:
        await self._handler(interaction, self.role)


class RegistrationOverview:
    """Builds and synchronizes the registration overview and member list."""

    def __init__(
        self,
        guild: discord.Guild,
        client: discord.Client,
        registration: recordsets.WzRegistration,
        roles: recordsets.WzRoles,
        registrations: recordsets.WzRegistrations,
        lists: recordsets.WzList,
        registration_handler: RegistrationHandler,
    ) -> None:
        self.guild = guild
        self.client = client
        self.registration = registration
        self.roles = roles
        self.registrations = registrations
        self.lists = lists
        self.registration_handler = registration_handler
        self._compose_lock = asyncio.Lock()
        self._last_compose_at = 0.0
        self._compose_min_interval_seconds = 1.5
        self._overview_message: discord.Message | None = None
        self._overview_signature: tuple[object, ...] | None = None
        self._list_messages: dict[int, discord.Message] = {}

    def forget_message(self, message_id: int) -> None:
        """Drop cached message state after Discord reports its deletion."""
        self._list_messages.pop(message_id, None)
        if self._overview_message is not None and self._overview_message.id == message_id:
            self._overview_message = None
            self._overview_signature = None

    @property
    def _client_color(self) -> discord.Color:
        member = (
            self.guild.get_member(self.client.user.id)
            if self.client.user is not None
            else None
        )
        if member and member.roles:
            return max(member.roles, key=lambda role: role.position).color
        return discord.Color.blurple()

    @property
    def _client_avatar(self) -> discord.Asset | None:
        guild_icon = self.guild.icon
        if isinstance(guild_icon, discord.Asset):
            return guild_icon
        user_avatar = self.client.user.avatar if self.client.user is not None else None
        return user_avatar if isinstance(user_avatar, discord.Asset) else None

    def _translate(self, key: str, **kwargs: object) -> str:
        return t(self.guild, key, **kwargs)

    async def _load_configuration(self) -> models.Configuration:
        registration_record = await self.registration.get(guild=self.guild)
        role_records = await self.roles.get(guild=self.guild)
        registration_roles = tuple(
            models.RegistrationRole(
                role_id=role.role,
                score=role.score,
                permanent=role.permanent,
            )
            for role in (role_records or [])
            if role.role is not None
        )

        if registration_record is None:
            return models.Configuration(
                guild_id=self.guild.id,
                channel_id=None,
                message_id=None,
                title=None,
                description=None,
                registration_roles=registration_roles,
            )

        return models.Configuration(
            guild_id=self.guild.id,
            channel_id=registration_record.channel,
            message_id=registration_record.message,
            title=registration_record.title,
            description=registration_record.description,
            registration_roles=registration_roles,
        )

    async def _load_registrations(
        self, configuration: models.Configuration
    ) -> models.Registration:
        role_map = {
            role.role_id: role for role in configuration.registration_roles
        }
        records = await self.registrations.get(guild=self.guild)
        members: list[models.RegistrationMember] = []

        for record in records or []:
            if record.member is None or record.role is None:
                continue
            role = role_map.get(record.role)
            if role is None:
                role = models.RegistrationRole(
                    role_id=record.role,
                    score=0,
                    permanent=False,
                )
            members.append(
                models.RegistrationMember(
                    member_id=record.member,
                    role=role,
                    timestamp=record.timestamp,
                )
            )

        return models.Registration(guild=self.guild, registrations=members)

    def _build_view(
        self, roles: tuple[models.RegistrationRole, ...]
    ) -> discord.ui.View:
        view = discord.ui.View(timeout=None)
        row = 0
        for role_data in roles:
            role = self.guild.get_role(role_data.role_id)
            if role is None:
                continue
            view.add_item(
                RegistrationButton(
                    role,
                    self.registration_handler,
                    row=min(row, 4),
                )
            )
            row += 1
        return view

    async def _load_list_messages(
        self, channel: discord.TextChannel
    ) -> list[discord.Message]:
        records = await self.lists.get(guild=self.guild)
        if not records:
            return []

        messages: list[discord.Message] = []
        stale_ids: list[int] = []
        for record in records:
            message = self._list_messages.get(record.message)
            if message is not None and message.channel.id != channel.id:
                message = None
            if message is None:
                message = await hmUtils.fetch_message(channel, record.message)
            if message is None:
                stale_ids.append(record.message)
            else:
                self._list_messages[record.message] = message
                messages.append(message)

        for stale_id in stale_ids:
            self._list_messages.pop(stale_id, None)
            await self.lists.remove(guild=self.guild, message=stale_id)
        return messages

    async def _create_list_embeds(
        self, registrations: models.Registration
    ) -> list[discord.Embed]:
        if not registrations.registrations:
            return []

        entries: list[tuple[str, bool, str]] = []
        for registration in registrations.registrations:
            role = self.guild.get_role(registration.role.role_id)
            member = await hmUtils.fetch_member(self.guild, registration.member_id)
            if role is not None and member is not None:
                entries.append(
                    (role.name, registration.role.permanent, member.display_name)
                )

        if not entries:
            return []

        entries.sort(key=lambda entry: (not entry[1], entry[0].lower(), entry[2].lower()))
        total = len(entries)
        permanent = sum(1 for entry in entries if entry[1])
        non_permanent = total - permanent

        rows: list[str] = []
        last_group = ""
        for index, (role_name, is_permanent, display_name) in enumerate(entries, 1):
            marker = (
                hmEmojis.PERMA_REGISTRATION
                if is_permanent
                else hmEmojis.NORMAL_REGISTRATION
            )
            group = f"{role_name} {marker}"
            if group != last_group:
                rows.append(f"**{group}**")
                last_group = group
            rows.append(f"{index}. {display_name}")

        def make_embed(page: int, content: str) -> discord.Embed:
            return BotEmbed(
                title=self._translate(
                    "wz.overview.list.title",
                    page=page,
                    total=total,
                    perma_emoji=hmEmojis.PERMA_REGISTRATION,
                    permanent_count=permanent,
                    normal_emoji=hmEmojis.NORMAL_REGISTRATION,
                    non_permanent_count=non_permanent,
                ),
                description=content,
                color=self._client_color,
                client_avatar=self._client_avatar,
            )

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

    async def _sync_list_messages(
        self,
        channel: discord.TextChannel,
        embeds: list[discord.Embed],
    ) -> None:
        existing_messages = await self._load_list_messages(channel)

        for index in range(max(len(existing_messages), len(embeds))):
            if index < len(embeds) and index < len(existing_messages):
                message = existing_messages[index]
                embed = embeds[index]
                if not message.embeds or message.embeds[0].to_dict() != embed.to_dict():
                    message = await message.edit(embed=embed)
                    self._list_messages[message.id] = message
                    await self.lists.add(
                        guild=self.guild,
                        channel=channel.id,
                        message=message.id,
                        title=embed.title or "",
                        text=embed.description or "",
                    )
            elif index < len(embeds):
                embed = embeds[index]
                message = await channel.send(embed=embed)
                self._list_messages[message.id] = message
                await self.lists.add(
                    guild=self.guild,
                    channel=channel.id,
                    message=message.id,
                    title=embed.title or "",
                    text=embed.description or "",
                )
            else:
                message = existing_messages[index]
                try:
                    await message.delete()
                finally:
                    self._list_messages.pop(message.id, None)
                    await self.lists.remove(guild=self.guild, message=message.id)

    async def _compose(self) -> bool:
        configuration = await self._load_configuration()
        if not configuration.has_channel:
            _logger.debug(
                "%s (%s) - No registration channel configured.",
                self.guild.name,
                self.guild.id,
            )
            return False
        if not configuration.has_registration_roles:
            _logger.debug(
                "%s (%s) - No registration roles configured.",
                self.guild.name,
                self.guild.id,
            )
            return False

        channel_id = configuration.channel_id
        if channel_id is None:
            return False
        channel = await hmUtils.fetch_channel(self.guild, channel_id)
        if channel is None:
            _logger.warning(
                "%s (%s) - Registration channel not found: %s",
                self.guild.name,
                self.guild.id,
                channel_id,
            )
            return False

        default_title = self._translate("wz.overview.default_title")
        default_description = self._translate("wz.overview.default_description")
        if isinstance(config, dict):
            registration_config = config.get("wz_registration")
            if isinstance(registration_config, dict):
                default_title = str(
                    registration_config.get("default_title", default_title)
                )
                default_description = str(
                    registration_config.get("default_description", default_description)
                )

        title = configuration.title or default_title
        description = configuration.description or default_description
        embed = BotEmbed(
            title=title,
            description=description,
            color=self._client_color,
            client_avatar=self._client_avatar,
        )
        view = self._build_view(configuration.registration_roles)
        overview_signature = (
            title,
            description,
            tuple(
                (item.role.id, item.role.name, item.row)
                for item in view.children
                if isinstance(item, RegistrationButton)
            ),
        )

        message = self._overview_message
        if (
            message is None
            or message.id != configuration.message_id
            or message.channel.id != channel.id
        ):
            message = None
        if message is None and configuration.has_message and configuration.message_id is not None:
            message = await hmUtils.fetch_message(channel, configuration.message_id)
        registrations = await self._load_registrations(configuration)

        if message is None:
            message = await channel.send(embed=embed, view=view)
            self._overview_message = message
            self._overview_signature = overview_signature
            action = "Created"
        elif self._overview_signature != overview_signature:
            message = await message.edit(embed=embed, view=view)
            self._overview_message = message
            self._overview_signature = overview_signature
            action = "Updated"
        else:
            action = "Reused"

        await self.registration.upsert(
            guild=self.guild,
            channel_id=channel.id,
            message_id=message.id,
            title=title,
            description=description,
        )
        list_embeds = await self._create_list_embeds(registrations)
        await self._sync_list_messages(channel, list_embeds)
        _logger.info(
            "%s (%s) - %s registration overview message %s in %s(%s).",
            self.guild.name,
            self.guild.id,
            action,
            message.id,
            channel.name,
            channel.id,
        )
        return True

    async def compose(self, force: bool = False) -> bool:
        now = time.monotonic()
        if (
            not force
            and now - self._last_compose_at < self._compose_min_interval_seconds
        ):
            _logger.debug(
                "%s (%s) - Debounced registration overview compose request.",
                self.guild.name,
                self.guild.id,
            )
            return True

        async with self._compose_lock:
            now = time.monotonic()
            if (
                not force
                and now - self._last_compose_at < self._compose_min_interval_seconds
            ):
                _logger.debug(
                    "%s (%s) - Debounced registration overview compose request (locked).",
                    self.guild.name,
                    self.guild.id,
                )
                return True

            result = await self._compose()
            if result:
                self._last_compose_at = time.monotonic()
            return result
