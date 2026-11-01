"""Compose registration overviews and member-list messages."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

import discord

from hmwz.configuration import registration_defaults
from hmwz.i18n import t
from hmwz.modules.overview import Overview, OverviewButton, OverviewModule
from hmwz.utils.loaders import fetch_channel

from . import models
from .list_overview import RegistrationListOverview

if TYPE_CHECKING:
    from . import repositories

_logger = logging.getLogger(__name__)
RegistrationHandler = Callable[[discord.Interaction, discord.Role], Awaitable[None]]


class RegistrationOverview:
    """Builds and synchronizes the registration overview and member list."""

    def __init__(
        self,
        guild: discord.Guild,
        client: discord.Client,
        registration: repositories.RegistrationSettingsRepository,
        roles: repositories.RegistrationRoleRepository,
        registrations: repositories.MemberRegistrationRepository,
        registration_handler: RegistrationHandler,
        overview_module: OverviewModule,
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
        self.registration_handler = registration_handler
        self.overview_module = overview_module
        self.overview_id = f"{module_key}-{channel_id}"
        self._compose_task: asyncio.Task[bool] | None = None
        self._compose_requested = False
        self._compose_force = asyncio.Event()
        self._last_compose_at = 0.0
        self._compose_min_interval_seconds = 1.5
        self._list_overview = RegistrationListOverview(
            guild=guild,
            registrations=registrations,
            overview_module=overview_module,
            overview_id=self.overview_id,
            module_key=module_key,
            max_players=max_players,
        )

    def forget_message(self, message_id: int) -> None:
        """Drop cached message state after Discord reports its deletion."""
        self._list_overview.forget_message(message_id)

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
                show_lock_emojis=True,
                registration_roles=registration_roles,
            )

        return models.Configuration(
            guild_id=self.guild.id,
            channel_id=registration_record.channel,
            message_id=registration_record.message,
            title=registration_record.title,
            description=registration_record.description,
            show_lock_emojis=registration_record.show_lock_emojis,
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

    def _build_buttons(
        self, roles: tuple[models.RegistrationRole, ...]
    ) -> tuple[OverviewButton, ...]:
        buttons: list[OverviewButton] = []
        for row, role_data in enumerate(roles):
            role = self.guild.get_role(role_data.role_id)
            if role is None:
                continue

            async def handle(
                interaction: discord.Interaction, role: discord.Role = role
            ) -> None:
                """Forward the selected role to the registration handler."""
                await self.registration_handler(interaction, role)

            button_id = str(role.id)
            self.overview_module.register_handler(
                overview_id=self.overview_id,
                button_id=button_id,
                handler=handle,
            )
            buttons.append(
                OverviewButton(
                    button_id=button_id,
                    label=role.name,
                    style=discord.ButtonStyle.primary,
                    row=min(row, 4),
                )
            )
        return tuple(buttons)

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
        if not await self.overview_module.sync():
            _logger.error(
                "%s (%s) - Failed to initialize the overview service.",
                self.guild.name,
                self.guild.id,
            )
            return False
        buttons = self._build_buttons(configuration.registration_roles)
        existing_overview = await self.overview_module.overviews.get(
            guild=self.guild,
            overview_id=self.overview_id,
        )
        if existing_overview is None and configuration.message_id is not None:
            legacy_overview = Overview(
                guild_id=self.guild.id,
                overview_id=self.overview_id,
                channel_id=channel.id,
                message_id=configuration.message_id,
                title=title,
                description=description,
                buttons=buttons,
            )
            if not await self.overview_module.overviews.save(legacy_overview):
                _logger.error(
                    "%s (%s) - Failed to adopt registration overview message %s.",
                    self.guild.name,
                    self.guild.id,
                    configuration.message_id,
                )
                return False
        if not await self.overview_module.publish(
            overview_id=self.overview_id,
            channel_id=channel.id,
            title=title,
            description=description,
            buttons=buttons,
        ):
            _logger.warning(
                "%s (%s) - Failed to publish registration overview in #%s (%s).",
                self.guild.name,
                self.guild.id,
                channel.name,
                channel.id,
            )
            return False
        overview = await self.overview_module.overviews.get(
            guild=self.guild,
            overview_id=self.overview_id,
        )
        if overview is None or overview.message_id is None:
            _logger.error(
                "%s (%s) - Registration overview %s was published without a message ID.",
                self.guild.name,
                self.guild.id,
                self.overview_id,
            )
            return False
        registrations = await self._load_registrations(configuration)
        if not await self.registration.upsert(
            guild=self.guild,
            channel_id=channel.id,
            message_id=overview.message_id,
            title=title,
            description=description,
        ):
            _logger.error(
                "%s (%s) - Failed to save registration overview message %s.",
                self.guild.name,
                self.guild.id,
                overview.message_id,
            )
            return False
        list_embeds = await self._list_overview.create_embeds(
            registrations,
            get_color=lambda: self.overview_module.client_color,
            get_client_avatar=lambda: self.overview_module.client_avatar,
            show_lock_emojis=configuration.show_lock_emojis,
        )
        if not await self._list_overview.sync_messages(channel, list_embeds):
            _logger.error(
                "%s (%s) - Failed to synchronize registration list overviews "
                "in #%s (%s).",
                self.guild.name,
                self.guild.id,
                channel.name,
                channel.id,
            )
            return False
        _logger.info(
            "%s (%s) - Synchronized registration overview message %s in %s(%s).",
            self.guild.name,
            self.guild.id,
            overview.message_id,
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
        """Synchronize this channel, coalescing requests into a shared task.

        Args:
            force: Bypass the minimum interval, but still coalesce pending updates.

        Returns:
            Whether every synchronization in the shared task succeeded.
        """
        self._compose_requested = True
        if force:
            self._compose_force.set()
        if self._compose_task is None or self._compose_task.done():
            self._compose_task = asyncio.create_task(self._run_compose())
            self._compose_task.add_done_callback(self._compose_done)
        return await asyncio.shield(self._compose_task)

    def _compose_done(self, task: asyncio.Task[bool]) -> None:
        if not task.cancelled() and (error := task.exception()) is not None:
            _logger.error(
                "%s (%s) - Registration overview synchronization failed.",
                self.guild.name,
                self.guild.id,
                exc_info=(type(error), error, error.__traceback__),
            )

    async def _run_compose(self) -> bool:
        status = True
        while self._compose_requested:
            delay = self._compose_min_interval_seconds - (
                time.monotonic() - self._last_compose_at
            )
            if delay > 0 and not self._compose_force.is_set():
                try:
                    await asyncio.wait_for(self._compose_force.wait(), timeout=delay)
                except TimeoutError:
                    pass
            self._compose_requested = False
            self._compose_force.clear()
            result = await self._compose()
            status = result and status
            if result:
                self._last_compose_at = time.monotonic()
        return status
