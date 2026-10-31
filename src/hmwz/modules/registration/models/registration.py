"""Domain model for registration state within a guild."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import discord

from hmwz.utils.interactions import log_guild

from .registration_member import RegistrationMember

_logger = logging.getLogger(__name__)


@dataclass(slots=True)
class Registration:
    """Registration state for a guild's configured channel."""

    guild: discord.Guild
    registrations: list[RegistrationMember] = field(default_factory=list)

    def add_registration(self, registration: RegistrationMember) -> None:
        """Add a member registration to this registration state.

        Args:
            registration: Registration record to append.
        """
        self.registrations.append(registration)
        _logger.debug(
            "%s Added registration for member %s role %s",
            log_guild(self.guild),
            registration.member_id,
            registration.role.role_id,
        )

    def remove_registration(self, registration: RegistrationMember) -> None:
        """Remove a member registration from this registration state.

        Args:
            registration: Registration record to remove.
        """
        self.registrations.remove(registration)
        _logger.debug(
            "%s Removed registration for member %s",
            log_guild(self.guild),
            registration.member_id,
        )

    def change_registration(
        self, old_registration: RegistrationMember, new_registration: RegistrationMember
    ) -> None:
        """Replace an existing registration with an updated record.

        Args:
            old_registration: Registration record to remove.
            new_registration: Updated registration record to add.
        """
        self.remove_registration(old_registration)
        self.add_registration(new_registration)

    @property
    def count_total_registrations(self) -> int:
        """Return the number of registrations."""
        return len(self.registrations)

    @property
    def count_permanent_registrations(self) -> int:
        """Return the number of permanent registrations."""
        return len(self.permanent_registrations)

    @property
    def count_temporary_registrations(self) -> int:
        """Return the number of temporary registrations."""
        return len(self.temporary_registrations)

    @property
    def permanent_registrations(self) -> tuple[RegistrationMember, ...]:
        """Return all registrations assigned to permanent roles."""
        return tuple(reg for reg in self.registrations if reg.role.permanent)

    @property
    def temporary_registrations(self) -> tuple[RegistrationMember, ...]:
        """Return all registrations assigned to temporary roles."""
        return tuple(reg for reg in self.registrations if not reg.role.permanent)

    @property
    def total_score(self) -> int:
        """Return the sum of registration role scores."""
        return sum(member.role.score for member in self.registrations)
