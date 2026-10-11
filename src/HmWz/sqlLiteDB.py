from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import cast

import aiosqlite
from discord import Guild

_logger = logging.getLogger(__name__)


class Base:
    """
    Basisklasse für alle Services, die Zugriff auf die Datenbank benötigen. Diese Klasse bietet grundlegende Funktionen wie das Abrufen des Tabellennamens, Logging und das Zählen von Einträgen in der Tabelle.
    Alle Services, die von dieser Klasse erben, müssen die TABLE-Eigenschaft implementieren, um die SQL-Abfrage zum Erstellen der entsprechenden Tabelle bereitzustellen.

    :param database: Eine Instanz der Database-Klasse, die für den Zugriff auf die Datenbank verwendet wird.
    :type database: Database
    :param table_name: Gibt den Namen der Tabelle zurück, die von diesem Service verwendet wird. Standardmäßig ist dies der Name der Klasse.
    :type table_name: str
    :param logger: Gibt einen Logger zurück, der für das Logging in diesem Service verwendet wird.
    :type logger: logging.Logger
    :param log_prefix: Gibt einen Log-Prefix zurück, der den Namen und die ID des Guilds enthält, wenn ein Guild-Objekt übergeben wird. Andernfalls ist der Prefix leer.
    :type log_prefix: str

    :raises NotImplementedError: Wenn die TABLE-Eigenschaft nicht von einer Unterklasse implementiert wird.
    """

    def __init__(self, database: Database):
        self.database: Database = database

    @property
    def table_name(self) -> str:
        """Gibt den Namen der Tabelle zurück, die von diesem Service verwendet wird. Standardmäßig ist dies der Name der Klasse.

        :return: Der Name der Tabelle als String.
        :rtype: str
        """
        return self.__class__.__name__

    @classmethod
    def log_prefix(cls, guild: Guild | None = None) -> str:
        """
        Gibt einen Log-Prefix zurück, der den Namen und die ID des Guilds enthält, wenn ein Guild-Objekt übergeben wird. Andernfalls ist der Prefix leer.

        :param guild: Ein optionales Guild-Objekt, für das der Log-Prefix generiert werden soll.
        :type guild: Optional[Guild]

        :return: Ein Log-Prefix als String.
        :rtype: str
        """
        if guild:
            return f"{guild.name} ({guild.id}) - "
        return ""

    @property
    def table(self) -> str:
        """Gibt die SQL-Abfrage zurück, um die Tabelle für diesen Service zu erstellen. Diese Eigenschaft muss von Unterklassen implementiert werden, um die spezifische SQL-Abfrage für die jeweilige Tabelle bereitzustellen."""
        raise NotImplementedError('Subclasses must implement the "table" property.')

    async def count_all(self) -> int:
        try:
            query = f"SELECT COUNT(*) FROM {self.table_name}"
            row = await self.database.fetch_one(query)
            _logger.info(f"{self.log_prefix()}Counted entries in {self.table_name} table.")
            return row[0] if row else 0
        except Exception as e:
            _logger.exception(f"{self.log_prefix()}Failed to count entries in {self.table_name} table: {e}")
            return 0


