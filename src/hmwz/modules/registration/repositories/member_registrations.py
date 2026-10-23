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

    table_name = "Registration_Members"
    legacy_table_name: str | None = "Registrations_Member"
    settings_table_name = "Registration_Settings"

    def __init__(self, database: sqlite_db.Database):
        super().__init__(database)

    @dataclass(frozen=True)
    class TableCols:
        Guild: str = "Guild"
        Channel: str = "Channel"
        Member: str = "Member"
        Account: str = "Alias"
        Role: str = "Role"
        Timestamp: str = "Timestamp"
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
            {self.TableCols.MemberUsername} TEXT,
            {self.TableCols.MemberDisplayName} TEXT,
            {self.TableCols.RoleName} TEXT,
            PRIMARY KEY (
                {self.TableCols.Guild}, {self.TableCols.Channel},
                {self.TableCols.Member}, {self.TableCols.Account}
            )
        ) WITHOUT ROWID
        """

    async def migrate_schema(self) -> bool:
        """Migrate legacy registration records while preserving alternate accounts."""
        if not await self.ensure_columns(
            (
                (self.TableCols.Channel, "INTEGER NOT NULL DEFAULT 0"),
                (self.TableCols.MemberUsername, "TEXT"),
                (self.TableCols.MemberDisplayName, "TEXT"),
                (self.TableCols.RoleName, "TEXT"),
            )
        ):
            return False
        if not await self._migrate_account_key():
            return False
        if not await self._migrate_legacy_table():
            return False
        return await self.drop_columns(("GuildName",))

    async def _migrate_account_key(self) -> bool:
        """Move legacy registrations to a key that supports multiple accounts."""
        try:
            async with self.database.connect() as connection:
                await connection.execute("BEGIN IMMEDIATE")
                cursor = await connection.execute(
                    f'PRAGMA table_info("{self.table_name}")'
                )
                columns = await cursor.fetchall()
                column_names = {column["name"] for column in columns}
                primary_key = {column["name"] for column in columns if column["pk"] > 0}
                alias_column = (
                    "Alias"
                    if "Alias" in column_names
                    else "Account"
                    if "Account" in column_names
                    else None
                )
                if {"Guild", "Channel", "Member", "Alias"}.issubset(
                    primary_key
                ) and "Account" not in column_names:
                    await connection.commit()
                    return True

                account_value = (
                    f"COALESCE(legacy.\"{alias_column}\", '')"
                    if alias_column is not None
                    else "''"
                )
                if "Channel" in primary_key:
                    channel_value = 'COALESCE(legacy."Channel", 0)'
                else:
                    stored_channel = (
                        'NULLIF(legacy."Channel", 0)'
                        if "Channel" in column_names
                        else "NULL"
                    )
                    channel_value = f"""COALESCE(
                            {stored_channel},
                            (SELECT Channel FROM "{self.settings_table_name}"
                             WHERE Guild = legacy.Guild
                             ORDER BY Channel LIMIT 1),
                            0
                        )
                    """
                role_value = 'legacy."Role"' if "Role" in column_names else "NULL"
                timestamp_value = (
                    'legacy."Timestamp"'
                    if "Timestamp" in column_names
                    else "CURRENT_TIMESTAMP"
                )
                member_username_value = (
                    'legacy."MemberUsername"'
                    if "MemberUsername" in column_names
                    else "NULL"
                )
                member_display_name_value = (
                    'legacy."MemberDisplayName"'
                    if "MemberDisplayName" in column_names
                    else "NULL"
                )
                role_name_value = (
                    'legacy."RoleName"' if "RoleName" in column_names else "NULL"
                )
                await connection.execute(
                    f"""
                    CREATE TABLE "{self.table_name}_new" (
                        Guild INTEGER,
                        Channel INTEGER NOT NULL DEFAULT 0,
                        Member INTEGER,
                        Alias TEXT NOT NULL DEFAULT '',
                        Role INTEGER,
                        Timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                        MemberUsername TEXT,
                        MemberDisplayName TEXT,
                        RoleName TEXT,
                        PRIMARY KEY (Guild, Channel, Member, Alias)
                    ) WITHOUT ROWID
                    """
                )
                await connection.execute(
                    f"""
                    INSERT OR IGNORE INTO "{self.table_name}_new"
                    (Guild, Channel, Member, Alias, Role, Timestamp,
                     MemberUsername, MemberDisplayName, RoleName)
                    SELECT legacy."Guild", {channel_value}, legacy."Member",
                           {account_value}, {role_value}, {timestamp_value},
                           {member_username_value}, {member_display_name_value},
                           {role_name_value}
                    FROM "{self.table_name}" AS legacy
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

    async def _migrate_legacy_table(self) -> bool:
        """Copy registrations from the former table name before removing it."""
        if self.legacy_table_name is None:
            return True

        try:
            legacy_table = await self.database.fetch_one(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                (self.legacy_table_name,),
            )
            if legacy_table is None:
                return True

            async with self.database.connect() as connection:
                await connection.execute("BEGIN IMMEDIATE")
                cursor = await connection.execute(
                    f'PRAGMA table_info("{self.legacy_table_name}")'
                )
                columns = await cursor.fetchall()
                column_names = {column["name"] for column in columns}
                primary_key = {column["name"] for column in columns if column["pk"] > 0}
                alias_column = (
                    "Alias"
                    if "Alias" in column_names
                    else "Account"
                    if "Account" in column_names
                    else None
                )
                alias_value = (
                    f"COALESCE(legacy.\"{alias_column}\", '')"
                    if alias_column is not None
                    else "''"
                )
                if "Channel" in primary_key:
                    channel_value = 'COALESCE(legacy."Channel", 0)'
                else:
                    stored_channel = (
                        'NULLIF(legacy."Channel", 0)'
                        if "Channel" in column_names
                        else "NULL"
                    )
                    channel_value = f"""COALESCE(
                        {stored_channel},
                        (SELECT Channel FROM "{self.settings_table_name}"
                         WHERE Guild = legacy.Guild
                         ORDER BY Channel LIMIT 1),
                        0
                    )"""
                role_value = 'legacy."Role"' if "Role" in column_names else "NULL"
                timestamp_value = (
                    'legacy."Timestamp"'
                    if "Timestamp" in column_names
                    else "CURRENT_TIMESTAMP"
                )
                member_username_value = (
                    'legacy."MemberUsername"'
                    if "MemberUsername" in column_names
                    else "NULL"
                )
                member_display_name_value = (
                    'legacy."MemberDisplayName"'
                    if "MemberDisplayName" in column_names
                    else "NULL"
                )
                role_name_value = (
                    'legacy."RoleName"' if "RoleName" in column_names else "NULL"
                )
                await connection.execute(
                    f"""
                    INSERT OR IGNORE INTO "{self.table_name}"
                        (Guild, Channel, Member, Alias, Role, Timestamp,
                         MemberUsername, MemberDisplayName, RoleName)
                    SELECT legacy."Guild", {channel_value}, legacy."Member",
                           {alias_value}, {role_value}, {timestamp_value},
                           {member_username_value}, {member_display_name_value},
                           {role_name_value}
                    FROM "{self.legacy_table_name}" AS legacy
                    """
                )
                await connection.execute(f'DROP TABLE "{self.legacy_table_name}"')
                await connection.commit()
            return True
        except Exception:
            _logger.exception(
                "%s Failed to migrate registrations from legacy table %s.",
                self.log_prefix(),
                self.legacy_table_name,
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
        member_username: str | None
        member_display_name: str | None
        role_name: str | None

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
                    member_username=rec[self.TableCols.MemberUsername],
                    member_display_name=rec[self.TableCols.MemberDisplayName],
                    role_name=rec[self.TableCols.RoleName],
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
        member_username: str | None = None,
        member_display_name: str | None = None,
        role_name: str | None = None,
    ) -> bool:
        member_name = f"unknown member ({member})"
        try:
            member_names = await self.member_names(guild, member)
            if member_names is not None:
                member_name = f"{member_names[0]} / {member_names[1]} ({member})"
            executed = await self.database.execute(
                f"""
                INSERT OR REPLACE INTO {self.table_name}
                ({self.TableCols.Guild}, {self.TableCols.Channel}, {self.TableCols.Member},
                 {self.TableCols.Account}, {self.TableCols.Role},
                 {self.TableCols.Timestamp}, {self.TableCols.MemberUsername},
                 {self.TableCols.MemberDisplayName}, {self.TableCols.RoleName})
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?)
                """,
                (
                    guild.id,
                    channel_id,
                    member,
                    account,
                    role,
                    member_username,
                    member_display_name,
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
