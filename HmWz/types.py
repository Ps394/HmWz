from dataclasses import dataclass, field
from typing import Union, Optional, Sequence, Tuple, List, Callable
from discord import Guild, Member, Role, TextChannel, Message, Embed

__all__ = (
    "dataclass",
    "field", 
    "Union", 
    "Optional", 
    "Sequence", 
    "Tuple", 
    "List",
    "Callable",
    "Guild", 
    "Member", 
    "Role", 
    "TextChannel", 
    "Message",
    "Embed",
    "Id",
    "Ids",
    "DiscordMember",
    "DiscordRole",
    "DiscordChannel",
    "DiscordMessage",
    )

type Id = int
"""
Type-Alias für die id von Discord-Objekten 

:type id: int
"""
type Ids = Tuple[Id, ...]

type DiscordMember = Union[Member, int]
"""Representiert ein Discord-Mitglied, entweder als Member-Objekt oder als ID (int). Kann auch None sein, wenn kein Mitglied vorhanden ist."""
type DiscordRole = Union[Role, int]
"""Representiert eine Discord-Rolle, entweder als Role-Objekt oder als ID (int). Kann auch None sein, wenn keine Rolle vorhanden ist."""
type DiscordChannel = Union[TextChannel, int]
"""Representiert einen Discord-Kanal, entweder als TextChannel-Objekt oder als ID (int). Kann auch None sein, wenn kein Kanal vorhanden ist."""
type DiscordMessage = Union[Message, int]
"""Representiert eine Discord-Nachricht, entweder als Message-Objekt oder als ID (int). Kann auch None sein, wenn keine Nachricht vorhanden ist."""


@dataclass(frozen=True, slots=True)
class RegistrationRole:
    """Repräsentiert eine Registrierungsrolle, die einem Mitglied zugewiesen werden kann.

    :param role: Die Discord-Rolle.
    :type role: Role
    :param permanent: Gibt an, ob die Rolle permanent ist (True) oder nicht (False).
    :type permanent: bool
    """
    role: Role = None
    score: int = 0
    permanent: bool = False

@dataclass(frozen=True, slots=True)
class RegistrationMember:
    """Repräsentiert ein registriertes Mitglied mit zugewiesenen Rollen.

    :param member: Das Discord-Mitglied.
    :type member: Member
    :param roles: Eine Liste von Registrierungsrollen, die dem Mitglied zugewiesen sind.
    :type roles: List[RegistrationRole]
    """
    member: Member = None
    role: RegistrationRole = None
    score: int = None
    timestamp: str = None