class Database:
    _busy_timeout_ms = 5000
    _write_retry_attempts = 5
    _write_retry_delay = 0.2

    def __init__(self, *, folder: str = "data", filename: str = "data.db") -> None:
        """
        Initialisiert die Datenbankverbindung und erstellt den Ordner für die Datenbankdatei, falls dieser nicht existiert.

        :param folder: Der Ordner, in dem die Datenbankdatei gespeichert werden soll. Standardmäßig "data".
        :type folder: str
        :param filename: Der Name der Datenbankdatei. Standardmäßig "data.db".
        :type filename: str
        """
        os.makedirs(folder, exist_ok=True)
        self.file = os.path.join(folder, filename)
        _logger = logging.getLogger(__name__)
        self._write_lock = asyncio.Lock()

    @asynccontextmanager
    async def connect(self):
        """
        Stellt eine asynchrone Verbindung zur SQLite-Datenbank her und sorgt dafür, dass die Verbindung ordnungsgemäß geschlossen wird.

         :return: Ein aiosqlite.Connection-Objekt, das für Datenbankoperationen verwendet werden kann.
         :rtype: aiosqlite.Connection
         :raises Exception: Wenn ein Fehler bei der Herstellung der Verbindung auftritt, wird die Ausnahme protokolliert und erneut ausgelöst.
        """
        database = None
        try:
            database = await aiosqlite.connect(self.file, timeout=self._busy_timeout_ms / 1000)
            await database.execute(f"PRAGMA busy_timeout = {self._busy_timeout_ms};")
            await database.execute("PRAGMA foreign_keys = ON;")
            await database.execute("PRAGMA journal_mode = WAL;")
            await database.execute("PRAGMA synchronous = NORMAL;")
            database.row_factory = aiosqlite.Row
            yield database
        except Exception as e:
            _logger.exception(f"Database connection error: {e}")
            raise
        finally:
            if database:
                await database.close()

    async def execute(self, query: str, params: tuple = ()) -> bool:
        """
        Führt eine SQL-Abfrage aus, die keine Ergebnisse zurückgibt (z.B. INSERT, UPDATE, DELETE).

        :param query: Die SQL-Abfrage, die ausgeführt werden soll.
        :type query: str
        :param params: Die Parameter für die SQL-Abfrage. Standardmäßig ein leeres Tupel.
        :type params: Tuple
        :return: True, wenn die Abfrage erfolgreich ausgeführt wurde, False andernfalls.
        :rtype: bool
        :raises Exception: Wenn ein Fehler bei der Ausführung der Abfrage auftritt, wird die Ausnahme protokolliert und erneut ausgelöst.
        """
        async with self._write_lock:
            for attempt in range(self._write_retry_attempts + 1):
                try:
                    async with self.connect() as connection:
                        await connection.execute(query, params)
                        await connection.commit()
                        return True
                except aiosqlite.OperationalError as e:
                    msg = str(e).lower()
                    is_locked = "database is locked" in msg or "database is busy" in msg
                    if not is_locked or attempt == self._write_retry_attempts:
                        _logger.exception(f"Database write error: {e}")
                        return False
                    delay = self._write_retry_delay * (2**attempt)
                    _logger.warning(
                        f"Database is locked, retrying in {delay:.2f} seconds (attempt {attempt + 1}/{self._write_retry_attempts})"
                    )
                    await asyncio.sleep(delay)
        return False

    async def fetch_all(self, query: str, params: tuple = ()) -> tuple[aiosqlite.Row, ...]:
        """
        Führt eine SQL-Abfrage aus, die mehrere Ergebnisse zurückgibt (z.B. SELECT) und gibt diese als Tupel von aiosqlite.Row-Objekten zurück.

        :param query: Die SQL-Abfrage, die ausgeführt werden soll.
        :type query: str
        :param params: Die Parameter für die SQL-Abfrage. Standardmäßig ein leeres Tupel.
        :type params: Tuple
        :return: Ein Tupel von aiosqlite.Row-Objekten, die die Ergebnisse der Abfrage enthalten.
        :rtype: Tuple[aiosqlite.Row, ...]
        :raises Exception: Wenn ein Fehler bei der Ausführung der Abfrage auftritt, wird die Ausnahme protokolliert und erneut ausgelöst.
        """
        async with self.connect() as connection, connection.execute(query, params) as cursor:
            return cast(tuple[aiosqlite.Row, ...], await cursor.fetchall())

    async def fetch_one(self, query: str, params: tuple = ()) -> aiosqlite.Row | None:
        """
        Führt eine SQL-Abfrage aus, die ein einzelnes Ergebnis zurückgibt (z.B. SELECT) und gibt dieses als aiosqlite.Row-Objekt zurück.

        :param query: Die SQL-Abfrage, die ausgeführt werden soll.
        :type query: str
        :param params: Die Parameter für die SQL-Abfrage. Standardmäßig ein leeres Tupel.
        :type params: Tuple
        :return: Ein aiosqlite.Row-Objekt, das das Ergebnis der Abfrage enthält, oder None, wenn kein Ergebnis gefunden wurde.
        :rtype: Optional[aiosqlite.Row]
        :raises Exception: Wenn ein Fehler bei der Ausführung der Abfrage auftritt, wird die Ausnahme protokolliert und erneut ausgelöst.
        """
        async with self.connect() as connection, connection.execute(query, params) as cursor:
            return cast(aiosqlite.Row | None, await cursor.fetchone())
