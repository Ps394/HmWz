"""Settings for a role managed by the WZ module."""

from dataclasses import dataclass
from typing import ClassVar


@dataclass(frozen=True, slots=True)
class Role:
    """A WZ role configured for a guild."""

    guild_id: int
    role: int
    MAX_PER_GUILD: ClassVar[int] = 25
