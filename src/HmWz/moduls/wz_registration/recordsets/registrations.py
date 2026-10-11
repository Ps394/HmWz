from __future__ import annotations

import asyncio
import logging
import typing
from dataclasses import dataclass

import discord
import sqlLiteDB

_logger = logging.getLogger(__name__)


class WzRegistrations(sqlLiteDB.Base):
    """Recordset fuer Mitgliederregistrierungen je Guild."""

    def __init__(self, database: sqlLiteDB.Database):
        super().__init__(database)

    @dataclass(frozen=True)
    class TableCols:
        Guild: str = "Guild"
        Member: str = "Member"
        Role: str = "Role"
        Timestamp: str = "Timestamp"

    @property
    def table(self) -> str:
        return f"""
        CREATE TABLE IF NOT EXISTS {self.table_name} (
            {self.TableCols.Guild} INTEGER,
            {self.TableCols.Member} INTEGER,
            {self.TableCols.Role} INTEGER,
            {self.TableCols.Timestamp} TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY ({self.TableCols.Guild}, {self.TableCols.Member})
        ) WITHOUT ROWID
        """

    @dataclass(frozen=True)
    class _Data:
        guild_id: int
        member: int | None
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
    ) -> int:
        try:
            if role is not None and roles:
                raise ValueError("Cannot provide both role and roles filters.")

            query = f"SELECT COUNT(*) FROM {self.table_name} WHERE {self.TableCols.Guild} = ?"
            params: list[typing.Any] = [guild.id]

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
            _logger.exception(f"{self.log_prefix(guild)} Failed to count WZ registrations: {e}")
            return 0

    async def get(
        self,
        *,
        guild: discord.Guild,
        member: int | None = None,
        role: int | None = None,
        roles: list[int] | None = None,
    ) -> Records:
        try:
            if member is not None and (role is not None or roles):
                raise ValueError("Cannot combine member with role or roles filters.")
            if role is not None and roles:
                raise ValueError("Cannot provide both role and roles filters.")

            query = f"SELECT * FROM {self.table_name} WHERE {self.TableCols.Guild} = ?"
            params: list[typing.Any] = [guild.id]

            if member is not None:
                query += f" AND {self.TableCols.Member} = ?"
                params.append(member)
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

            async def resolve_record(rec: typing.Any) -> WzRegistrations._Data:
                return self._Data(
                    guild_id=guild.id,
                    member=rec[self.TableCols.Member],
                    role=rec[self.TableCols.Role],
                    timestamp=rec[self.TableCols.Timestamp],
                )

            out: list[WzRegistrations._Data] = await asyncio.gather(*(resolve_record(rec) for rec in records))
            return tuple(out) if out else None
        except Exception as e:
            _logger.exception(f"{self.log_prefix(guild)} Failed to get WZ registrations: {e}")
            return None

    async def add(self, *, guild: discord.Guild, member: int, role: int) -> bool:
        try:
            await self.database.execute(
                f"""
                INSERT OR REPLACE INTO {self.table_name}
                ({self.TableCols.Guild}, {self.TableCols.Member}, {self.TableCols.Role}, {self.TableCols.Timestamp})
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (guild.id, member, role),
            )
            _logger.info(f"{self.log_prefix(guild)} Added WZ registration for member {member}.")
            return True
        except Exception as e:
            _logger.exception(f"{self.log_prefix(guild)} Failed to add WZ registration for member {member}: {e}")
            return False

    async def remove(
        self,
        *,
        guild: discord.Guild,
        member: int | None = None,
        role: int | None = None,
        roles: list[int] | None = None,
    ) -> bool:
        target = "registrations"
        try:
            if member is not None and (role is not None or roles):
                raise ValueError("Cannot combine member with role or roles filters.")
            if role is not None and roles:
                raise ValueError("Cannot provide both role and roles filters.")

            query = f"DELETE FROM {self.table_name} WHERE {self.TableCols.Guild} = ?"
            params: list[typing.Any] = [guild.id]

            if member is not None:
                query += f" AND {self.TableCols.Member} = ?"
                params.append(member)
                target = f"member {member}"
            elif role is not None:
                query += f" AND {self.TableCols.Role} = ?"
                params.append(role)
                target = f"role {role}"
            elif roles:
                placeholders = ",".join("?" for _ in roles)
                query += f" AND {self.TableCols.Role} IN ({placeholders})"
                params.extend(roles)
                target = f"roles {roles}"
            else:
                target = "all registrations"

            await self.database.execute(query, tuple(params))
            _logger.info(f"{self.log_prefix(guild)} Removed WZ {target}.")
            return True
        except Exception as e:
            _logger.exception(f"{self.log_prefix(guild)} Failed to remove WZ {target}: {e}")
            return False
