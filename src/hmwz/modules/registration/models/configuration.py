"""Domain model for a registration channel configuration."""

from __future__ import annotations

from dataclasses import dataclass

from .registration_role import RegistrationRole


@dataclass(frozen=True, slots=True)
class Configuration:
    """Domain configuration for one registration channel."""

    guild_id: int
    channel_id: int | None
    message_id: int | None
    title: str | None
    description: str | None
    show_lock_emojis: bool = True
    registration_roles: tuple[RegistrationRole, ...] = ()

    @property
    def has_channel(self) -> bool:
        """Whether this configuration has a channel assigned."""
        return self.channel_id is not None

    @property
    def has_message(self) -> bool:
        """Whether this configuration has an overview message assigned."""
        return self.message_id is not None

    @property
    def has_registration_roles(self) -> bool:
        """Whether this configuration contains at least one registration role."""
        return bool(self.registration_roles)

    @property
    def is_configured(self) -> bool:
        """Whether a channel and at least one registration role are configured."""
        return self.has_channel and self.has_registration_roles
