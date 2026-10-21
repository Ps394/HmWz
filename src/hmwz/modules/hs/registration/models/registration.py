from __future__ import annotations

import logging
from dataclasses import dataclass, field

import discord

from hmwz import utils

from .registration_member import RegistrationMember

_logger = logging.getLogger(__name__)


@dataclass(slots=True)
class Registration:
    """Registration state for a guild's configured channel."""

    guild: discord.Guild
    registrations: list[RegistrationMember] = field(default_factory=list)

    def add_registration(self, registration: RegistrationMember) -> None:
        self.registrations.append(registration)
        _logger.debug(
            "%s Added registration for member %s role %s",
            utils.log_guild(self.guild),
            registration.member_id,
            registration.role.role_id,
        )

    def remove_registration(self, registration: RegistrationMember) -> None:
        self.registrations.remove(registration)
        _logger.debug(
            "%s Removed registration for member %s",
            utils.log_guild(self.guild),
            registration.member_id,
        )

    def change_registration(
        self, old_registration: RegistrationMember, new_registration: RegistrationMember
    ) -> None:
        self.remove_registration(old_registration)
        self.add_registration(new_registration)

    @property
    def count_total_registrations(self) -> int:
        return len(self.registrations)

    @property
    def count_permanent_registrations(self) -> int:
        return len(self.permanent_registrations)

    @property
    def count_temporary_registrations(self) -> int:
        return len(self.temporary_registrations)

    @property
    def permanent_registrations(self) -> tuple[RegistrationMember, ...]:
        return tuple(reg for reg in self.registrations if reg.role.permanent)

    @property
    def temporary_registrations(self) -> tuple[RegistrationMember, ...]:
        return tuple(reg for reg in self.registrations if not reg.role.permanent)

    @property
    def total_score(self) -> int:
        return sum(member.role.score for member in self.registrations)
