import logging
from typing import Optional
from discord import Guild
from .database import Database

logger = logging.getLogger(__name__)

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
        self.database : Database = database
        self.logger : logging.Logger = logger

    @property
    def table_name(self) -> str:
        """Gibt den Namen der Tabelle zurück, die von diesem Service verwendet wird. Standardmäßig ist dies der Name der Klasse.
        
        :return: Der Name der Tabelle als String.
        :rtype: str
        """
        return self.__class__.__name__
    

    @classmethod
    def log_prefix(cls, guild: Optional[Guild] = None) -> str:
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
        raise NotImplementedError("Subclasses must implement the \"table\" property.")

    async def count(self) -> int:
        try:
            query = f"SELECT COUNT(*) FROM {self.table_name}"
            row = await self.database.fetch_one(query)
            self.logger.info(f"{self.log_prefix()}Counted entries in {self.table_name} table.")
            return row[0] if row else 0
        except Exception as e:
            self.logger.exception(f"{self.log_prefix()}Failed to count entries in {self.table_name} table: {e}")
            return 0
        

        