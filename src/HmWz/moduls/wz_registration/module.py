from __future__ import annotations

import logging

import discord
import hmEvents
import hmUtils
import sqlLiteDB
from i18n import t

from ..basic_module import BasicModule
from ..registry import register
from . import recordsets
from .overview import RegistrationOverview

_logger = logging.getLogger(__name__)


@register
class WzRegistrationModule(BasicModule):
    """Guild-spezifisches WZ-Registrierungsmodul."""

    def __init__(self, guild: discord.Guild, client: discord.Client) -> None:
        """Initialisiert Recordsets und Laufzeitzustand fuer die Guild."""
        super().__init__(guild, client)
        if self.database is None and not isinstance(self.database, sqlLiteDB.Database):
            raise RuntimeError("WZ registration module requires a database.")
        self.configuration : recordsets.Configuration = recordsets.Configuration(self.database)
        self.roles : recordsets.WzRoles = recordsets.WzRoles(self.database)
        self.registration : recordsets.WzRegistration = recordsets.WzRegistration(self.database)
        self.registrations : recordsets.WzRegistrations = recordsets.WzRegistrations(self.database)
        self.list : recordsets.WzList = recordsets.WzList(self.database)
        self.purge_channels : recordsets.WzPurgeChannels = recordsets.WzPurgeChannels(self.database)
        self._schema_ready : bool = False
        self._overview : RegistrationOverview = RegistrationOverview(
            guild=self.guild,
            client=client,
            registration=self.registration,
            roles=self.roles,
            registrations=self.registrations,
            lists=self.list,
            registration_handler=self._handle_registration,
        )

    async def _handle_registration(
        self, interaction: discord.Interaction, role: discord.Role
    ) -> None:
        """Verarbeitet An- und Abmeldung eines Users fuer eine Rolle."""
        guild = interaction.guild
        member = interaction.user
        if guild is None or not isinstance(member, discord.Member):
            return

        await interaction.response.defer(ephemeral=True)

        records = await self.registrations.get(guild=guild, member=member.id)
        current = records[0] if records else None

        if current and current.role == role.id:
            removed = await self.registrations.remove(guild=guild, member=member.id)
            if not removed:
                await interaction.followup.send(
                    t(interaction, "wz.overview.registration.error_registration"),
                    ephemeral=True,
                )
                _logger.error(
                    "Failed to remove registration for member %s (%s) in guild %s",
                    member.name,
                    member.id,
                    guild.id,
                )
                return
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
                "Removed registration for member %s (%s) in guild %s",
                member.name,
                member.id,
                guild.id,
            )
            await self.compose_registration_overview(force=True)
            return

        is_update = current is not None and current.role != role.id
        if current and current.role != role.id and current.role is not None:
            old_role = await hmUtils.fetch_role(guild, current.role)
            if old_role is not None:
                await member.remove_roles(old_role, reason="WZ registration update")

        added = await self.registrations.add(
            guild=guild,
            member=member.id,
            role=role.id,
        )
        if not added:
            await interaction.followup.send(
                t(interaction, "wz.overview.registration.error_registration"),
                ephemeral=True,
            )
            return
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
            "Added registration for member %s (%s) in guild %s",
            member.name,
            member.id,
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
            await self.database.execute(self.configuration.table)
            await self.database.execute(self.roles.table)
            await self.database.execute(self.registration.table)
            await self.database.execute(self.registrations.table)
            await self.database.execute(self.list.table)
            await self.database.execute(self.purge_channels.table)
            self._schema_ready = True
            _logger.info("%s (%s) - WZ module schema ready.", self.guild.name, self.guild.id)
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
        if not await self._ensure_schema():
            return False
        if startup:
            _logger.debug(
                "%s (%s) - WZ module startup sync done.",
                self.guild.name,
                self.guild.id,
            )
        return True

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
        return True

    async def on_guild_channel_create(
        self, channel: discord.abc.GuildChannel
    ) -> bool:
        """Bestaetigt Relevanz des Events fuer diese Guild."""
        return channel.guild.id == self.guild.id

    async def on_guild_channel_update(
        self,
        before: discord.abc.GuildChannel,
        after: discord.abc.GuildChannel,
    ) -> bool:
        """Bestaetigt Relevanz des Events fuer diese Guild."""
        return before.guild.id == self.guild.id

    async def on_guild_channel_delete(
        self, channel: discord.abc.GuildChannel
    ) -> bool:
        """Bestaetigt Relevanz des Events fuer diese Guild."""
        return channel.guild.id == self.guild.id

    async def on_guild_role_update(
        self, before: discord.Role, after: discord.Role
    ) -> bool:
        """Bestaetigt Relevanz des Events fuer diese Guild."""
        return before.guild.id == self.guild.id

    async def on_guild_role_delete(self, role: discord.Role) -> bool:
        """Bereinigt geloeschte Rollen aus Rollen- und Registrierungsrecordset."""
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

        registrations : list[Registration] = await self.registrations.get(
            guild=self.guild,
            member=after.id,
        )
        current_registration = registrations[0] if registrations else None
        changed = False

        if current_registration and current_registration.role is not None:
            current_role_id = current_registration.role
            if current_role_id in removed_registration_roles:
                changed = await self.registrations.remove(
                    guild=self.guild,
                    member=after.id,
                )
            elif added_registration_roles and current_role_id not in after_role_ids:
                changed = await self.registrations.add(
                    guild=self.guild,
                    member=after.id,
                    role=min(added_registration_roles),
                )
        elif added_registration_roles:
            changed = await self.registrations.add(
                guild=self.guild,
                member=after.id,
                role=min(added_registration_roles),
            )

        if changed:
            await self.compose_registration_overview(force=True)
        return True

    async def on_raw_member_remove(
        self, payload: hmEvents.RawMemberRemoveEvent
    ) -> bool:
        """Entfernt Registrierungen fuer verlassende Mitglieder."""
        if payload.guild_id != self.guild.id:
            return False
        await self.registrations.remove(
            guild=self.guild,
            member=payload.user.id,
        )
        return True

    async def on_raw_message_delete(
        self, payload: hmEvents.RawMessageDeleteEvent
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
        self, payload: hmEvents.RawBulkMessageDeleteEvent
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
