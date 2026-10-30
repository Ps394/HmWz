from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

import discord

from hmwz.configuration import registration_defaults
from hmwz.i18n import t
from hmwz.ui.embeds import create_embed
from hmwz.ui.messages import edit_message, send_message
from hmwz.utils.loaders import fetch_channel, fetch_message

from . import models
from .list_overview import RegistrationListOverview

if TYPE_CHECKING:
    from . import repositories

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
        registration: repositories.RegistrationSettingsRepository,
        roles: repositories.RegistrationRoleRepository,
        registrations: repositories.MemberRegistrationRepository,
        lists: repositories.RegistrationMessageRepository,
        registration_handler: RegistrationHandler,
        channel_id: int,
        module_key: str = "registration",
        max_players: int | None = None,
    ) -> None:
        self.guild = guild
        self.channel_id = channel_id
        self.module_key = module_key
        self.max_players = max_players
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
        self._list_overview = RegistrationListOverview(
            guild=guild,
            registrations=registrations,
            lists=lists,
            module_key=module_key,
            max_players=max_players,
        )

    def forget_message(self, message_id: int) -> None:
        """Drop cached message state after Discord reports its deletion."""
        self._list_overview.forget_message(message_id)
        if (
            self._overview_message is not None
            and self._overview_message.id == message_id
        ):
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
        _, suffix = key.split(".", maxsplit=1)
        return t(self.guild, f"{self.module_key}.{suffix}", **kwargs)

    async def _load_configuration(self) -> models.Configuration:
        registration_record = await self.registration.get(
            guild=self.guild, channel_id=self.channel_id
        )
        role_records = await self.roles.get(
            guild=self.guild, channel_id=self.channel_id
        )
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
        role_map = {role.role_id: role for role in configuration.registration_roles}
        records = await self.registrations.get(
            guild=self.guild, channel_id=self.channel_id
        )
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
                    account=record.account,
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
        channel = await fetch_channel(self.guild, channel_id)
        if channel is None:
            _logger.warning(
                "%s (%s) - Registration channel not found: %s",
                self.guild.name,
                self.guild.id,
                channel_id,
            )
            return False

        missing_permissions = self._missing_send_permissions(channel)
        if missing_permissions:
            _logger.warning(
                "%s (%s) - Cannot compose registration overview in #%s (%s); "
                "bot is missing channel permissions: %s.",
                self.guild.name,
                self.guild.id,
                channel.name,
                channel.id,
                ", ".join(missing_permissions),
            )
            return False

        default_title = self._translate(f"{self.module_key}.overview.default_title")
        default_description = self._translate(
            f"{self.module_key}.overview.default_description"
        )
        registration_config = registration_defaults(self.module_key)
        default_title = str(registration_config.get("default_title", default_title))
        default_description = str(
            registration_config.get("default_description", default_description)
        )

        title = configuration.title or default_title
        description = configuration.description or default_description
        embed = create_embed(
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
        if (
            message is None
            and configuration.has_message
            and configuration.message_id is not None
        ):
            message = await fetch_message(channel, configuration.message_id)
        registrations = await self._load_registrations(configuration)

        if message is None:
            message = await send_message(channel, embed=embed, view=view)
            if message is None:
                _logger.warning(
                    "%s (%s) - Discord could not send the registration overview "
                    "in #%s (%s); verify the bot's channel permissions.",
                    self.guild.name,
                    self.guild.id,
                    channel.name,
                    channel.id,
                )
                return False
            self._overview_message = message
            self._overview_signature = overview_signature
            action = "Created"
        elif self._overview_signature != overview_signature:
            updated_message = await edit_message(message, embed=embed, view=view)
            if updated_message is None:
                return False
            message = updated_message
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
        list_embeds = await self._list_overview.create_embeds(
            registrations,
            get_color=lambda: self._client_color,
            get_client_avatar=lambda: self._client_avatar,
        )
        await self._list_overview.sync_messages(channel, list_embeds)
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

    def _missing_send_permissions(
        self, channel: discord.TextChannel
    ) -> tuple[str, ...]:
        """Return required channel permissions missing from the bot member."""
        bot_member = self.guild.me
        if bot_member is None:
            return ()
        permissions = channel.permissions_for(bot_member)
        required = ("view_channel", "send_messages", "embed_links")
        return tuple(name for name in required if not getattr(permissions, name))

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
