from __future__ import annotations

import logging

import discord

from hmwz import events, sqlite_db
from hmwz.modules.registration import RegistrationModuleBase
from hmwz.modules.registry import register

from . import repositories

_logger = logging.getLogger(__name__)


@register
class QsRegistrationModule(RegistrationModuleBase):
    """Guild-spezifisches QS-Registrierungsmodul."""

    module_key = "qs"

    def __init__(self, guild: discord.Guild, client: discord.Client) -> None:
        super().__init__(guild, client)
        database = self.database
        if not isinstance(database, sqlite_db.Database):
            raise RuntimeError("QS registration module requires a database.")
        self._database = database
        self.registration = repositories.QSRegistrationSettingsRepository(database)
        self.roles = repositories.QSRegistrationRoleRepository(database)
        self.registrations = repositories.QSMemberRegistrationRepository(database)
        self.list = repositories.QSRegistrationMessageRepository(database)
        self.purge_channels = repositories.QSPurgeChannelRepository(database)
        self._initialize_registration(
            registration=self.registration,
            roles=self.roles,
            registrations=self.registrations,
            lists=self.list,
        )
        self._schema_ready = False

    async def _ensure_schema(self) -> bool:
        if self._schema_ready:
            return True
        try:
            for repository in (
                self.registration,
                self.registration_event_channel,
                self.registration_snapshot_messages,
                self.roles,
                self.registrations,
                self.list,
                self.purge_channels,
            ):
                if not await self._database.execute(repository.table):
                    _logger.error(
                        "%s Failed to create QS table %s.",
                        self.guild.name,
                        repository.table_name,
                    )
                    return False
            self._schema_ready = True
            return True
        except Exception:
            _logger.exception(
                "%s (%s) - Failed to ensure QS schema.",
                self.guild.name,
                self.guild.id,
            )
            return False

    async def migrate_schema(self) -> bool:
        """Migrate QS registration tables to the current schema."""
        if not await self._ensure_schema():
            return False
        synced = True
        for repository in (self.registration, self.roles, self.registrations):
            if not await repository.migrate_schema():
                _logger.error(
                    "%s Failed to sync names in QS table %s.",
                    self.guild.name,
                    repository.table_name,
                )
                synced = False
        return synced

    async def sync(self, startup: bool = False) -> bool:
        if not await self.migrate_schema():
            return False
        if startup:
            await self.export_startup_snapshots()
            _logger.debug(
                "%s (%s) - QS module startup sync done.", self.guild.name, self.guild.id
            )
        return True

    async def ensure(self) -> bool:
        return await self.compose_registration_overview()

    async def on_guild_join(self, guild: discord.Guild) -> bool:
        return guild.id == self.guild.id and await self.sync(startup=True)

    async def on_guild_update(
        self, before: discord.Guild, after: discord.Guild
    ) -> bool:
        return after.id == self.guild.id

    async def on_guild_remove(self, guild: discord.Guild) -> bool:
        if guild.id != self.guild.id:
            return False
        await self.registration.remove(guild=guild)
        await self.roles.remove(guild=guild)
        await self.list.remove(guild=guild)
        await self.registrations.remove(guild=guild)
        await self.purge_channels.remove(guild=guild)
        return True

    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel) -> bool:
        return channel.guild.id == self.guild.id

    async def on_guild_channel_update(
        self,
        before: discord.abc.GuildChannel,
        after: discord.abc.GuildChannel,
    ) -> bool:
        return before.guild.id == self.guild.id

    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> bool:
        if channel.guild.id != self.guild.id:
            return False
        await self.purge_channels.remove(guild=self.guild, channel_id=channel.id)
        return True

    async def on_guild_role_update(
        self, before: discord.Role, after: discord.Role
    ) -> bool:
        return before.guild.id == self.guild.id

    async def on_guild_role_delete(self, role: discord.Role) -> bool:
        if role.guild.id != self.guild.id:
            return False
        await self.roles.remove(guild=self.guild, role=role.id)
        await self.registrations.remove(guild=self.guild, role=role.id)
        return True

    async def on_raw_member_remove(self, payload: events.RawMemberRemoveEvent) -> bool:
        if payload.guild_id != self.guild.id:
            return False
        await self.registrations.remove(guild=self.guild, member=payload.user.id)
        return True

    async def on_raw_message_delete(
        self, payload: events.RawMessageDeleteEvent
    ) -> bool:
        if payload.guild_id != self.guild.id or payload.message_id is None:
            return False
        if payload.channel_id is not None:
            self._overview_for(payload.channel_id).forget_message(payload.message_id)
        registration = await self.registration.get(
            guild=self.guild, channel_id=payload.channel_id
        )
        if registration and registration.message == payload.message_id:
            if registration.channel is None:
                return False
            await self.registration.clear_message(
                guild=self.guild, channel_id=registration.channel
            )
            await self.compose_registration_overview(
                force=True, channel_id=registration.channel
            )
        await self.list.remove(
            guild=self.guild,
            message=payload.message_id,
            channel=payload.channel_id,
        )
        return True

    async def on_raw_bulk_message_delete(
        self, payload: events.RawBulkMessageDeleteEvent
    ) -> bool:
        if payload.guild_id != self.guild.id:
            return False
        registration = await self.registration.get(
            guild=self.guild, channel_id=payload.channel_id
        )
        needs_recompose = bool(
            registration and registration.message in payload.message_ids
        )
        overview = self._overview_for(payload.channel_id)
        for message_id in payload.message_ids:
            overview.forget_message(message_id)
            await self.list.remove(
                guild=self.guild, message=message_id, channel=payload.channel_id
            )
        if needs_recompose:
            await self.registration.clear_message(
                guild=self.guild, channel_id=payload.channel_id
            )
            await self.compose_registration_overview(
                force=True, channel_id=payload.channel_id
            )
        return True
