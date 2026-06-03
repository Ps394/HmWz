from __future__ import annotations
from dataclasses import dataclass, field
import discord
import discord.ui
import logging
import typing

from configuration import config

from .registration_role import RegistrationRole


import hmModels
import hmUtils

_logger = logging.getLogger(__name__)

@dataclass(slots=True)
class Configuration():
    guild: discord.Guild
    """Guild, für die die Konfiguration gilt"""
    channel: typing.Optional[discord.TextChannel] = None
    """Anmeldungskanal"""
    message: typing.Optional[discord.Message] = None
    """Anmeldenachricht"""

    @property
    def get_title(self) -> str:
        """Gibt den Titel zurück, der im Embed angezeigt wird. Wenn kein benutzerdefinierter Titel festgelegt ist, wird der Standardtitel aus der config verwendet."""
        result = self.title if self.title else config["wz_registration"]["default_title"]
        _logger.debug(f"{hmUtils.log_guild(self.guild)} get_title: {result}")
        return result
    @property
    def get_description(self) -> str:
        """Gibt die Beschreibung zurück, die im Embed angezeigt wird. Wenn keine benutzerdefinierte Beschreibung festgelegt ist, wird die Standardbeschreibung aus der config verwendet."""
        result = self.description if self.description else config["wz_registration"]["default_description"]
        _logger.debug(f"{hmUtils.log_guild(self.guild)} get_description: {result}")
        return result

    @property
    def has_channel(self) -> bool:
        """Gibt zurück, ob ein Anmeldungskanal vorhanden ist."""
        result = self.channel is not None and isinstance(self.channel, discord.TextChannel)
        _logger.debug(f"{hmUtils.log_guild(self.guild)} has_channel: {result}")
        return result    
    @property
    def has_message(self) -> bool:
        """Gibt zurück, ob eine Anmeldenachricht vorhanden ist."""
        result = self.message is not None and isinstance(self.message, discord.Message)
        _logger.debug(f"{hmUtils.log_guild(self.guild)} has_message: {result}")
        return result
    
    @property
    def has_registration_roles(self) -> bool:
        """Gibt zurück, ob Registrierungsrollen vorhanden sind."""
        result = self.registration_roles is not None and len(self.registration_roles) > 0
        _logger.debug(f"{hmUtils.log_guild(self.guild)} has_registration_roles: {result}")
        return result

    @property
    def is_configured(self) -> bool:
        """Gibt zurück, ob die Konfiguration vollständig ist (d.h. sowohl ein Anmeldungskanal als auch Anmeldungsrollen vorhanden sind)."""
        result = self.has_channel and self.has_registration_roles
        _logger.debug(f"{hmUtils.log_guild(self.guild)} is_configured: {result}")
        return result
    
    @property
    def client_avatar(self) -> discord.Asset:
        """
        Gibt das Avatar des Clients zurück.

        :return: Das Avatar des Clients.
        :rtype: discord.Asset
        """
        return self.guild.icon if self.guild.icon else self.client.user.avatar if self.client.user.avatar else None
    
    @property
    def client_color(self) -> discord.Color:
        """
        Gibt die Farbe des Clients zurück, basierend auf der höchsten Rolle des Clients in der Gilde.

        :return: Die Farbe des Clients.
        :rtype: discord.Color
        """
        return max(self.guild.get_member(self.client.user.id).roles, key=lambda r: r.position).color

    @classmethod
    def get_embed(cls, ) -> hmModels.BotEmbed:
        """Erstellt und gibt ein Embed zurück, das für die Anmeldenachricht verwendet werden kann. Das Embed enthält den Titel, die Beschreibung und den Avatar des Clients als Footer."""
        return hmModels.BotEmbed(
            title=cls.get_title,
            description=cls.get_description,
            color=cls.embed_color,
            client_avatar=cls.client_avatar
        )
    
    @classmethod
    def get_view(cls) -> discord.ui.View:
        """Erstellt und gibt eine View zurück, die für die Anmeldenachricht verwendet werden kann. Die View enthält die Schaltflächen für die Registrierung."""
        view = discord.ui.View(timeout=None)
        row = 0
        if not cls.is_configured:
            _logger.error(f"{hmUtils.log_guild(cls.guild)} get_view: Configuration is not complete, cannot create view.")
            return view
        
        for registration_role in cls.registration_roles:
            def gen_callback(role: discord.Role):
                async def callback(interaction):
                    await cls.handle_registration(interaction, role)
                return callback
            
            button = discord.ui.Button(label=registration_role.role.name, style=discord.ButtonStyle.primary, row=row)
            button.callback = gen_callback(registration_role.role)
            view.add_item(button)
            row += 1
            _logger.debug(f"{hmUtils.log_guild(cls.guild)} get_view: Added button for role {registration_role.role.name} with score {registration_role.score} and permanent={registration_role.permanent}")
        return view
    
    # Settings
    title: typing.Optional[str] = None
    """Anmeldungstitel, der im Embed angezeigt wird"""
    description: typing.Optional[str] = None
    """Anmeldungsbeschreibung, die im Embed angezeigt wird"""
    show_registrations: bool = False
    """Anzeige der Registrierungen im Anmeldungskanal"""
    score_mod_lvl: bool = False
    """Anzeigen des Wz-Scores in der Anmeldung"""
    matchmaker: bool = False
    """Matchmaker für Zuweisung von Rollen basierend auf dem Wz-Score"""
    registration_roles: list[RegistrationRole] = field(default_factory=list)
    """Liste der Rollen, die bei der Registrierung zugewiesen werden können"""


