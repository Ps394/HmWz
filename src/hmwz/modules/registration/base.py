from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import discord

from hmwz import sqlite_db, utils
from hmwz.i18n import t
from hmwz.modules.basic_module import BasicModule
from hmwz.modules.snapshots.registration import (
    RegistrationEventType,
    RegistrationSnapshotExporter,
)

from .overview import RegistrationOverview
from .repositories import RegistrationEventChannelRepository

if TYPE_CHECKING:
    from .repositories import (
        MemberRegistrationRepository,
        RegistrationMessageRepository,
        RegistrationRoleRepository,
        RegistrationSettingsRepository,
    )

_logger = logging.getLogger(__name__)


class RegistrationModuleBase(BasicModule):
    """Shared channel-scoped registration behavior for WZ and QS."""

    module_key: str
    max_players: int | None = None

    registration: RegistrationSettingsRepository
    roles: RegistrationRoleRepository
    registrations: MemberRegistrationRepository
    list: RegistrationMessageRepository
    registration_event_channel: RegistrationEventChannelRepository

    def _initialize_registration(
        self,
        *,
        registration: RegistrationSettingsRepository,
        roles: RegistrationRoleRepository,
        registrations: MemberRegistrationRepository,
        lists: RegistrationMessageRepository,
    ) -> None:
        database = self.database
        if database is None:
            raise RuntimeError("Registration module requires a database.")
        self.registration = registration
        self.roles = roles
        self.registrations = registrations
        self.list = lists
        self.registration_event_channel = RegistrationEventChannelRepository(database)
        self._registration_snapshot_exporter = RegistrationSnapshotExporter(
            guild=self.guild,
            module_key=self.module_key,
            event_channel=self.registration_event_channel,
            registration=self.registration,
            registrations=self.registrations,
        )
        self._overviews: dict[int, RegistrationOverview] = {}
        self._registration_locks: dict[int, asyncio.Lock] = {}

    def _overview_for(self, channel_id: int) -> RegistrationOverview:
        overview = self._overviews.get(channel_id)
        if overview is None:
            overview = RegistrationOverview(
                guild=self.guild,
                client=self.client,
                registration=self.registration,
                roles=self.roles,
                registrations=self.registrations,
                lists=self.list,
                registration_handler=self._handle_registration,
                channel_id=channel_id,
                module_key=self.module_key,
                max_players=self.max_players,
            )
            self._overviews[channel_id] = overview
        return overview

    async def _handle_registration(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
        *,
        response_deferred: bool = False,
    ) -> None:
        """Add, change, or remove the invoking member's registration."""
        guild = interaction.guild
        member = interaction.user
        channel_id = interaction.channel_id
        if (
            guild is None
            or not isinstance(member, discord.Member)
            or channel_id is None
        ):
            return

        if not response_deferred:
            await interaction.response.defer(ephemeral=True)

        lock = self._registration_locks.setdefault(channel_id, asyncio.Lock())
        async with lock:
            records = await self.registrations.get(
                guild=guild,
                member=member.id,
                account="",
                channel_id=channel_id,
            )
            current = records[0] if records else None
            if current is not None and current.role == role.id:
                await self._remove_member_registration(
                    interaction, guild, member, role, channel_id
                )
                return

            await self._add_member_registration(
                interaction, guild, member, role, channel_id, current
            )

    async def _remove_member_registration(
        self,
        interaction: discord.Interaction,
        guild: discord.Guild,
        member: discord.Member,
        role: discord.Role,
        channel_id: int,
    ) -> None:
        if not await self.registrations.remove(
            guild=guild,
            member=member.id,
            account="",
            channel_id=channel_id,
        ):
            await self._send_registration_error(interaction)
            return

        await self.export_registration_snapshot(channel_id, "deregistration")
        remaining = await self.registrations.get(
            guild=guild, member=member.id, channel_id=channel_id
        )
        if role.id not in {
            item.role for item in remaining or () if item.role is not None
        }:
            await member.remove_roles(
                role, reason=f"{self.module_key.upper()} deregistration"
            )
        await interaction.followup.send(
            t(
                interaction,
                f"{self.module_key}.overview.registration.remove_registration",
                role_name=role.name,
            ),
            ephemeral=True,
        )
        await self.compose_registration_overview(force=True, channel_id=channel_id)

    async def _add_member_registration(
        self,
        interaction: discord.Interaction,
        guild: discord.Guild,
        member: discord.Member,
        role: discord.Role,
        channel_id: int,
        current: MemberRegistrationRepository._Data | None,
    ) -> None:
        if current is None and self.max_players is not None:
            count = await self.registrations.count(guild=guild, channel_id=channel_id)
            if count >= self.max_players:
                await interaction.followup.send(
                    t(
                        interaction,
                        f"{self.module_key}.overview.registration.full",
                        max_players=self.max_players,
                    ),
                    ephemeral=True,
                )
                return

        if not await self.registrations.add(
            guild=guild,
            member=member.id,
            role=role.id,
            account="",
            channel_id=channel_id,
            member_username=member.name,
            member_display_name=member.display_name,
            role_name=role.name,
        ):
            await self._send_registration_error(interaction)
            return

        is_update = current is not None and current.role != role.id
        event_type: RegistrationEventType = (
            "registration_change" if is_update else "registration"
        )
        await self.export_registration_snapshot(channel_id, event_type)
        if current is not None and current.role is not None and current.role != role.id:
            await self._remove_previous_role(guild, member, current.role, channel_id)
        await member.add_roles(role, reason=f"{self.module_key.upper()} registration")
        response_key = "update_registration" if is_update else "new_registration"
        await interaction.followup.send(
            t(
                interaction,
                f"{self.module_key}.overview.registration.{response_key}",
                role_name=role.name,
            ),
            ephemeral=True,
        )
        await self.compose_registration_overview(force=True, channel_id=channel_id)

    async def _remove_previous_role(
        self,
        guild: discord.Guild,
        member: discord.Member,
        role_id: int,
        channel_id: int,
    ) -> None:
        remaining = await self.registrations.get(
            guild=guild, member=member.id, channel_id=channel_id
        )
        if any(item.role == role_id for item in remaining or ()):
            return
        old_role = await utils.fetch_role(guild, role_id)
        if old_role is not None:
            await member.remove_roles(
                old_role,
                reason=f"{self.module_key.upper()} registration update",
            )

    async def export_registration_snapshot(
        self, channel_id: int, event_type: RegistrationEventType
    ) -> bool:
        """Export the current registration snapshot through the shared contract."""
        return await self._registration_snapshot_exporter.export(channel_id, event_type)

    async def export_startup_snapshots(self) -> None:
        """Export one startup snapshot for each configured registration channel."""
        await self._registration_snapshot_exporter.export_startup_snapshots()

    async def _send_registration_error(self, interaction: discord.Interaction) -> None:
        await interaction.followup.send(
            t(
                interaction,
                f"{self.module_key}.overview.registration.error_registration",
            ),
            ephemeral=True,
        )

    async def migrate_schema(self) -> bool:
        """Ensure shared registration tables exist and migrate their schema."""
        if not await self._ensure_registration_schema():
            return False
        for repository in (
            self.registration,
            self.roles,
            self.registrations,
        ):
            if not await repository.migrate_schema():
                _logger.error(
                    "%s Failed to synchronize %s table %s.",
                    sqlite_db.Base.log_prefix(self.guild),
                    self.module_key.upper(),
                    repository.table_name,
                )
                return False
        return True

    async def on_member_update(
        self, before: discord.Member, after: discord.Member
    ) -> bool:
        """Keep manually changed registration roles in sync with stored signups."""
        if before.guild.id != self.guild.id:
            return False
        if not await self.migrate_schema():
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

        role_channels = {role.role: role.channel_id for role in configured_roles}
        registration_role_ids = set(role_channels)
        added_registration_roles = added_role_ids & registration_role_ids
        removed_registration_roles = removed_role_ids & registration_role_ids
        if not added_registration_roles and not removed_registration_roles:
            return True

        member_registrations = await self.registrations.get(
            guild=self.guild,
            member=after.id,
        )
        tracked_roles = {
            record.role
            for record in member_registrations or ()
            if record.role is not None
        }
        removed_channels = await self._remove_member_role_registrations(
            after,
            removed_registration_roles & tracked_roles,
            role_channels,
        )
        additions_changed, added_channels = await self._add_member_role_registrations(
            after,
            added_registration_roles,
            removed_registration_roles,
            role_channels,
            after_role_ids,
        )
        changed_channels = removed_channels | added_channels
        if removed_channels or additions_changed:
            await self._publish_registration_changes(changed_channels)
        return True

    async def _remove_member_role_registrations(
        self,
        member: discord.Member,
        role_ids: set[int],
        role_channels: dict[int, int],
    ) -> set[int]:
        changed_channels: set[int] = set()
        for role_id in role_ids:
            channel_id = role_channels[role_id]
            if await self.registrations.remove_member_role(
                guild=self.guild,
                member=member.id,
                role=role_id,
                channel_id=channel_id,
            ):
                changed_channels.add(channel_id)
        return changed_channels

    async def _add_member_role_registrations(
        self,
        member: discord.Member,
        role_ids: set[int],
        removed_role_ids: set[int],
        role_channels: dict[int, int],
        member_role_ids: set[int],
    ) -> tuple[bool, set[int]]:
        added_by_channel: dict[int, list[int]] = {}
        for role_id in role_ids:
            added_by_channel.setdefault(role_channels[role_id], []).append(role_id)

        changed = False
        changed_channels: set[int] = set()
        for channel_id, channel_role_ids in added_by_channel.items():
            current = await self.registrations.get(
                guild=self.guild,
                member=member.id,
                account="",
                channel_id=channel_id,
            )
            current_registration = current[0] if current else None
            if (
                current_registration is not None
                and current_registration.role not in removed_role_ids
                and current_registration.role in member_role_ids
            ):
                continue

            selected_role_id = min(channel_role_ids)
            selected_role = self.guild.get_role(selected_role_id)
            changed = (
                await self.registrations.add(
                    guild=self.guild,
                    member=member.id,
                    role=selected_role_id,
                    account="",
                    channel_id=channel_id,
                    member_username=member.name,
                    member_display_name=member.display_name,
                    role_name=selected_role.name if selected_role is not None else None,
                )
                or changed
            )
            changed_channels.add(channel_id)
        return changed, changed_channels

    async def _publish_registration_changes(self, channel_ids: set[int]) -> None:
        for channel_id in channel_ids:
            await self.export_registration_snapshot(channel_id, "sync")
        for channel_id in channel_ids:
            await self.compose_registration_overview(force=True, channel_id=channel_id)

    async def compose_registration_overview(
        self, force: bool = False, channel_id: int | None = None
    ) -> bool:
        """Compose one registration overview or all configured overviews."""
        if channel_id is not None:
            return await self._overview_for(channel_id).compose(force=force)
        configurations = await self.registration.get_all(guild=self.guild)
        if not configurations:
            return False
        results = await asyncio.gather(
            *(
                self._overview_for(configuration.channel).compose(force=force)
                for configuration in configurations
                if configuration.channel is not None
            )
        )
        return all(results)

    async def _ensure_registration_schema(self) -> bool:
        database = self.database
        if database is None:
            _logger.error(
                "%s Cannot create %s schema without a database.",
                sqlite_db.Base.log_prefix(self.guild),
                self.module_key.upper(),
            )
            return False
        for repository in (
            self.registration,
            self.registration_event_channel,
            self.roles,
            self.registrations,
            self.list,
        ):
            if not await database.execute(repository.table):
                _logger.error(
                    "%s Failed to create %s table %s.",
                    sqlite_db.Base.log_prefix(self.guild),
                    self.module_key.upper(),
                    repository.table_name,
                )
                return False
        return True
