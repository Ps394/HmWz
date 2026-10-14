from dataclasses import dataclass
from typing import ClassVar


@dataclass(frozen=True, slots=True)
class PurgeChannel:
    """Ein für den Registrierungs-Reset konfigurierter Bereinigungskanal."""

    guild_id: int
    channel_id: int

    MAX_PER_GUILD: ClassVar[int] = 25
