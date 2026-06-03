import discord
from dataclasses import dataclass

from .registration_role import RegistrationRole

@dataclass(frozen=True, slots=True)
class RegistrationMember:
    """Repräsentiert ein registriertes Mitglied mit zugewiesenen Rollen.

    :param member: Das Discord-Mitglied.
    :type member: discord.Member
    :param roles: Eine Liste von Registrierungsrollen, die dem Mitglied zugewiesen sind.
    :type roles: list[RegistrationRole]
    """
    member: discord.Member = None
    role: RegistrationRole = None
    score: int = None
    timestamp: str = None
