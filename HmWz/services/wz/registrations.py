from __future__ import annotations
import datetime
import asyncio
import logging

from ..database import Database
from ..base import Base
from .roles import WzRoles

from ...types import dataclass, Optional, Tuple, Id, Ids, Guild

class WzRegistrations(Base):
    """
    Die WzRegistrations-Klasse verwaltet die Registrierungsinformationen für die WZ-Funktionalität eines Discord-Servers (Guild). 
    Sie ermöglicht das Hinzufügen, Abrufen und Entfernen von Registrierungen, die aus einem Mitglied und einer zugehörigen Rolle bestehen. 
    """
    def __init__(self, database: Database):
        super().__init__(database)
        self.roles_service = WzRoles(database)
        self.logger = logging.getLogger(__name__)

    @dataclass(frozen=True)
    class TableCols:
        Guild: str = "Guild"
        Member: str = "Member"
        Role: str = "Role"
        Timestamp: str = "Timestamp"

    @property
    def table(self) -> str:
        return f"""
        CREATE TABLE IF NOT EXISTS {self.table_name}(
            {self.TableCols.Guild} INTEGER,
            {self.TableCols.Member} INTEGER,
            {self.TableCols.Role} INTEGER,
            {self.TableCols.Timestamp} TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY ({self.TableCols.Guild}, {self.TableCols.Member})
        )WITHOUT ROWID
        """

    @dataclass(frozen=True)
    class Data:
        guild: Guild
        member: Optional[Id]
        role: Optional[Id]
        timestamp: str

        @property
        def has_member(self) -> bool:
            return self.member is not None
        @property
        def has_role(self) -> bool:
            return self.role is not None

    type Record = Optional[Data]
    """
    Basisdatentyp für eine Wz-Registrierung, bestehend aus einem Guild, einem Member, einer Role und einem Timestamp.
    
    :param guild: Das Guild-Objekt, für das die Registrierung gilt.
    :type guild: discord.Guild
    :param member: Die ID des registrierten Mitglieds.
    :type member: Optional[int]
    :param role: Die ID der mit der Registrierung verknüpften Rolle.
    :type role: Optional[int]
    :type role: DiscordRole
    :param timestamp: Der Zeitstempel der Registrierung.
    :type timestamp: str
    """
    type Records = Optional[Tuple[Data, ...]]
    """
    Der Datentyp für die WZ-Registrierungsinformationen einer Guild. Er kann entweder ein einzelner Record oder ein Tuple von Records sein, oder None, wenn keine Registrierungen vorhanden sind.
    """
    
    async def count(self, *, guild: Guild, role: Optional[Id]=None, roles: Optional[Ids]=None) -> int:
        """
        Zählt die Anzahl der WZ-Registrierungen in einem Guild, optional gefiltert nach einer bestimmten Rolle oder einer Liste von Rollen.

        :param guild: Das Guild-Objekt, für das die Anzahl der Registrierungen gezählt werden soll.
        :type guild: discord.Guild
        :param role: Optionaler Filter, um nur Registrierungen mit einer bestimmten Rolle zu zählen.
        :type role: Optional[int]
        :param roles: Optionaler Filter, um nur Registrierungen mit bestimmten Rollen zu zählen.
        :type roles: Optional[tuple[int, ...]]
        :return: Die Anzahl der WZ-Registrierungen, die den angegebenen Filtern entsprechen.
        :rtype: int
        :raises ValueError: Wenn sowohl role als auch roles Filter gleichzeitig angegeben werden.
        """
        try:
            if role and roles:
                raise ValueError("Cannot provide both role and roles filters.")
          
            query = f"""
            SELECT 
                COUNT(*) 
            FROM 
                {self.table_name} 
            WHERE 
                {self.TableCols.Guild} = ?
            """

            params = [guild.id]
            if role:
                query += f" AND {self.TableCols.Role} = ?"
                params.append(role)
            elif roles:
                placeholders = ','.join('?' for _ in roles)
                query += f" AND {self.TableCols.Role} IN ({placeholders})"
                params.extend(roles)
            
            row = await self.database.fetch_one(query, params)
            self.logger.info(f"{self.log_prefix(guild)} Counted WZ registrations with filters role={role}, roles={roles}: {row[0] if row else 0}")
            return row[0] if row else 0
        except Exception as e:
            self.logger.exception(f"{self.log_prefix(guild)} Failed to count WZ registrations: {e}")
            return 0

    async def get(self, *, guild: Guild, member: Optional[Id]=None, role: Optional[Id]=None, roles: Optional[Ids]=None) -> Records:
        """
        Ruht die WZ-Registrierungsinformationen für eine bestimmte Gilde ab, optional gefiltert nach Mitglied oder Rolle(n).
        Stale Einträge (d.h. solche, deren Mitglied oder Rolle nicht mehr existiert) werden automatisch bereinigt.

        :param guild: Das Guild-Objekt, für das die Informationen abgerufen werden sollen.
        :type guild: discord.Guild
        :param member: Optionaler Filter, um die Registrierung eines bestimmten Mitglieds abzurufen
        :type member: Optional[int]
        :param role: Optionaler Filter, um Registrierungen mit einer bestimmten Rolle abzurufen
        :type role: Optional[int]
        :param roles: Optionaler Filter, um Registrierungen mit bestimmten Rollen abzurufen
        :type roles: Optional[tuple[int, ...]]  
        :return: Die WZ-Registrierungsinformationen, die den angegebenen Filtern entsprechen.
        :rtype: Union[Records, Record]
        :raises ValueError: Wenn sowohl member als auch role/roles Filter gleichzeitig angegeben werden.
        """
        try:
            if member and (role or roles):
                raise ValueError("Cannot combine member with role or roles filters.")
            if role and roles:
                raise ValueError("Cannot provide both role and roles filters.")
            
            query = f"SELECT * FROM {self.table_name} WHERE {self.TableCols.Guild} = ?"
            params = [guild.id]
            if member:
                query += f" AND {self.TableCols.Member} = ?"
                params.append(member)
            elif roles:
                placeholders = ','.join('?' for _ in roles)
                query += f" AND {self.TableCols.Role} IN ({placeholders})"
                params.extend(roles)
            elif role:
                query += f" AND {self.TableCols.Role} = ?"
                params.append(role)

            records = await self.database.fetch_all(query, tuple(params))
            if not records:
                return None
            
            async def resolve_records(rec):
                return self.Data(
                    guild=guild,
                    member=rec[self.TableCols.Member],
                    role=rec[self.TableCols.Role],
                    timestamp=rec[self.TableCols.Timestamp]
                )

            out = []
            out : WzRegistrations.Records = await asyncio.gather(*(resolve_records(rec) for rec in records))

            return out if out else None
        except Exception as e:
            self.logger.exception(f"{self.log_prefix(guild)} Failed to get WZ registrations: {e}")
            return None

    async def add(self, *, guild: Guild, member: Id, role: Id) -> bool:
        """
        Fügt eine neue WZ-Registrierung für ein Mitglied mit einer zugehörigen Rolle hinzu oder aktualisiert sie.

        :param guild: Das Guild-Objekt, für das die Registrierung hinzugefügt werden soll.
        :type guild: discord.Guild
        :param member: Die ID des Mitglieds, das registriert werden soll.
        :type member: int
        :param role: Die ID der Rolle, die mit der Registrierung verknüpft werden soll.
        :type role: int
        :return: True, wenn die Registrierung erfolgreich hinzugefügt oder aktualisiert wurde, False sonst.
        :rtype: bool
        """
        try:
            timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
            query = f"""INSERT OR REPLACE INTO {self.table_name} ({self.TableCols.Guild}, {self.TableCols.Member}, {self.TableCols.Role}, {self.TableCols.Timestamp}) VALUES (?, ?, ?, ?)"""
            params = (guild.id, member, role, timestamp)
            await self.database.execute(query, params)
            return True    
        except Exception as e:
            self.logger.exception(f"{self.log_prefix(guild)} Failed to add WZ registration for member {member}: {e}")
            return False

    async def remove(self, *, guild: Guild, member: Optional[Id]=None, role: Optional[Id]=None, roles: Optional[Ids]=None, members: Optional[Ids]=None) -> bool:
        """
        Entfernt WZ-Registrierungen basierend auf den angegebenen Filtern.

        :param guild: Das Guild-Objekt, für das die Registrierung entfernt werden soll.
        :type guild: discord.Guild
        :param member: Die ID des Mitglieds, dessen Registrierung entfernt werden soll.
        :type member: int
        :param role: Die ID der Rolle, deren Registrierung entfernt werden soll.
        :type role: int
        :param roles: Eine Liste von Rollen-IDs, deren Registrierungen entfernt werden sollen.
        :type roles: list[int]
        :param members: Eine Liste von Mitglieder-IDs, deren Registrierungen entfernt werden sollen.
        :type members: list[int]
        :return: True, wenn die Registrierung erfolgreich entfernt wurde, False sonst.
        :rtype: bool
        :raises ValueError: Wenn ungültige Kombinationen von Filtern bereitgestellt werden (z.B. sowohl member als auch members).
        """
        try:
            args = [member, role, roles, members]
            if sum(arg is not None for arg in args) > 1:
                raise ValueError("Cannot combine multiple filters. Provide only one of member, role, roles, or members.")

            roles = tuple(roles) if roles else None
            members = tuple(members) if members else None
            query = f"DELETE FROM {self.table_name} WHERE {self.TableCols.Guild} = ?"
            params = [guild.id]

            if member:
                query += f" AND {self.TableCols.Member} = ?"
                params.append(member)
            elif roles:
                placeholders = ','.join('?' for _ in roles)
                query += f" AND {self.TableCols.Role} IN ({placeholders})"
                params.extend(roles)
            elif role:
                query += f" AND {self.TableCols.Role} = ?"
                params.append(role)
            elif members:
                placeholders = ','.join('?' for _ in members)
                query += f" AND {self.TableCols.Member} IN ({placeholders})"
                params.extend(members)
            await self.database.execute(query, tuple(params))
            return True
        except Exception as e:
            self.logger.exception(f"{self.log_prefix(guild)} Failed to remove WZ registrations: {e}")
            return False
