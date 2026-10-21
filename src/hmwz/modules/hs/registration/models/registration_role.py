from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RegistrationRole:
    """A Discord role that can be selected during a registration."""

    role_id: int
    score: int = 0
    permanent: bool = False
