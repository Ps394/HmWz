"""Persistence for roles available in registration channels."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import discord

from hmwz import sqlite_db

_logger = logging.getLogger(__name__)


class RegistrationRoleRepository(sqlite_db.Base):
    """Store registration role settings for guild channels."""

    table_name = "Registration_Roles"
    legacy_table_name = "Roles"
    settings_table_name = "Registration_Settings"

    def __init__(self, database: sqlite_db.Database):
        super().__init__(database)

    @dataclass(frozen=True)
    class TableCols:
        """Column names used by the registration role table."""

        Guild: str = "Guild"
        Channel: str = "Channel"
        Role: str = "Role"
        Permanent: str = "Permanent"
        Score: str = "Score"

    @property
    def table(self) -> str:
        """
        Return the SQL statement that creates the registration role table.
        """
        return f"""
        CREATE TABLE IF NOT EXISTS {self.table_name}(
        {self.TableCols.Guild} INTEGER NOT NULL,
        {self.TableCols.Channel} INTEGER NOT NULL DEFAULT 0,
        {self.TableCols.Role} INTEGER NOT NULL,
        {self.TableCols.Permanent} BOOLEAN,
        {self.TableCols.Score} INTEGER DEFAULT 1,
        PRIMARY KEY ({self.TableCols.Guild}, {self.TableCols.Role})
        )WITHOUT ROWID
        """

    async def migrate_schema(self) -> bool:
        """Add channel scope to legacy role records and remove cached names."""
        if not await self.ensure_columns(
            ((self.TableCols.Channel, "INTEGER NOT NULL DEFAULT 0"),)
        ):
            return False
        if not await self._migrate_legacy_table():
            return False
        if not await self.database.execute(
            f"""
            UPDATE {self.table_name}
            SET {self.TableCols.Channel} = COALESCE(
                (SELECT Channel FROM {self.settings_table_name}
                 WHERE Guild = {self.table_name}.Guild
                 ORDER BY Channel LIMIT 1),
                0
            )
            WHERE {self.TableCols.Channel} = 0
            """
        ):
            return False
        return await self.drop_columns(("GuildName", "RoleName"))

    async def _migrate_legacy_table(self) -> bool:
        """Move role assignments from the former ``Roles`` table."""
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
                channel_value = (
                    f"""
                    COALESCE(
                        NULLIF(legacy."{self.TableCols.Channel}", 0),
                        (SELECT Channel FROM "{self.settings_table_name}"
                         WHERE Guild = legacy."{self.TableCols.Guild}"
                         ORDER BY Channel LIMIT 1),
                        0
                    )
                    """
                    if self.TableCols.Channel in column_names
                    else f"""
                    COALESCE(
                        (SELECT Channel FROM "{self.settings_table_name}"
                         WHERE Guild = legacy."{self.TableCols.Guild}"
                         ORDER BY Channel LIMIT 1),
                        0
                    )
                    """
                )
                permanent_value = (
                    f'legacy."{self.TableCols.Permanent}"'
                    if self.TableCols.Permanent in column_names
                    else "0"
                )
                score_value = (
                    f'legacy."{self.TableCols.Score}"'
                    if self.TableCols.Score in column_names
                    else "1"
                )
                await connection.execute(
                    f"""
                    INSERT OR IGNORE INTO "{self.table_name}"
                        (Guild, Channel, Role, Permanent, Score)
                    SELECT legacy."{self.TableCols.Guild}", {channel_value},
                           legacy."{self.TableCols.Role}", {permanent_value},
                           {score_value}
                    FROM "{self.legacy_table_name}" AS legacy
                    """
                )
                await connection.execute(f'DROP TABLE "{self.legacy_table_name}"')
                await connection.commit()
            return True
        except Exception:
            _logger.exception(
                "%s Failed to migrate role assignments from %s.",
                self.log_prefix(),
                self.legacy_table_name,
            )
            return False

    @dataclass(frozen=True)
    class _Data:
        guild_id: int
        role: int
        permanent: bool
        score: int
        channel_id: int = 0

    type Record = _Data | None
    """A registration role record, or ``None`` when no record exists."""

    type Records = tuple[_Data, ...] | None
    """A tuple of registration role records, or ``None`` when none are found."""

    async def count(
        self,
        *,
        guild: discord.Guild,
        permanent: bool | None = None,
        roles: list[int] | None = None,
        channel_id: int | None = None,
    ) -> int:
        """
        Count registration roles matching the supplied filters.

        Args:
            guild: Guild whose roles should be counted.
            permanent: Optional permanence filter.
            roles: Optional role identifiers to count.
            channel_id: Optional channel identifier to filter by.

        Returns:
            Number of matching roles, or zero if the query fails.

        Conflicting ``permanent`` and ``roles`` filters are rejected and logged.
        """
        try:
            if permanent is not None and roles:
                raise ValueError("Cannot provide both permanent and roles filters.")

            query = f"SELECT COUNT(*) FROM {self.table_name} WHERE {self.TableCols.Guild} = ?"
            params = [guild.id]
            if channel_id is not None:
                query += f" AND {self.TableCols.Channel} = ?"
                params.append(channel_id)

            if permanent is not None:
                query += f" AND {self.TableCols.Permanent} = ?"
                params.append(int(permanent))
            elif roles:
                placeholders = ",".join("?" for _ in roles)
                query += f" AND {self.TableCols.Role} IN ({placeholders})"
                params.extend(roles)

            row = await self.database.fetch_one(query, tuple(params))
            _logger.debug(f"{self.log_prefix(guild)} WZ registration roles counted.")
            return row[0] if row else 0
        except Exception as e:
            _logger.exception(
                f"{self.log_prefix(guild)} Failed to count WZ registration roles: {e}"
            )
            return 0

    async def get(
        self,
        *,
        guild: discord.Guild,
        permanent: bool | None = None,
        channel_id: int | None = None,
    ) -> Records:
        """
        Retrieve registration roles matching the supplied filters.

        Args:
            guild: Guild whose roles should be retrieved.
            permanent: Optional permanence filter.
            channel_id: Optional channel identifier to filter by.

        Returns:
            Matching role records, or ``None`` if none are found or the query fails.
        """
        try:
            query = f"SELECT {self.TableCols.Channel}, {self.TableCols.Role}, {self.TableCols.Permanent}, {self.TableCols.Score} FROM {self.table_name} WHERE {self.TableCols.Guild} = ?"
            params = [guild.id]
            if channel_id is not None:
                query += f" AND {self.TableCols.Channel} = ?"
                params.append(channel_id)

            if permanent is not None:
                query += f" AND {self.TableCols.Permanent} = ?"
                params.append(int(permanent))

            records = await self.database.fetch_all(query, tuple(params))
            if not records:
                return None

            async def resolve_records(rec):
                """
                Convert a database row to a registration role record.
                """
                return self._Data(
                    guild_id=guild.id,
                    role=rec[self.TableCols.Role],
                    permanent=bool(rec[self.TableCols.Permanent]),
                    score=rec[self.TableCols.Score],
                    channel_id=rec[self.TableCols.Channel],
                )

            out: list[RegistrationRoleRepository._Data] = await asyncio.gather(
                *(resolve_records(rec) for rec in records)
            )
            return tuple(out) if out else None
        except Exception as e:
            _logger.exception(
                f"{self.log_prefix(guild)} Failed to get WZ registration roles: {e}"
            )
            return None

    async def add(
        self,
        *,
        guild: discord.Guild,
        role: int,
        permanent: bool | None = False,
        score: int | None = 1,
        channel_id: int = 0,
    ) -> bool:
        """
        Insert or update a registration role for a guild channel.

        Args:
            guild: Guild that owns the registration role.
            role: Discord role identifier.
            permanent: Whether the role is permanent.
            score: Score associated with the role.
            channel_id: Registration channel identifier.

        Returns:
            Whether the database write succeeded.
        """
        role_name = f"unknown role ({role})"
        try:
            resolved_role_name = await self.role_name(guild, role)
            role_name = (
                f"{resolved_role_name} ({role})"
                if resolved_role_name is not None
                else role_name
            )
            executed = await self.database.execute(
                f"""
                INSERT INTO {self.table_name}
                    (Guild, Channel, Role, Permanent, Score)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(Guild, Role) DO UPDATE SET
                    Permanent = excluded.Permanent,
                    Score = excluded.Score
                WHERE {self.table_name}.Channel = excluded.Channel
                """,
                (
                    guild.id,
                    channel_id,
                    role,
                    int(permanent is True),
                    score,
                ),
            )
            if not executed:
                return False
            saved_role = await self.database.fetch_one(
                f"SELECT Channel FROM {self.table_name} WHERE Guild = ? AND Role = ?",
                (guild.id, role),
            )
            if saved_role is None or saved_role[self.TableCols.Channel] != channel_id:
                return False
            _logger.debug(
                f"{self.log_prefix(guild)} Added WZ registration role {role_name}."
            )
            return True
        except Exception as e:
            _logger.exception(
                f"{self.log_prefix(guild)} Failed to add WZ registration role "
                f"{role_name}: {e}"
            )
            return False

    async def remove(
        self,
        *,
        guild: discord.Guild,
        role: int | None = None,
        roles: list[int] | None = None,
        channel_id: int | None = None,
    ) -> bool:
        """
        Remove registration roles matching the supplied filters.

        Args:
            guild: Guild whose roles should be removed.
            role: Optional role identifier to remove.
            roles: Optional role identifiers to remove.
            channel_id: Optional channel identifier to filter by.

        Returns:
            Whether the database operation succeeded.

        Conflicting ``role`` and ``roles`` filters are rejected and logged.
        """
        target = "roles"
        try:
            role_names = (
                [await self.role_log_name(guild, role)]
                if role is not None
                else [
                    await self.role_log_name(guild, role_id) for role_id in roles or ()
                ]
            )
            if role and roles:
                raise ValueError("Cannot provide both role and roles filters.")
            query = f"DELETE FROM {self.table_name} WHERE Guild = ?"
            params = [guild.id]
            if channel_id is not None:
                query += " AND Channel = ?"
                params.append(channel_id)
            if role:
                query += " AND Role = ?"
                params.append(role)
                target = f"role {role_names[0]}"
            elif roles:
                placeholders = ",".join("?" for _ in roles)
                query += f" AND Role IN ({placeholders})"
                params.extend(roles)
                target = f"roles {role_names}"
            else:
                target = "all roles"
            executed = await self.database.execute(query, tuple(params))
            if executed:
                _logger.debug(
                    f"{self.log_prefix(guild)} Removed WZ registration role {target}."
                )
            return executed
        except Exception as e:
            _logger.exception(
                f"{self.log_prefix(guild)} Failed to remove WZ registration role {target}: {e}"
            )
            return False
