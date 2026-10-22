from __future__ import annotations

import logging

import discord

from hmwz import events, sqlite_db
from ...registry import register
from ..account.repositories import MemberGameAccountRepository
from hmwz.modules.registrations import RegistrationModuleBase
from . import repositories

_logger = logging.getLogger(__name__)


@register
class WzRegistrationModule(RegistrationModuleBase):
    """Guild-spezifisches WZ-Registrierungsmodul."""

    def __init__(self, guild: discord.Guild, client: discord.Client) -> None:
        """Initialisiert Repositories und Laufzeitzustand fuer die Guild."""
        super().__init__(guild, client)
        database = self.database
        if not isinstance(database, sqlite_db.Database):
            raise RuntimeError("WZ registration module requires a database.")
        self._database: sqlite_db.Database = database
        self.configuration: repositories.WzConfigurationRepository = (
            repositories.WzConfigurationRepository(self._database)
        )
        self.roles: repositories.RegistrationRoleRepository = (
            repositories.RegistrationRoleRepository(self._database)
        )
        self.registration: repositories.RegistrationSettingsRepository = (
            repositories.RegistrationSettingsRepository(self._database)
        )
        self.registrations: repositories.MemberRegistrationRepository = (
            repositories.MemberRegistrationRepository(self._database)
        )
        self.game_accounts = MemberGameAccountRepository(self._database)
        self.list: repositories.RegistrationMessageRepository = (
            repositories.RegistrationMessageRepository(self._database)
        )
        self._initialize_registration(
            registration=self.registration,
            roles=self.roles,
            registrations=self.registrations,
            lists=self.list,
        )
        self.purge_channels: repositories.PurgeChannelRepository = (
            repositories.PurgeChannelRepository(self._database)
        )
        self._schema_ready: bool = False
        self.module_key = "wz"
        self.max_players = None

    async def _ensure_schema(self) -> bool:
        """Stellt sicher, dass alle benoetigten Tabellen existieren."""
        if self._schema_ready:
            return True
        try:
            for repository in (
                self.configuration,
                self.registration,
                self.roles,
                self.registrations,
                self.game_accounts,
                self.list,
                self.purge_channels,
            ):
                if not await self._database.execute(repository.table):
                    _logger.error(
                        "%s (%s) - Failed to create table %s.",
                        self.guild.name,
                        self.guild.id,
                        repository.table_name,
                    )
                    return False
            self._schema_ready = True
            _logger.info(
                "%s (%s) - WZ module schema ready.", self.guild.name, self.guild.id
            )
            return True
        except Exception:
            _logger.exception(
                "%s (%s) - Failed to ensure WZ schema.",
                self.guild.name,
                self.guild.id,
            )
            return False

    async def sync(self, startup: bool = False) -> bool:
        """Synchronisiert den technischen Modulzustand (Schema)."""
        if not await self.sync_names():
            return False
        if startup:
            _logger.debug(
                "%s (%s) - WZ module startup sync done.",
                self.guild.name,
                self.guild.id,
            )
        return True

    async def sync_names(self) -> bool:
        """Synchronize current Discord names into the WZ tables."""
        if not await self._ensure_schema():
            return False
        synced = True
        for repository in (
            self.registration,
            self.roles,
            self.registrations,
            self.purge_channels,
        ):
            if not await repository.migrate_names():
                _logger.error(
                    "%s (%s) - Failed to sync names in table %s.",
                    self.guild.name,
                    self.guild.id,
                    repository.table_name,
                )
                synced = False
        return synced

    async def ensure(self) -> bool:
        """Stellt sicher, dass die Registrierungsuebersicht sichtbar und aktuell ist."""
        try:
            return await self.compose_registration_overview()
        except Exception:
            _logger.exception(
                "%s (%s) - Failed to compose registration overview.",
                self.guild.name,
                self.guild.id,
            )
            return False

    async def on_guild_join(self, guild: discord.Guild) -> bool:
        """Initialisiert Modulzustand bei Guild-Join."""
        if guild.id != self.guild.id:
            return False
        return await self.sync(startup=True)

    async def on_guild_update(
        self, before: discord.Guild, after: discord.Guild
    ) -> bool:
        """Aktualisiert gespeicherte Guild-Namen nach einer Umbenennung."""
        if after.id != self.guild.id:
            return False
        return await self.sync_names()

    async def on_guild_remove(self, guild: discord.Guild) -> bool:
        """Entfernt guild-bezogene WZ-Daten beim Verlassen der Guild."""
        if guild.id != self.guild.id:
            return False
        await self.configuration.remove(guild=guild)
        await self.registration.remove(guild=guild)
        await self.purge_channels.remove(guild=guild)
        await self.roles.remove(guild=guild)
        await self.list.remove(guild=guild)
        await self.registrations.remove(guild=guild)
        await self.game_accounts.remove_guild(guild=guild)
        return True

    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel) -> bool:
        """Bestaetigt Relevanz des Events fuer diese Guild."""
        if channel.guild.id != self.guild.id:
            return False
        return await self.sync_names()

    async def on_guild_channel_update(
        self,
        before: discord.abc.GuildChannel,
        after: discord.abc.GuildChannel,
    ) -> bool:
        """Bestaetigt Relevanz des Events fuer diese Guild."""
        if before.guild.id != self.guild.id:
            return False
        return await self.sync_names()

    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> bool:
        """Bestaetigt Relevanz des Events fuer diese Guild."""
        return channel.guild.id == self.guild.id

    async def on_guild_role_update(
        self, before: discord.Role, after: discord.Role
    ) -> bool:
        """Bestaetigt Relevanz des Events fuer diese Guild."""
        if before.guild.id != self.guild.id:
            return False
        return await self.sync_names()

    async def on_guild_role_delete(self, role: discord.Role) -> bool:
        """Bereinigt geloeschte Rollen aus Rollen- und Registrierungsdaten."""
        if role.guild.id != self.guild.id:
            return False
        await self.roles.remove(guild=self.guild, role=role.id)
        await self.registrations.remove(guild=self.guild, role=role.id)
        return True

    async def on_raw_member_remove(self, payload: events.RawMemberRemoveEvent) -> bool:
        """Entfernt Registrierungen fuer verlassende Mitglieder."""
        if payload.guild_id != self.guild.id:
            return False
        if not await self.sync_names():
            return False
        await self.registrations.remove(
            guild=self.guild,
            member=payload.user.id,
        )
        await self.game_accounts.remove_member(
            guild=self.guild,
            member=payload.user.id,
        )
        return True

    async def on_raw_message_delete(
        self, payload: events.RawMessageDeleteEvent
    ) -> bool:
        """Bereinigt geloeschte Nachrichtenreferenzen und stellt die Uebersicht wieder her."""
        if payload.guild_id != self.guild.id:
            return False
        if payload.message_id is not None:
            if payload.channel_id is not None:
                self._overview_for(payload.channel_id).forget_message(
                    payload.message_id
                )
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
        """Behandelt Massenloeschungen wie mehrere einzelne Nachrichtenloeschungen."""
        if payload.guild_id != self.guild.id:
            return False

        registration = await self.registration.get(
            guild=self.guild, channel_id=payload.channel_id
        )
        needs_recompose = bool(
            registration and registration.message in payload.message_ids
        )
        for message_id in payload.message_ids:
            self._overview_for(payload.channel_id).forget_message(message_id)
        if needs_recompose:
            await self.registration.clear_message(
                guild=self.guild, channel_id=payload.channel_id
            )

        for message_id in payload.message_ids:
            await self.list.remove(
                guild=self.guild, message=message_id, channel=payload.channel_id
            )

        if needs_recompose:
            await self.compose_registration_overview(
                force=True, channel_id=payload.channel_id
            )
        return True
