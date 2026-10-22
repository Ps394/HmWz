from __future__ import annotations

import asyncio
import logging
import typing
from dataclasses import dataclass

import discord

from hmwz import sqlite_db

_logger = logging.getLogger(__name__)


class MemberRegistrationRepository(sqlite_db.Base):
    """Repository fuer Mitgliederregistrierungen je Guild."""

    table_name = "Registrations_Member"
    settings_table_name = "Registration"

    def __init__(self, database: sqlite_db.Database):
        super().__init__(database)

    @dataclass(frozen=True)
    class TableCols:
        Guild: str = "Guild"
        Channel: str = "Channel"
        Member: str = "Member"
        Account: str = "Account"
        Role: str = "Role"
        Timestamp: str = "Timestamp"
        GuildName: str = "GuildName"
        MemberUsername: str = "MemberUsername"
        MemberDisplayName: str = "MemberDisplayName"
        RoleName: str = "RoleName"

    @property
    def table(self) -> str:
        return f"""
        CREATE TABLE IF NOT EXISTS {self.table_name} (
            {self.TableCols.Guild} INTEGER,
            {self.TableCols.Channel} INTEGER NOT NULL DEFAULT 0,
            {self.TableCols.Member} INTEGER,
            {self.TableCols.Account} TEXT NOT NULL DEFAULT '',
            {self.TableCols.Role} INTEGER,
            {self.TableCols.Timestamp} TEXT DEFAULT CURRENT_TIMESTAMP,
            {self.TableCols.GuildName} TEXT,
            {self.TableCols.MemberUsername} TEXT,
            {self.TableCols.MemberDisplayName} TEXT,
            {self.TableCols.RoleName} TEXT,
            PRIMARY KEY (
                {self.TableCols.Guild}, {self.TableCols.Channel},
                {self.TableCols.Member}, {self.TableCols.Account}
            )
        ) WITHOUT ROWID
        """

    async def migrate_names(self) -> bool:
        """Add and populate readable names for existing registration records."""
        if not await self.ensure_columns(
            (
                (self.TableCols.Channel, "INTEGER NOT NULL DEFAULT 0"),
                (self.TableCols.GuildName, "TEXT"),
                (self.TableCols.MemberUsername, "TEXT"),
                (self.TableCols.MemberDisplayName, "TEXT"),
                (self.TableCols.RoleName, "TEXT"),
            )
        ):
            return False
        if not await self._migrate_account_key():
            return False
        return await self.database.execute(
            f"""
            UPDATE {self.table_name}
            SET {self.TableCols.GuildName} = COALESCE(
                    (SELECT Name FROM Servers WHERE Guild = {self.table_name}.Guild),
                    {self.TableCols.GuildName}
                ),
                {self.TableCols.MemberUsername} = COALESCE(
                    (SELECT Username FROM DiscordMembers
                     WHERE Guild = {self.table_name}.Guild
                       AND Member = {self.table_name}.Member),
                    {self.TableCols.MemberUsername}
                ),
                {self.TableCols.MemberDisplayName} = COALESCE(
                    (SELECT DisplayName FROM DiscordMembers
                     WHERE Guild = {self.table_name}.Guild
                       AND Member = {self.table_name}.Member),
                    {self.TableCols.MemberDisplayName}
                ),
                {self.TableCols.RoleName} = COALESCE(
                    (SELECT Name FROM DiscordRoles
                     WHERE Guild = {self.table_name}.Guild
                       AND Role = {self.table_name}.Role),
                    {self.TableCols.RoleName}
                )
            """
        )

    async def _migrate_account_key(self) -> bool:
        """Move legacy registrations to a key that supports multiple accounts."""
        try:
            async with self.database.connect() as connection:
                await connection.execute("BEGIN IMMEDIATE")
                cursor = await connection.execute(
                    f'PRAGMA table_info("{self.table_name}")'
                )
                columns = await cursor.fetchall()
                account_column = next(
                    (column for column in columns if column["name"] == "Account"),
                    None,
                )
                channel_column = next(
                    (column for column in columns if column["name"] == "Channel"),
                    None,
                )
                if (
                    account_column is not None
                    and account_column["pk"] > 0
                    and channel_column is not None
                    and channel_column["pk"] > 0
                ):
                    await connection.commit()
                    return True

                account_value = (
                    f"COALESCE({self.TableCols.Account}, '')"
                    if account_column is not None
                    else "''"
                )
                channel_value = (
                    f"COALESCE({self.TableCols.Channel}, 0)"
                    if channel_column is not None and channel_column["pk"] > 0
                    else f"""
                    COALESCE(
                        (SELECT Channel FROM {self.settings_table_name}
                         WHERE Guild = {self.table_name}_legacy.Guild
                         ORDER BY Channel LIMIT 1),
                        0
                    )
                    """
                )
                await connection.execute(
                    f"""
                    CREATE TABLE "{self.table_name}_new" (
                        Guild INTEGER,
                        Channel INTEGER NOT NULL DEFAULT 0,
                        Member INTEGER,
                        Account TEXT NOT NULL DEFAULT '',
                        Role INTEGER,
                        Timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                        GuildName TEXT,
                        MemberUsername TEXT,
                        MemberDisplayName TEXT,
                        RoleName TEXT,
                        PRIMARY KEY (Guild, Channel, Member, Account)
                    ) WITHOUT ROWID
                    """
                )
                await connection.execute(
                    f"""
                    INSERT OR IGNORE INTO "{self.table_name}_new"
                    (Guild, Channel, Member, Account, Role, Timestamp, GuildName,
                     MemberUsername, MemberDisplayName, RoleName)
                    SELECT Guild, {channel_value}, Member, {account_value}, Role, Timestamp,
                           GuildName, MemberUsername, MemberDisplayName, RoleName
                    FROM "{self.table_name}" AS {self.table_name}_legacy
                    """
                )
                await connection.execute(f'DROP TABLE "{self.table_name}"')
                await connection.execute(
                    f'ALTER TABLE "{self.table_name}_new" RENAME TO "{self.table_name}"'
                )
                await connection.commit()
            return True
        except Exception:
            _logger.exception(
                "%s Failed to migrate WZ registrations for multiple accounts.",
                self.log_prefix(),
            )
            return False

    @dataclass(frozen=True)
    class _Data:
        guild_id: int
        channel_id: int
        member: int | None
        account: str
        role: int | None
        timestamp: str

        @property
        def has_member(self) -> bool:
            return self.member is not None

        @property
        def has_role(self) -> bool:
            return self.role is not None

    type Record = _Data | None
    type Records = tuple[_Data, ...] | None

    async def count(
        self,
        *,
        guild: discord.Guild,
        role: int | None = None,
        roles: list[int] | None = None,
        channel_id: int | None = None,
    ) -> int:
        try:
            if role is not None and roles:
                raise ValueError("Cannot provide both role and roles filters.")

            query = f"SELECT COUNT(*) FROM {self.table_name} WHERE {self.TableCols.Guild} = ?"
            params: list[typing.Any] = [guild.id]
            if channel_id is not None:
                query += f" AND {self.TableCols.Channel} = ?"
                params.append(channel_id)

            if role is not None:
                query += f" AND {self.TableCols.Role} = ?"
                params.append(role)
            elif roles:
                placeholders = ",".join("?" for _ in roles)
                query += f" AND {self.TableCols.Role} IN ({placeholders})"
                params.extend(roles)

            row = await self.database.fetch_one(query, tuple(params))
            return row[0] if row else 0
        except Exception as e:
            _logger.exception(
                f"{self.log_prefix(guild)} Failed to count WZ registrations: {e}"
            )
            return 0

    async def get(
        self,
        *,
        guild: discord.Guild,
        member: int | None = None,
        account: str | None = None,
        role: int | None = None,
        roles: list[int] | None = None,
        channel_id: int | None = None,
    ) -> Records:
        try:
            if member is not None and (role is not None or roles):
                raise ValueError("Cannot combine member with role or roles filters.")
            if account is not None and (member is None or role is not None or roles):
                raise ValueError("Account filters require a member filter only.")
            if role is not None and roles:
                raise ValueError("Cannot provide both role and roles filters.")

            query = f"SELECT * FROM {self.table_name} WHERE {self.TableCols.Guild} = ?"
            params: list[typing.Any] = [guild.id]
            if channel_id is not None:
                query += f" AND {self.TableCols.Channel} = ?"
                params.append(channel_id)

            if member is not None:
                query += f" AND {self.TableCols.Member} = ?"
                params.append(member)
                if account is not None:
                    query += f" AND {self.TableCols.Account} = ?"
                    params.append(account)
            elif roles:
                placeholders = ",".join("?" for _ in roles)
                query += f" AND {self.TableCols.Role} IN ({placeholders})"
                params.extend(roles)
            elif role is not None:
                query += f" AND {self.TableCols.Role} = ?"
                params.append(role)

            records = await self.database.fetch_all(query, tuple(params))
            if not records:
                return None

            async def resolve_record(
                rec: typing.Any,
            ) -> MemberRegistrationRepository._Data:
                return self._Data(
                    guild_id=guild.id,
                    channel_id=rec[self.TableCols.Channel],
                    member=rec[self.TableCols.Member],
                    account=rec[self.TableCols.Account],
                    role=rec[self.TableCols.Role],
                    timestamp=rec[self.TableCols.Timestamp],
                )

            out: list[MemberRegistrationRepository._Data] = await asyncio.gather(
                *(resolve_record(rec) for rec in records)
            )
            return tuple(out) if out else None
        except Exception as e:
            _logger.exception(
                f"{self.log_prefix(guild)} Failed to get WZ registrations: {e}"
            )
            return None

    async def add(
        self,
        *,
        guild: discord.Guild,
        member: int,
        role: int,
        account: str = "",
        channel_id: int = 0,
    ) -> bool:
        member_name = f"unknown member ({member})"
        try:
            member_names = await self.member_names(guild, member)
            role_name = await self.role_name(guild, role)
            if member_names is not None:
                member_name = f"{member_names[0]} / {member_names[1]} ({member})"
            executed = await self.database.execute(
                f"""
                INSERT OR REPLACE INTO {self.table_name}
                ({self.TableCols.Guild}, {self.TableCols.Channel}, {self.TableCols.Member},
                 {self.TableCols.Account}, {self.TableCols.Role},
                 {self.TableCols.Timestamp}, {self.TableCols.GuildName},
                 {self.TableCols.MemberUsername}, {self.TableCols.MemberDisplayName},
                 {self.TableCols.RoleName})
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?, ?)
                """,
                (
                    guild.id,
                    channel_id,
                    member,
                    account,
                    role,
                    guild.name,
                    member_names[0] if member_names is not None else None,
                    member_names[1] if member_names is not None else None,
                    role_name,
                ),
            )
            if not executed:
                return False
            _logger.info(
                f"{self.log_prefix(guild)} Added WZ registration for member {member_name}."
            )
            return True
        except Exception as e:
            _logger.exception(
                f"{self.log_prefix(guild)} Failed to add WZ registration for "
                f"member {member_name}: {e}"
            )
            return False

    async def remove(
        self,
        *,
        guild: discord.Guild,
        member: int | None = None,
        account: str | None = None,
        role: int | None = None,
        roles: list[int] | None = None,
        channel_id: int | None = None,
    ) -> bool:
        target = "registrations"
        try:
            if member is not None and (role is not None or roles):
                raise ValueError("Cannot combine member with role or roles filters.")
            if account is not None and (member is None or role is not None or roles):
                raise ValueError("Account filters require a member filter only.")
            if role is not None and roles:
                raise ValueError("Cannot provide both role and roles filters.")

            query = f"DELETE FROM {self.table_name} WHERE {self.TableCols.Guild} = ?"
            params: list[typing.Any] = [guild.id]
            if channel_id is not None:
                query += f" AND {self.TableCols.Channel} = ?"
                params.append(channel_id)

            if member is not None:
                query += f" AND {self.TableCols.Member} = ?"
                params.append(member)
                if account is not None:
                    query += f" AND {self.TableCols.Account} = ?"
                    params.append(account)
                target = f"member {await self.member_log_name(guild, member)}"
            elif role is not None:
                query += f" AND {self.TableCols.Role} = ?"
                params.append(role)
                target = f"role {await self.role_log_name(guild, role)}"
            elif roles:
                placeholders = ",".join("?" for _ in roles)
                query += f" AND {self.TableCols.Role} IN ({placeholders})"
                params.extend(roles)
                target = "roles " + str(
                    [await self.role_log_name(guild, role_id) for role_id in roles]
                )
            else:
                target = "all registrations"

            executed = await self.database.execute(query, tuple(params))
            if executed:
                _logger.debug(f"{self.log_prefix(guild)} Removed WZ {target}.")
            return executed
        except Exception as e:
            _logger.exception(
                f"{self.log_prefix(guild)} Failed to remove WZ {target}: {e}"
            )
            return False

    async def remove_member_role(
        self,
        *,
        guild: discord.Guild,
        member: int,
        role: int,
        channel_id: int | None = None,
    ) -> bool:
        """Remove registrations for one member and one role across their accounts."""
        try:
            return await self.database.execute(
                f"""
                DELETE FROM {self.table_name}
                WHERE {self.TableCols.Guild} = ?
                  AND {self.TableCols.Member} = ?
                  AND {self.TableCols.Role} = ?
                  AND (? IS NULL OR {self.TableCols.Channel} = ?)
                """,
                (guild.id, member, role, channel_id, channel_id),
            )
        except Exception:
            _logger.exception(
                "%s Failed to remove role %s registrations for member %s.",
                self.log_prefix(guild),
                role,
                member,
            )
            return False
