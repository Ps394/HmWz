from __future__ import annotations

import logging

import discord

from hmwz import sqlite_db

_logger = logging.getLogger(__name__)


class DiscordEntityRepository(sqlite_db.Base):
    """Persists current and last-known Discord member and channel names."""

    table_name = "DiscordMembers"
    channels_table_name = "DiscordChannels"
    roles_table_name = "DiscordRoles"

    @property
    def tables(self) -> tuple[str, str, str]:
        """Return the entity table creation statements."""
        return (
            f"""
            CREATE TABLE IF NOT EXISTS {self.table_name} (
                Guild INTEGER NOT NULL,
                Member INTEGER NOT NULL,
                Username TEXT NOT NULL,
                DisplayName TEXT NOT NULL,
                PRIMARY KEY (Guild, Member),
                FOREIGN KEY (Guild) REFERENCES Servers(Guild) ON DELETE CASCADE
            ) WITHOUT ROWID
            """,
            f"""
            CREATE TABLE IF NOT EXISTS {self.channels_table_name} (
                Guild INTEGER NOT NULL,
                Channel INTEGER NOT NULL,
                Name TEXT NOT NULL,
                PRIMARY KEY (Guild, Channel),
                FOREIGN KEY (Guild) REFERENCES Servers(Guild) ON DELETE CASCADE
            ) WITHOUT ROWID
            """,
            f"""
            CREATE TABLE IF NOT EXISTS {self.roles_table_name} (
                Guild INTEGER NOT NULL,
                Role INTEGER NOT NULL,
                Name TEXT NOT NULL,
                PRIMARY KEY (Guild, Role),
                FOREIGN KEY (Guild) REFERENCES Servers(Guild) ON DELETE CASCADE
            ) WITHOUT ROWID
            """,
        )

    async def add_member(
        self, *, guild: discord.Guild, member: discord.Member | discord.User
    ) -> bool:
        """Insert or update one member's username and display name."""
        update_clause = "Username = excluded.Username"
        if isinstance(member, discord.Member):
            update_clause += ", DisplayName = excluded.DisplayName"
        return await self.database.execute(
            f"""
            INSERT INTO {self.table_name} (Guild, Member, Username, DisplayName)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(Guild, Member) DO UPDATE SET {update_clause}
            """,
            (guild.id, member.id, member.name, member.display_name),
        )

    async def add_channel(
        self,
        *,
        guild: discord.Guild,
        channel: discord.abc.GuildChannel | discord.Thread,
    ) -> bool:
        """Insert or update a channel's name."""
        return await self.database.execute(
            f"""
            INSERT INTO {self.channels_table_name} (Guild, Channel, Name)
            VALUES (?, ?, ?)
            ON CONFLICT(Guild, Channel) DO UPDATE SET Name = excluded.Name
            """,
            (guild.id, channel.id, channel.name),
        )

    async def add_role(self, *, role: discord.Role) -> bool:
        """Insert or update a role's name."""
        return await self.database.execute(
            f"""
            INSERT INTO {self.roles_table_name} (Guild, Role, Name)
            VALUES (?, ?, ?)
            ON CONFLICT(Guild, Role) DO UPDATE SET Name = excluded.Name
            """,
            (role.guild.id, role.id, role.name),
        )

    async def sync_guild(self, guild: discord.Guild) -> bool:
        """Persist names for members, channels, and roles currently in a guild."""
        member_rows = [
            (guild.id, member.id, member.name, member.display_name)
            for member in guild.members
        ]
        channel_rows = [
            (guild.id, channel.id, channel.name)
            for channel in (*guild.channels, *guild.threads)
        ]
        role_rows = [(guild.id, role.id, role.name) for role in guild.roles]

        members_saved = not member_rows or await self.database.execute_many(
            f"""
            INSERT INTO {self.table_name} (Guild, Member, Username, DisplayName)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(Guild, Member) DO UPDATE SET
                Username = excluded.Username,
                DisplayName = excluded.DisplayName
            """,
            member_rows,
        )
        channels_saved = not channel_rows or await self.database.execute_many(
            f"""
            INSERT INTO {self.channels_table_name} (Guild, Channel, Name)
            VALUES (?, ?, ?)
            ON CONFLICT(Guild, Channel) DO UPDATE SET Name = excluded.Name
            """,
            channel_rows,
        )
        roles_saved = not role_rows or await self.database.execute_many(
            f"""
            INSERT INTO {self.roles_table_name} (Guild, Role, Name)
            VALUES (?, ?, ?)
            ON CONFLICT(Guild, Role) DO UPDATE SET Name = excluded.Name
            """,
            role_rows,
        )
        if not members_saved or not channels_saved or not roles_saved:
            _logger.error(
                "%s Failed to sync Discord entity names.", self.log_prefix(guild)
            )
            return False

        _logger.info(
            "%s Saved %s member, %s channel, and %s role names.",
            self.log_prefix(guild),
            len(member_rows),
            len(channel_rows),
            len(role_rows),
        )
        return True

    async def remove_guild(self, *, guild: discord.Guild) -> bool:
        """Remove cached names for a guild before its server row is deleted."""
        members_removed = await self.database.execute(
            f"DELETE FROM {self.table_name} WHERE Guild = ?", (guild.id,)
        )
        channels_removed = await self.database.execute(
            f"DELETE FROM {self.channels_table_name} WHERE Guild = ?", (guild.id,)
        )
        roles_removed = await self.database.execute(
            f"DELETE FROM {self.roles_table_name} WHERE Guild = ?", (guild.id,)
        )
        return members_removed and channels_removed and roles_removed
