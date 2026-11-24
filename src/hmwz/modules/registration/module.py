"""Guild-scoped application services for independent registrations."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import aiosqlite
import discord

from hmwz import events, sqlite_db
from hmwz.i18n import t
from hmwz.modules.module import Module
from hmwz.modules.protocols import (
    MemberModuleProtocol,
    MessageModuleProtocol,
    RoleModuleProtocol,
)
from hmwz.modules.managed_messages import ManagedMessagesModule
from .managed_messages import RegistrationManagedMessagesAdapter
from .services import RegistrationMutationService
from hmwz.modules.registry import register
from hmwz.modules.registration.snapshot import (
    RegistrationEventType,
    RegistrationSnapshotExporter,
)
from hmwz.ui.messages import send_temporary_followup

from .overview import RegistrationOverview
from .repositories import (
    MemberRegistrationRepository,
    RegistrationRoleRepository,
    RegistrationSettingsRepository,
    RegistrationSnapshotChannelRepository,
    RegistrationSnapshotMessageRepository,
)

_logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from hmwz.client import Client


@register
class RegistrationModule(
    Module, MessageModuleProtocol, RoleModuleProtocol, MemberModuleProtocol
):
    """Guild-scoped module for independent registration configurations."""

    module_key: str = "registration"
    max_players: int | None = None

    def __init__(self, guild: discord.Guild, client: Client) -> None:
        super().__init__(guild, client)
        database = self.database
        if not isinstance(database, sqlite_db.Database):
            raise RuntimeError("Registration module requires a database.")
        from hmwz.modules.hs.account.repositories import MemberGameAccountRepository

        self.registration = RegistrationSettingsRepository(database)
        self.roles = RegistrationRoleRepository(database)
        self.registrations = MemberRegistrationRepository(database)
        self.game_accounts = MemberGameAccountRepository(database)
        self._schema_ready = False
        self._initialize_registration(
            registration=self.registration,
            roles=self.roles,
            registrations=self.registrations,
        )

    registration: RegistrationSettingsRepository
    roles: RegistrationRoleRepository
    registrations: MemberRegistrationRepository
    registration_event_channel: RegistrationSnapshotChannelRepository
    registration_snapshot_messages: RegistrationSnapshotMessageRepository

    def _initialize_registration(
        self,
        *,
        registration: RegistrationSettingsRepository,
        roles: RegistrationRoleRepository,
        registrations: MemberRegistrationRepository,
    ) -> None:
        database = self.database
        if database is None:
            raise RuntimeError("Registration module requires a database.")
        self.registration = registration
        self.roles = roles
        self.registrations = registrations
        self.registration_event_channel = RegistrationSnapshotChannelRepository(
            database
        )
        self.registration_snapshot_messages = RegistrationSnapshotMessageRepository(
            database
        )
        self._registration_snapshot_exporter = RegistrationSnapshotExporter(
            client=self.client,
            guild=self.guild,
            module_key=self.module_key,
            event_channel=self.registration_event_channel,
            registration=self.registration,
            registrations=self.registrations,
            snapshot_messages=self.registration_snapshot_messages,
        )
        self._managed_messages: ManagedMessagesModule | None = None
        self._managed_messages_adapter: RegistrationManagedMessagesAdapter | None = None
        self._overviews: dict[int, RegistrationOverview] = {}
        self._mutations = RegistrationMutationService(self)

    def _overview_for(self, channel_id: int) -> RegistrationOverview:
        overview = self._overviews.get(channel_id)
        if overview is None:
            overview = RegistrationOverview(
                guild=self.guild,
                client=self.client,
                registration=self.registration,
                roles=self.roles,
                registrations=self.registrations,
                registration_handler=self._handle_registration,
                managed_messages=ManagedMessagesModule(self.guild, self.client),
                channel_id=channel_id,
                module_key=self.module_key,
                max_players=self.max_players,
                managed_messages_adapter=None,
            )
            self._overviews[channel_id] = overview
        return overview

    async def _managed_messages_adapter_for(self) -> RegistrationManagedMessagesAdapter:
        if self._managed_messages_adapter is not None:
            return self._managed_messages_adapter
        manager = getattr(self.client, "module_manager", None)
        if manager is not None:
            managed_messages = await manager.get_module(
                self.guild, ManagedMessagesModule
            )
        else:
            managed_messages = ManagedMessagesModule(self.guild, self.client)
        await managed_messages.sync()
        self._managed_messages = managed_messages
        self._managed_messages_adapter = RegistrationManagedMessagesAdapter(
            guild=self.guild,
            managed_messages=managed_messages,
        )
        managed_messages.register_batch_refresh_handler(
            owner_id="registration",
            handler=self._refresh_managed_registration_messages,
        )
        managed_messages.register_channel_delete_handler(
            owner_id="registration",
            handler=self._delete_managed_registration_channel,
        )
        return self._managed_messages_adapter

    async def _managed_messages_for(self) -> ManagedMessagesModule:
        adapter = await self._managed_messages_adapter_for()
        return adapter.managed_messages

    async def _delete_managed_registration_channel(
        self, channel_id: int, managed_ids
    ) -> bool:
        del managed_ids
        adapter = await self._managed_messages_adapter_for()
        return await adapter.delete_channel(channel_id)

    async def _refresh_managed_registration_messages(
        self, managed_ids: frozenset[str]
    ) -> bool:
        channel_ids: set[int] = set()
        adapter = await self._managed_messages_adapter_for()
        for managed_id in managed_ids:
            channel_id = adapter.channel_id(managed_id)
            if channel_id is not None:
                channel_ids.add(channel_id)
        results = [
            await self.compose_registration_overview(
                force=True,
                channel_id=channel_id,
            )
            for channel_id in channel_ids
        ]
        return all(results)

    async def activate_managed_messages_for_channel(
        self, channel_id: int
    ) -> RegistrationManagedMessagesAdapter:
        """Activate the shared publisher for one registration channel."""
        adapter = await self._managed_messages_adapter_for()
        overview = self._overview_for(channel_id)
        overview.managed_messages_adapter = adapter
        overview._list_overview.managed_messages_adapter = adapter
        return adapter

    def queue_registration_refresh(self, channel_id: int) -> asyncio.Task[bool]:
        """Queue one shared 250 ms refresh for a registration channel."""
        adapter = self._managed_messages_adapter
        if adapter is None:
            raise RuntimeError("Registration managed messages are not initialized.")
        return adapter.managed_messages.queue_refresh(
            "registration",
            adapter.main_id(channel_id),
            force=True,
        )

    async def _queue_all_registration_refreshes(self) -> None:
        configurations = await self.registration.get_all(guild=self.guild)
        for configuration in configurations or ():
            if configuration.channel is not None:
                await self.queue_registration_refresh(configuration.channel)

    async def _handle_registration(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
        *,
        response_deferred: bool = False,
    ) -> None:
        """Delegate the member mutation to the focused registration service."""
        await self._mutations.handle(
            interaction,
            role,
            response_deferred=response_deferred,
        )

    async def _remove_member_registration(
        self,
        interaction: discord.Interaction,
        guild: discord.Guild,
        member: discord.Member,
        role: discord.Role,
        channel_id: int,
    ) -> None:
        await self._mutations.remove(
            interaction,
            guild,
            member,
            role,
            channel_id,
        )

    async def _add_member_registration(
        self,
        interaction: discord.Interaction,
        guild: discord.Guild,
        member: discord.Member,
        role: discord.Role,
        channel_id: int,
        current: MemberRegistrationRepository._Data | None,
    ) -> None:
        await self._mutations.add(
            interaction,
            guild,
            member,
            role,
            channel_id,
            current,
        )

    async def _remove_previous_role(
        self,
        guild: discord.Guild,
        member: discord.Member,
        role_id: int,
        channel_id: int,
    ) -> None:
        await self._mutations._remove_previous_role(
            guild,
            member,
            role_id,
            channel_id,
        )

    async def export_registration_snapshot(
        self, channel_id: int, event_type: RegistrationEventType
    ) -> bool:
        """Export the current registration snapshot through the shared contract."""
        return await self._registration_snapshot_exporter.export(channel_id, event_type)

    async def sync(self, startup: bool = False) -> bool:
        """Migrate registration schemas to the current version.

        Args:
            startup: Accepted for the shared module contract; snapshots are
                exported only on explicit commands.

        Returns:
            Whether the schema migration succeeded.
        """
        return await self.migrate_schema()

    async def ensure(self) -> bool:
        """Restore overview messages for all configured registration channels.

        Returns:
            Whether every configured overview was synchronized successfully.
        """
        adapter = await self._managed_messages_adapter_for()
        if not await adapter.managed_messages.sync():
            return False
        configurations = await self.registration.get_all(guild=self.guild)
        if not configurations:
            return True
        results = [
            await self.compose_registration_overview(
                force=True,
                channel_id=configuration.channel,
            )
            for configuration in configurations
            if configuration.channel is not None
        ]
        return all(results)

    async def on_guild_join(self, guild: discord.Guild) -> bool:
        """Initialize this module when the bot joins its guild."""
        return guild.id == self.guild.id and await self.sync(startup=True)

    async def on_guild_remove(self, guild: discord.Guild) -> bool:
        """Remove managed messages and persisted registration data for a guild."""
        if guild.id != self.guild.id:
            return False
        if self._managed_messages is not None:
            managed_removed = await self._managed_messages.on_guild_remove(guild)
        else:
            managed_removed = True
        data_removed = await self._remove_guild_data(guild)
        return managed_removed and data_removed

    async def _remove_guild_data(self, guild: discord.Guild) -> bool:
        """Delete all registration-owned guild records in one transaction."""
        database = self.database
        if database is None:
            _logger.error(
                "%s Cannot remove registration data without a database.",
                sqlite_db.Base.log_prefix(guild),
            )
            return False
        table_names = (
            self.registration_snapshot_messages.table_name,
            self.registration_event_channel.table_name,
            self.registration_event_channel.legacy_table_name,
            self.registrations.table_name,
            self.registrations.legacy_table_name,
            self.roles.table_name,
            self.roles.legacy_table_name,
            "Registration_Messages",
            self.registration.table_name,
            self.game_accounts.table_name,
        )
        try:
            async with database.connect() as connection:
                await connection.execute("BEGIN IMMEDIATE")
                existing_rows = await connection.execute_fetchall(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
                existing_tables = {row["name"] for row in existing_rows}
                for table_name in table_names:
                    if table_name is not None and table_name in existing_tables:
                        await connection.execute(
                            f'DELETE FROM "{table_name}" WHERE Guild = ?',
                            (guild.id,),
                        )
                await connection.commit()
            return True
        except aiosqlite.Error:
            _logger.exception(
                "%s Failed to remove registration data for guild.",
                guild.name,
            )
            return False

    async def on_message_create(self, message: discord.Message) -> bool:
        """Ignore newly created messages not managed by the module."""
        return True

    async def on_message_update(
        self, before: discord.Message, after: discord.Message
    ) -> bool:
        """Ignore edits to messages not managed by the module."""
        return True

    async def on_message_delete(self, message: discord.Message) -> bool:
        """Forward a cached message deletion for this guild to the overview service."""
        if message.guild is not None and message.guild.id == self.guild.id:
            if self._managed_messages is not None:
                return await self._managed_messages.on_message_delete(message)
            return True
        return True

    async def on_raw_message_delete(
        self, payload: events.RawMessageDeleteEvent
    ) -> bool:
        """Forward a raw message deletion to managed Registration messages."""
        if payload.guild_id != self.guild.id:
            return False
        if self._managed_messages is not None:
            return await self._managed_messages.on_raw_message_delete(payload)
        return True

    async def on_raw_bulk_message_delete(
        self, payload: events.RawBulkMessageDeleteEvent
    ) -> bool:
        """Forward a bulk message deletion to managed Registration messages."""
        if payload.guild_id != self.guild.id:
            return False
        if self._managed_messages is not None:
            return await self._managed_messages.on_raw_bulk_message_delete(payload)
        return True

    async def on_guild_role_create(self, role: discord.Role) -> bool:
        """Confirm that a newly created role belongs to this module's guild."""
        return role.guild.id == self.guild.id

    async def on_guild_role_update(
        self, before: discord.Role, after: discord.Role
    ) -> bool:
        """Refresh this guild's overview after a role is updated."""
        if before.guild.id != self.guild.id:
            return False
        await self._queue_all_registration_refreshes()
        return True

    async def on_guild_role_delete(self, role: discord.Role) -> bool:
        """Remove a deleted role and its registrations from the guild."""
        if role.guild.id != self.guild.id:
            return False
        if not await self.roles.remove(guild=self.guild, role=role.id):
            return False
        if not await self.registrations.remove(guild=self.guild, role=role.id):
            return False
        await self._queue_all_registration_refreshes()
        return True

    async def on_raw_member_remove(self, payload: events.RawMemberRemoveEvent) -> bool:
        """Remove registrations belonging to a member who left this guild."""
        if payload.guild_id != self.guild.id:
            return False
        if not await self.registrations.remove(
            guild=self.guild, member=payload.user.id
        ):
            return False
        await self._queue_all_registration_refreshes()
        return True

    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel) -> bool:
        """Confirm that a newly created channel belongs to this guild."""
        return channel.guild.id == self.guild.id

    async def on_guild_channel_update(
        self,
        before: discord.abc.GuildChannel,
        after: discord.abc.GuildChannel,
    ) -> bool:
        """Refresh this guild's registration overview after a channel update."""
        if before.guild.id != self.guild.id:
            return False
        await self.queue_registration_refresh(after.id)
        return True

    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> bool:
        """Remove configuration and overview data for a deleted channel."""
        if channel.guild.id != self.guild.id:
            return False
        if self._managed_messages is not None:
            await self._managed_messages.on_guild_channel_delete(channel)
        status = True
        status = (
            await self.registrations.remove(guild=self.guild, channel_id=channel.id)
            and status
        )
        status = (
            await self.roles.remove(guild=self.guild, channel_id=channel.id) and status
        )
        status = (
            await self.registration.remove(guild=self.guild, channel_id=channel.id)
            and status
        )
        return status

    async def _send_registration_error(self, interaction: discord.Interaction) -> None:
        await send_temporary_followup(
            interaction,
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
        if not await self.registration_event_channel.migrate_schema():
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
            await self.queue_registration_refresh(channel_id)

    async def compose_registration_overview(
        self, force: bool = False, channel_id: int | None = None
    ) -> bool:
        """Compose one registration overview or all configured overviews."""
        if channel_id is not None:
            await self.activate_managed_messages_for_channel(channel_id)
            return await self._overview_for(channel_id).compose(force=force)
        configurations = await self.registration.get_all(guild=self.guild)
        if not configurations:
            return False
        results = await asyncio.gather(
            *(
                self._compose_configured_registration_overview(
                    configuration.channel, force
                )
                for configuration in configurations
                if configuration.channel is not None
            )
        )
        return all(results)

    async def _compose_configured_registration_overview(
        self, channel_id: int, force: bool
    ) -> bool:
        await self.activate_managed_messages_for_channel(channel_id)
        return await self._overview_for(channel_id).compose(force=force)

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
            self.registration_snapshot_messages,
            self.roles,
            self.registrations,
            self.game_accounts,
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
