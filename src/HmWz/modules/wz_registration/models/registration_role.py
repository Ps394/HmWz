from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RegistrationRole:
    """Repräsentiert eine Registrierungsrolle, die einem Mitglied zugewiesen werden kann.

    :param role: Die Discord-Rolle.
    :type role: discord.Role
    :param permanent: Gibt an, ob die Rolle permanent ist (True) oder nicht (False).
    :type permanent: bool
    """

    role_id: int
    score: int = 0
    permanent: bool = False
