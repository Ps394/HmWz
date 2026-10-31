"""Domain model for a member's registration."""

from dataclasses import dataclass

from .registration_role import RegistrationRole


@dataclass(frozen=True, slots=True)
class RegistrationMember:
    """A member's registration and selected role."""

    member_id: int
    role: RegistrationRole
    timestamp: str
    account: str = ""
