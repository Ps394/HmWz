from __future__ import annotations
from dataclasses import dataclass, field
import discord
import logging
from HmWz.utils import log_guild
from .registration_role import RegistrationRole
from .registration_member import RegistrationMember

_logger = logging.getLogger(__name__)

@dataclass(slots=True)
class Registration:
    guild : discord.Guild
    registrations: list[RegistrationMember] = field(default_factory=list)

    @classmethod
    def add_registration(cls, registration: RegistrationMember) -> None:
        """Fügt eine neue Registrierung hinzu."""
        cls.registrations.append(registration)
        _logger.debug(f"{log_guild(cls.guild)} Added registration for user {registration.user_id} with roles {[role.name for role in registration.roles]}")

    @classmethod
    def remove_registration(cls, registration: RegistrationMember) -> None:
        """Entfernt eine bestehende Registrierung."""
        cls.registrations.remove(registration)
        _logger.debug(f"{log_guild(cls.guild)} Removed registration for user {registration.user_id}")

    @classmethod 
    def change_registration(cls, old_registration: RegistrationMember, new_registration: RegistrationMember) -> None:
        """Ändert eine bestehende Registrierung."""
        cls.remove_registration(old_registration)
        cls.add_registration(new_registration)
        _logger.debug(f"{log_guild(cls.guild)} Changed registration for user {old_registration.user_id} to new roles {[role.name for role in new_registration.roles]}")
        
    @property
    def count_total_registrations(self) -> int:
        """Gibt die Gesamtzahl der Registrierungen zurück."""
        result = len(self.registrations)
        _logger.debug(f"{log_guild(self.guild)} count_total_registrations: {result}")
        return result
    
    @property
    def count_permanent_registrations(self) -> int:
        """Gibt die Anzahl der permanenten Registrierungen zurück."""
        result = len(self.permanent_registrations)
        _logger.debug(f"{log_guild(self.guild)} count_permanent_registrations: {result}")
        return result
    
    @property
    def count_temporary_registrations(self) -> int:
        """Gibt die Anzahl der temporären Registrierungen zurück."""
        result = len(self.temporary_registrations)
        _logger.debug(f"{log_guild(self.guild)} count_temporary_registrations: {result}")
        return result
        
    @property
    def permanent_registrations(self) -> tuple[RegistrationMember, ...]:
        """Gibt eine Liste der permanenten Registrierungen zurück."""
        result = [reg for reg in self.registrations if reg.role.permanent]
        _logger.debug(f"{log_guild(self.guild)} permanent_registrations: {len(result)}")
        return tuple(result)    

    @property
    def temporary_registrations(self) -> tuple[RegistrationMember, ...]:
        """Gibt eine Liste der temporären Registrierungen zurück."""
        result = [reg for reg in self.registrations if not reg.role.permanent]
        _logger.debug(f"{log_guild(self.guild)} temporary_registrations: {len(result)}")
        return tuple(result)

    @property
    def total_score(self) -> int:
        """Berechnet die Gesamtpunktzahl aller Registrierungen, basierend auf den zugewiesenen Rollen und deren Punktzahlen."""
        return sum(
            role.score for member in self.registrations for role in member.roles
        )
