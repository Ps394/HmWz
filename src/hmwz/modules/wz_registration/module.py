from __future__ import annotations

import logging

import discord

from hmwz import events, sqlite_db, utils
from hmwz.hm_client.repositories import DiscordEntityRepository
from hmwz.i18n import t

from ..basic_module import BasicModule
from ..registry import register
from . import repositories
from .overview import RegistrationOverview

_logger = logging.getLogger(__name__)


@register
class WzRegistrationModule(BasicModule):
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
        self.game_accounts: repositories.MemberGameAccountRepository = (
            repositories.MemberGameAccountRepository(self._database)
        )
        self.list: repositories.RegistrationMessageRepository = (
            repositories.RegistrationMessageRepository(self._database)
        )
        self.purge_channels: repositories.PurgeChannelRepository = (
            repositories.PurgeChannelRepository(self._database)
        )
        self.entities = DiscordEntityRepository(self._database)
        self._schema_ready: bool = False
        self._overview: RegistrationOverview = RegistrationOverview(
            guild=self.guild,
            client=client,
            registration=self.registration,
            roles=self.roles,
            registrations=self.registrations,
            lists=self.list,
            registration_handler=self._handle_registration,
        )

    async def _handle_registration(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
        *,
        response_deferred: bool = False,
    ) -> None:
        """Verarbeitet An- und Abmeldung eines Users fuer eine Rolle."""
        guild = interaction.guild
        member = interaction.user
        if guild is None or not isinstance(member, discord.Member):
            return

        if not response_deferred:
            await interaction.response.defer(ephemeral=True)
        if not await self.entities.add_member(guild=guild, member=member):
            _logger.error(
                "%s Failed to save member name %s / %s (%s).",
                sqlite_db.Base.log_prefix(guild),
                member.name,
                member.display_name,
                member.id,
            )
            await interaction.followup.send(
                t(interaction, "wz.overview.registration.error_registration"),
                ephemeral=True,
            )
            return

        records = await self.registrations.get(
            guild=guild, member=member.id, account=""
        )
        current = records[0] if records else None

        if current and current.role == role.id:
            removed = await self.registrations.remove(
                guild=guild, member=member.id, account=""
            )
            if not removed:
                await interaction.followup.send(
                    t(interaction, "wz.overview.registration.error_registration"),
                    ephemeral=True,
                )
                _logger.error(
                    "Failed to remove registration for member %s / %s (%s) in guild %s (%s)",
                    member.name,
                    member.display_name,
                    member.id,
                    guild.name,
                    guild.id,
                )
                return
            remaining = await self.registrations.get(guild=guild, member=member.id)
            if role.id not in {
                record.role for record in remaining or () if record.role is not None
            }:
                await member.remove_roles(role, reason="WZ deregistration")
            await interaction.followup.send(
                t(
                    interaction,
                    "wz.overview.registration.remove_registration",
                    role_name=role.name,
                ),
                ephemeral=True,
            )
            _logger.info(
                "Removed registration for member %s / %s (%s) in guild %s (%s)",
                member.name,
                member.display_name,
                member.id,
                guild.name,
                guild.id,
            )
            await self.compose_registration_overview(force=True)
            return

        is_update = current is not None and current.role != role.id
        added = await self.registrations.add(
            guild=guild,
            member=member.id,
            role=role.id,
            account="",
        )
        if not added:
            await interaction.followup.send(
                t(interaction, "wz.overview.registration.error_registration"),
                ephemeral=True,
            )
            return
        if current and current.role is not None and current.role != role.id:
            remaining = await self.registrations.get(guild=guild, member=member.id)
            old_role_is_used = any(
                record.role == current.role for record in remaining or ()
            )
            old_role = await utils.fetch_role(guild, current.role)
            if not old_role_is_used and old_role is not None:
                await member.remove_roles(old_role, reason="WZ registration update")
        await member.add_roles(role, reason="WZ registration")
        key = (
            "wz.overview.registration.update_registration"
            if is_update
            else "wz.overview.registration.new_registration"
        )
        await interaction.followup.send(
            t(interaction, key, role_name=role.name),
            ephemeral=True,
        )
        _logger.info(
            "Added registration for member %s / %s (%s) in guild %s (%s)",
            member.name,
            member.display_name,
            member.id,
            guild.name,
            guild.id,
        )
        await self.compose_registration_overview(force=True)

    async def compose_registration_overview(self, force: bool = False) -> bool:
        """Aktualisiert die Registrierungsuebersicht und die zugehoerige Liste."""
        return await self._overview.compose(force=force)

    async def _ensure_schema(self) -> bool:
        """Stellt sicher, dass alle benoetigten Tabellen existieren."""
        if self._schema_ready:
            return True
        try:
            for repository in (
                self.configuration,
                self.roles,
                self.registration,
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
            self.roles,
            self.registration,
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

    async def on_member_update(
        self, before: discord.Member, after: discord.Member
    ) -> bool:
        """Synchronisiert Registrierungen bei manuellen Rollen-Aenderungen."""
        if before.guild.id != self.guild.id:
            return False
        if not await self.sync_names():
            return False

        before_role_ids = {role.id for role in before.roles}
        after_role_ids = {role.id for role in after.roles}
        added_role_ids = after_role_ids - before_role_ids
        removed_role_ids = before_role_ids - after_role_ids
        if not added_role_ids and not removed_role_ids:
            return True

        configured_roles = await self.roles.get(guild=self.guild)
        if not configured_roles:
            return True

        registration_role_ids = {role.role for role in configured_roles}
        added_registration_roles = added_role_ids & registration_role_ids
        removed_registration_roles = removed_role_ids & registration_role_ids
        if not added_registration_roles and not removed_registration_roles:
            return True

        registrations: repositories.MemberRegistrationRepository.Records = (
            await self.registrations.get(
                guild=self.guild,
                member=after.id,
                account="",
            )
        )
        all_member_registrations = await self.registrations.get(
            guild=self.guild,
            member=after.id,
        )
        current_registration = registrations[0] if registrations else None
        changed = False
        tracked_roles = {
            record.role
            for record in all_member_registrations or ()
            if record.role is not None
        }
        for removed_role_id in removed_registration_roles & tracked_roles:
            role_removed = await self.registrations.remove_member_role(
                guild=self.guild,
                member=after.id,
                role=removed_role_id,
            )
            changed = role_removed or changed

        if current_registration and current_registration.role is not None:
            current_role_id = current_registration.role
            if (
                current_role_id not in removed_registration_roles
                and added_registration_roles
                and current_role_id not in after_role_ids
            ):
                changed = (
                    await self.registrations.add(
                        guild=self.guild,
                        member=after.id,
                        role=min(added_registration_roles),
                        account="",
                    )
                    or changed
                )
        elif added_registration_roles and not any(
            record.role in added_registration_roles
            for record in all_member_registrations or ()
        ):
            changed = await self.registrations.add(
                guild=self.guild,
                member=after.id,
                role=min(added_registration_roles),
                account="",
            )

        if changed:
            await self.compose_registration_overview(force=True)
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
            self._overview.forget_message(payload.message_id)
            registration = await self.registration.get(guild=self.guild)
            if registration and registration.message == payload.message_id:
                await self.registration.upsert(guild=self.guild, message_id=None)
                await self.compose_registration_overview(force=True)
            await self.list.remove(guild=self.guild, message=payload.message_id)
        return True

    async def on_raw_bulk_message_delete(
        self, payload: events.RawBulkMessageDeleteEvent
    ) -> bool:
        """Behandelt Massenloeschungen wie mehrere einzelne Nachrichtenloeschungen."""
        if payload.guild_id != self.guild.id:
            return False

        registration = await self.registration.get(guild=self.guild)
        needs_recompose = bool(
            registration and registration.message in payload.message_ids
        )
        for message_id in payload.message_ids:
            self._overview.forget_message(message_id)
        if needs_recompose:
            await self.registration.upsert(guild=self.guild, message_id=None)

        for message_id in payload.message_ids:
            await self.list.remove(guild=self.guild, message=message_id)

        if needs_recompose:
            await self.compose_registration_overview(force=True)
        return True
