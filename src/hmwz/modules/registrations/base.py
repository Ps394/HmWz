from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import discord

from hmwz import sqlite_db, utils
from hmwz.hm_client.repositories import DiscordEntityRepository
from hmwz.i18n import t
from hmwz.modules.basic_module import BasicModule

from .overview import RegistrationOverview

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
    entities: DiscordEntityRepository

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
        self.entities = DiscordEntityRepository(database)
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
            if not await self.entities.add_member(guild=guild, member=member):
                await self._send_registration_error(interaction)
                _logger.error(
                    "%s Failed to persist member %s before registration.",
                    sqlite_db.Base.log_prefix(guild),
                    member.id,
                )
                return

            records = await self.registrations.get(
                guild=guild,
                member=member.id,
                account="",
                channel_id=channel_id,
            )
            current = records[0] if records else None
            if current is not None and current.role == role.id:
                if not await self.registrations.remove(
                    guild=guild,
                    member=member.id,
                    account="",
                    channel_id=channel_id,
                ):
                    await self._send_registration_error(interaction)
                    return
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
                await self.compose_registration_overview(
                    force=True, channel_id=channel_id
                )
                return

            if current is None and self.max_players is not None:
                count = await self.registrations.count(
                    guild=guild, channel_id=channel_id
                )
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
            ):
                await self._send_registration_error(interaction)
                return

            is_update = current is not None and current.role != role.id
            if current and current.role is not None and current.role != role.id:
                remaining = await self.registrations.get(
                    guild=guild, member=member.id, channel_id=channel_id
                )
                old_role_is_used = any(
                    item.role == current.role for item in remaining or ()
                )
                old_role = await utils.fetch_role(guild, current.role)
                if not old_role_is_used and old_role is not None:
                    await member.remove_roles(
                        old_role,
                        reason=f"{self.module_key.upper()} registration update",
                    )
            await member.add_roles(
                role, reason=f"{self.module_key.upper()} registration"
            )
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

    async def _send_registration_error(self, interaction: discord.Interaction) -> None:
        await interaction.followup.send(
            t(
                interaction,
                f"{self.module_key}.overview.registration.error_registration",
            ),
            ephemeral=True,
        )

    async def sync_names(self) -> bool:
        """Ensure shared registration tables exist and synchronize cached names."""
        if not await self._ensure_registration_schema():
            return False
        for repository in (
            self.registration,
            self.roles,
            self.registrations,
        ):
            if not await repository.migrate_names():
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
        changed = False
        changed_channels: set[int] = set()
        tracked_roles = {
            record.role
            for record in member_registrations or ()
            if record.role is not None
        }
        for role_id in removed_registration_roles & tracked_roles:
            channel_id = role_channels[role_id]
            role_removed = await self.registrations.remove_member_role(
                guild=self.guild,
                member=after.id,
                role=role_id,
                channel_id=channel_id,
            )
            changed = role_removed or changed
            if role_removed:
                changed_channels.add(channel_id)

        added_by_channel: dict[int, list[int]] = {}
        for role_id in added_registration_roles:
            added_by_channel.setdefault(role_channels[role_id], []).append(role_id)
        for channel_id, role_ids in added_by_channel.items():
            current = await self.registrations.get(
                guild=self.guild,
                member=after.id,
                account="",
                channel_id=channel_id,
            )
            current_registration = current[0] if current else None
            if (
                current_registration is not None
                and current_registration.role not in removed_registration_roles
                and current_registration.role in after_role_ids
            ):
                continue
            changed = (
                await self.registrations.add(
                    guild=self.guild,
                    member=after.id,
                    role=min(role_ids),
                    account="",
                    channel_id=channel_id,
                )
                or changed
            )
            changed_channels.add(channel_id)

        if changed:
            for channel_id in changed_channels:
                await self.compose_registration_overview(
                    force=True, channel_id=channel_id
                )
        return True

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
