from __future__ import annotations
from dataclasses import dataclass
import typing

from .registration_role import RegistrationRole


@dataclass(frozen=True, slots=True)
class Configuration:
    """Domain-Konfiguration fuer WZ-Registrierung auf Guild-Ebene."""

    guild_id: int
    channel_id: typing.Optional[int]
    message_id: typing.Optional[int]
    title: typing.Optional[str]
    description: typing.Optional[str]
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
