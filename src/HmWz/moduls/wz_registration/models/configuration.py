from __future__ import annotations

from dataclasses import dataclass

from .registration_role import RegistrationRole


@dataclass(frozen=True, slots=True)
class Configuration:
    """Domain-Konfiguration fuer WZ-Registrierung auf Guild-Ebene."""

    guild_id: int
    channel_id: int | None
    message_id: int | None
    title: str | None
    description: str | None
    registration_roles: tuple[RegistrationRole, ...] = ()

    @property
    def has_channel(self) -> bool:
        return self.channel_id is not None

    @property
    def has_message(self) -> bool:
        return self.message_id is not None

    @property
    def has_registration_roles(self) -> bool:
        return len(self.registration_roles) > 0

    @property
    def is_configured(self) -> bool:
        return self.has_channel and self.has_registration_roles
