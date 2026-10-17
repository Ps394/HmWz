from __future__ import annotations

import logging
from dataclasses import dataclass, field

import discord

from hmwz import utils

from .registration_member import RegistrationMember

_logger = logging.getLogger(__name__)


@dataclass(slots=True)
class Registration:
    guild: discord.Guild
    registrations: list[RegistrationMember] = field(default_factory=list)

    def add_registration(self, registration: RegistrationMember) -> None:
        """Fügt eine neue Registrierung hinzu."""
        self.registrations.append(registration)
        _logger.debug(
            f"{utils.log_guild(self.guild)} Added registration for member {registration.member_id} role {registration.role.role_id}"
        )

    def remove_registration(self, registration: RegistrationMember) -> None:
        """Entfernt eine bestehende Registrierung."""
        self.registrations.remove(registration)
        _logger.debug(
            f"{utils.log_guild(self.guild)} Removed registration for member {registration.member_id}"
        )

    def change_registration(
        self, old_registration: RegistrationMember, new_registration: RegistrationMember
    ) -> None:
        """Ändert eine bestehende Registrierung."""
        self.remove_registration(old_registration)
        self.add_registration(new_registration)
        _logger.debug(
            f"{utils.log_guild(self.guild)} Changed registration for member {old_registration.member_id} to role {new_registration.role.role_id}"
        )

    @property
    def count_total_registrations(self) -> int:
        """Gibt die Gesamtzahl der Registrierungen zurück."""
        result = len(self.registrations)
        _logger.debug(
            f"{utils.log_guild(self.guild)} count_total_registrations: {result}"
        )
        return result

    @property
    def count_permanent_registrations(self) -> int:
        """Gibt die Anzahl der permanenten Registrierungen zurück."""
        result = len(self.permanent_registrations)
        _logger.debug(
            f"{utils.log_guild(self.guild)} count_permanent_registrations: {result}"
        )
        return result

    @property
    def count_temporary_registrations(self) -> int:
        """Gibt die Anzahl der temporären Registrierungen zurück."""
        result = len(self.temporary_registrations)
        _logger.debug(
            f"{utils.log_guild(self.guild)} count_temporary_registrations: {result}"
        )
        return result

    @property
    def permanent_registrations(self) -> tuple[RegistrationMember, ...]:
        """Gibt eine Liste der permanenten Registrierungen zurück."""
        result = [reg for reg in self.registrations if reg.role.permanent]
        _logger.debug(
            f"{utils.log_guild(self.guild)} permanent_registrations: {len(result)}"
        )
        return tuple(result)

    @property
    def temporary_registrations(self) -> tuple[RegistrationMember, ...]:
        """Gibt eine Liste der temporären Registrierungen zurück."""
        result = [reg for reg in self.registrations if not reg.role.permanent]
        _logger.debug(
            f"{utils.log_guild(self.guild)} temporary_registrations: {len(result)}"
        )
        return tuple(result)

    @property
    def total_score(self) -> int:
        """Berechnet die Gesamtpunktzahl aller Registrierungen, basierend auf den zugewiesenen Rollen und deren Punktzahlen."""
        return sum(member.role.score for member in self.registrations)
