from dataclasses import dataclass
from typing import ClassVar


@dataclass(frozen=True, slots=True)
class Channel:
    """Ein fuer die WZ-Bereinigung konfigurierter Kanal."""

    guild_id: int
    channel_id: int

    MAX_PER_GUILD: ClassVar[int] = 25
