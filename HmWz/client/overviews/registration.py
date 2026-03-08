from __future__ import annotations
import logging

from discord import Embed, Interaction, ButtonStyle
from discord.ui import View, Button
from .registry import register
from .basic_overview import BasicOverview
from dataclasses import dataclass, field
from typing import Optional, List, Tuple
from enum import Enum

from ...services import wz, Services
from ...emojis import Emojis
from ...types import Guild, TextChannel, Message, Member, Role, RegistrationRole, RegistrationMember
from ...utils import fetch_channel, fetch_message, fetch_member, fetch_role
from ...exception import HTTPException, Forbidden, NotFound, InteractionResponded
from ...event import RawMessageDeleteEvent

logger = logging.getLogger(__name__)

type ConfigurationRoles = List[RegistrationRole]
type RegistrationMembers = List[RegistrationMember]

type RegistrationEmbeds = List[Embed]
type RegistrationList = List[str]
type RegistrationMessages = List[Message]

@dataclass()
class State():
    on_startup: bool = True
    sync_from_discord: bool = False
    sync_configuration: bool = False
    sync_data: bool = False
    
    class Event(Enum):
        STARTUP = 0x100
        CHANGED_DISCORD = 0x200
        CHANGED_CONFIGURATION = 0x300
        CHANGED_REGISTRATIONS = 0x400
    
    def check(self, event: Event) -> bool:
        if event == self.Event.STARTUP and self.on_startup:
            self.reset(self.Event.STARTUP)
            return True
        elif event == self.Event.CHANGED_DISCORD and self.sync_from_discord:
            self.reset(self.Event.CHANGED_DISCORD)
            return True
        elif event == self.Event.CHANGED_CONFIGURATION and self.sync_configuration:
            self.reset(self.Event.CHANGED_CONFIGURATION)
            return True
        elif event == self.Event.CHANGED_REGISTRATIONS and self.sync_data:
            self.reset(self.Event.CHANGED_REGISTRATIONS)
            return True
        else:
            return False  
        
    
    def reset(self, event: Optional[Event] = None):
        if event is not None or event == self.Event.STARTUP:
             self.on_startup = False
             self.sync_from_discord = False
             self.sync_configuration = False
             self.sync_data = False
        elif event == self.Event.CHANGED_DISCORD:
            self.sync_from_discord = False
        elif event == self.Event.CHANGED_CONFIGURATION:
            self.sync_configuration = False
        elif event == self.Event.CHANGED_REGISTRATIONS:
            self.sync_data = False


    def clear(self):
        self.on_startup = False
        self.sync_from_discord = False
        self.sync_configuration = False
        self.sync_data = False

@dataclass(slots=True)
class Records:
    """
    Repräsentiert die Datenbank-Records für die Registrierung, einschließlich der Konfiguration, Rollen, Registrierungen und zugehörigen Nachrichten.
    """
    configuration : Optional[wz.RegistrationRecord] = None
    roles : Optional[wz.RolesRecords] = None
    registrations : Optional[wz.RegistrationsRecords] = None
    registrations_messages : Optional[wz.ListRecords] = None

    async def sync_configuration(self, services: Services, guild: Guild) -> bool:
        try:
            self.configuration = await services.wz.registration.get(guild=guild)
            self.roles = await services.wz.roles.get(guild=guild)

            return self.configuration is not None and self.roles is not None
        except Exception as e:
            logger.exception(f"Failed to sync registration configuration record from database for guild {guild.id}: {e}")
            return False
        
    async def sync_data(self, services: Services, guild: Guild) -> bool:
        try:
            self.registrations = await services.wz.registrations.get(guild=guild)
            self.registrations_messages = await services.wz.list.get(guild=guild)
            
            return self.registrations is not None or self.registrations_messages is not None
        except Exception as e:
            logger.exception(f"Failed to sync registration records from database for guild {guild.id}: {e}")
            return False
        
    @property
    def has_configured_channel(self) -> bool:
        """Überprüft, ob ein gültiger Registrierungskanal in der Konfiguration vorhanden ist."""
        return self.configuration is not None and self.configuration.channel is not None
    @property
    def has_configured_roles(self) -> bool:
        """Überprüft, ob gültige Rollen in der Konfiguration vorhanden sind."""
        return self.roles is not None and len(self.roles) > 0
    @property
    def has_registrations(self) -> bool:
        """Überprüft, ob Registrierungen vorhanden sind."""
        return self.registrations is not None and len(self.registrations) > 0
    @property
    def has_registration_messages(self) -> bool:
        """Überprüft, ob Registrierungslisten-Nachrichten vorhanden sind."""
        return self.registrations_messages is not None and len(self.registrations_messages) > 0
    @property
    def is_configured(self) -> bool:
        """Überprüft, ob die Registrierungskonfiguration vollständig ist (Kanal und Rollen)."""
        return self.has_configured_channel and self.has_configured_roles
    @property
    def permanent_roles(self) -> Tuple[RegistrationRole, ...]:
        """Gibt eine Liste der permanenten Registrierungsrollen zurück."""
        return tuple(role for role in self.roles if role.permanent) if self.roles else tuple()
    @property
    def non_permanent_roles(self) -> Tuple[RegistrationRole, ...]:
        """Gibt eine Liste der nicht-permanenten Registrierungsrollen zurück."""
        return tuple(role for role in self.roles if not role.permanent) if self.roles else tuple()

@dataclass(slots=True)
class Configuration:
    """Repräsentiert die Konfiguration für die Registrierung, einschließlich der verfügbaren Rollen und deren Eigenschaften.

    :param roles: Eine Liste von Registrierungsrollen, die für die Registrierung verfügbar sind.
    :type roles: ConfigurationRoles
    """
    roles: ConfigurationRoles = field(default_factory=list)
    title: Optional[str] = None
    description: Optional[str] = None
    channel: Optional[TextChannel] = None
    message: Optional[Message] = None
    embed: Optional[Embed] = None
    view: Optional[View] = None

    @property
    def has_channel(self) -> bool:
        """Überprüft, ob ein gültiger Registrierungskanal in der Konfiguration vorhanden ist."""
        return self.channel is not None
    @property
    def has_roles(self) -> bool:
        """Überprüft, ob gültige Rollen in der Konfiguration vorhanden sind."""
        return len(self.roles) > 0
    @property
    def is_valid(self) -> bool:
        """Überprüft, ob die Registrierungskonfiguration vollständig ist (Kanal und Rollen)."""
        return self.has_channel and self.has_roles
    @property
    def has_message(self) -> bool:
        """Überprüft, ob eine Registrierungsnachricht in der Konfiguration vorhanden ist."""
        logger.debug(f"Checking if registration configuration has message: {self.message is not None}")
        return self.message is not None
    @property
    def permanent_roles(self) -> Tuple[RegistrationRole, ...]:
        """Gibt eine Liste der permanenten Registrierungsrollen zurück."""
        return tuple(role for role in self.roles if role.permanent)
    @property
    def non_permanent_roles(self) -> Tuple[RegistrationRole, ...]:
        """Gibt eine Liste der nicht-permanenten Registrierungsrollen zurück."""
        return tuple(role for role in self.roles if not role.permanent)
    @property
    def permanent_roles_ids(self) -> Tuple[int, ...]:
        """Gibt eine Liste der IDs der permanenten Registrierungsrollen zurück."""
        return tuple(role.role.id for role in self.roles if role.permanent)
    @property
    def non_permanent_roles_ids(self) -> Tuple[int, ...]:
        """Gibt eine Liste der IDs der nicht-permanenten Registrierungsrollen zurück."""
        return tuple(role.role.id for role in self.roles if not role.permanent)

@dataclass(slots=True)
class Data:
    """Repräsentiert die Daten für die Registrierung, einschließlich der registrierten Mitglieder und zugehörigen Informationen.

    :param members: Eine Liste von registrierten Mitgliedern mit ihren zugewiesenen Rollen.
    :type members: RegistrationMembers
    """
    members: RegistrationMembers = field(default_factory=list)
    messages: RegistrationMessages = field(default_factory=list)
    embeds: RegistrationEmbeds = field(default_factory=list)
    list: RegistrationList = field(default_factory=list)

@dataclass(slots=True)
class Stats:
    """Repräsentiert die Statistiken für die Registrierung, einschließlich der Anzahl der permanenten und nicht-permanenten Rollen.

    :param permanent: Die Anzahl der permanenten Rollen.
    :type permanent: int
    :param non_permanent: Die Anzahl der nicht-permanenten Rollen.
    :type non_permanent: int
    """
    total: int = 0
    permanent: int = 0
    non_permanent: int = 0

@register
class RegistrationOverview(BasicOverview):
    """
    Übersicht, die die Registrierung für den nächsten WZ verwaltet und anzeigt.
    Sie zeigt die registrierten Benutzer und ihre Rollen an und ermöglicht es den Benutzern,
    sich für den nächsten WZ anzumelden oder abzumelden, indem sie auf die entsprechenden Schaltflächen klicken.
    """

    def __init__(self, guild, services, client):
        super().__init__(guild, services, client)

        self.records : Records = Records()
        self.configuration : Configuration = Configuration()
        self.data : Data = Data()
        self.stats : Stats = Stats()
        self.state : State = State()

    async def create_registrations_list(self) -> bool:
        try:
            if not self.data.members:
                self.data.list = []
                return True
            self.data.list = []
            i = 0
            for reg_member in self.data.members:
                i += 1
                role_name = reg_member.role.role.name if reg_member.role else "-"
                self.data.list.append(f"{i}. {reg_member.member.display_name} [{role_name}]")
            return True
        except Exception as e:
            logger.exception(f"{self.log_context} Failed to create registrations list: {e}")
            return False
            
    async def create_registrations_embeds(self, chunk_size=4095, max_players=40) -> bool:
        """Erstellt Embeds mit Berücksichtigung von 4096 Zeichen-Limit und max. 35-40 Spielern pro Embed."""
        try:
            if not self.data.list or len(self.data.list) == 0:
                self.data.embeds = []
                return True
            self.data.embeds = []
            permanent_registration = f"{Emojis.PERMA_REGISTRATION.value}: {self.stats.permanent}"
            non_permanent_registration = f"{Emojis.NORMAL_REGISTRATION.value}: {self.stats.non_permanent}"
            total_registrations = f"{self.stats.total}"
            temp = ""
            i = 0
            player_count = 0
            for row in self.data.list:
                # Check beide Limits: Zeichen (4096) und Spieler (35)
                if len(temp) + len(row) + 1 > chunk_size or player_count >= max_players:
                    i += 1
                    embed = self.BotEmbed(
                        title=f"{i}. Anmeldungen: {total_registrations} ( {permanent_registration} | {non_permanent_registration} )",
                        description=temp,
                        color=self.client_color,
                        client_avatar=self.client_avatar
                    ) 
                    self.data.embeds.append(embed)
                    temp = ""
                    player_count = 0
                temp += row + "\n"
                player_count += 1
            if temp:
                i += 1
                embed = self.BotEmbed(
                    title=f"{i}. Anmeldungen: {total_registrations} ( {permanent_registration} | {non_permanent_registration} )",
                    description=temp,
                    color=self.client_color,
                    client_avatar=self.client_avatar
                )
                self.data.embeds.append(embed)
            return True
        except Exception as e:
            logger.exception(f"{self.log_context} Failed to create registrations embeds: {e}")
            return False

    async def update_registrations(self) -> bool:
        try:
            if self.configuration.is_valid:
                embeds = self.data.embeds or []
                messages = self.data.messages or []
                len_embeds = len(embeds)
                len_messages = len(messages)
                updated_messages = []

                for i in range(max(len_embeds, len_messages)):
                    if i < len_embeds and i < len_messages:
                        # Bestehende Nachricht aktualisieren
                        try:
                            await messages[i].edit(embed=embeds[i])
                            await self.services.wz.list.update(
                                guild=self.guild,
                                message=messages[i].id,
                                title=embeds[i].title,
                                text=embeds[i].description
                            )
                            updated_messages.append(messages[i])
                        except Exception as e:
                            logger.warning(f"{self.log_context} Registrations List Overview update warning: Failed to update message {messages[i].id}: {e}")
                    elif i < len_embeds:
                        # Neue Nachricht senden
                        try:
                            new_msg = await self.configuration.channel.send(embed=embeds[i])
                            await self.services.wz.list.add(
                                guild=self.guild,
                                channel=self.configuration.channel.id,
                                message=new_msg.id,
                                title=embeds[i].title,
                                text=embeds[i].description
                            )
                            updated_messages.append(new_msg)
                        except NotFound:
                            logger.warning(f"{self.log_context} Registrations List Overview update warning: Registration channel {self.configuration.channel.id} not found for sending new message.")
                        except Forbidden:
                            logger.warning(f"{self.log_context} Registrations List Overview update warning: Missing permissions to access registration channel {self.configuration.channel.id} for sending new message.")
                        except HTTPException as e:
                            logger.warning(f"{self.log_context} Registrations List Overview update warning: HTTP error while sending new message in registration channel {self.configuration.channel.id}: {e}")
                        except ValueError as e:
                            logger.warning(f"{self.log_context} Registrations List Overview update warning: Failed to add new message to database: {e}")
                    elif i < len_messages:
                        # Überschüssige Nachricht löschen
                        try:
                            await messages[i].delete()
                        except NotFound:
                            logger.warning(f"{self.log_context} Registrations List Overview update warning: Message {messages[i].id} not found for deletion.")
                        except Forbidden:
                            logger.warning(f"{self.log_context} Registrations List Overview update warning: Missing permissions to delete message {messages[i].id}.")
                        except HTTPException as e:
                            logger.warning(f"{self.log_context} Registrations List Overview update warning: HTTP error while deleting message {messages[i].id}: {e}")
                        await self.services.wz.list.remove(guild=self.guild, message=messages[i].id)

                # Messages-Liste aktualisieren, damit beim nächsten Aufruf wiederverwendet wird
                self.data.messages = updated_messages
                return True
            else:
                logger.debug(f"{self.log_context} Cannot update registrations list overview: Invalid setup.")
                return False
        except Exception as e:
            logger.exception(f"{self.log_context} Registrations List Overview update failed: {e}")
            return False

    async def registration_register(self, interaction: Interaction, role: Role):
            try:
                await interaction.response.defer(ephemeral=True)
                records =await self.services.wz.registrations.get(guild=self.guild, member=interaction.user.id)
                registration : wz.RegistrationsRecord = records[0] if records and len(records) > 0 else None
                message = ""
                if registration and registration.role == role.id:
                    await self.services.wz.registrations.remove(guild=self.guild, member=interaction.user.id)
                    message = f"{Emojis.UNREGISTER.value} Abmeldung von {role.name} erfolgreich."
                    await interaction.user.remove_roles(role, reason="WZ Deregistration")
                    action = "deregister"
                elif registration and registration.role != role.id:
                    await interaction.user.remove_roles(registration.role, reason="WZ Registration Update") 
                    await self.services.wz.registrations.add(guild=self.guild, member=interaction.user.id, role=role.id)
                    await interaction.user.add_roles(role, reason="WZ Registration")
                    message = f"{Emojis.REREGISTER.value} Aktualisierung auf {role.name} erfolgreich."
                    action = "update"
                else:       
                    await self.services.wz.registrations.add(guild=self.guild, member=interaction.user.id, role=role.id)
                    await interaction.user.add_roles(role, reason="WZ Registration")
                    message = f"{Emojis.REGISTER.value} Anmeldung mit {role.name} erfolgreich."
                    action = "register"

                await interaction.followup.send(message, ephemeral=True)
                await self.sync(sync_data=True)
                await self.sleep(self.WAIT_INTERVAL)
                logger.debug(f"{self.log_context} {interaction.user} registration action({action}) for role {role.id}.")
            except (HTTPException, Forbidden, NotFound, InteractionResponded, Exception) as e:
                await interaction.followup.send(f"{Emojis.ERROR.value} Fehler bei der Registrierung.", ephemeral=True)
                logger.exception(f"{self.log_context} {interaction.user} failed to register for role {role.name}: {e}")

    def gen_view(self)->View:
        view = View(timeout=None)
        row = 0
        if not self.configuration.has_roles:
            logger.warning(f"{self.log_context} No configured roles found for registration overview view generation.")
            return view
        
        for configured in self.configuration.roles:
            def gen_callback(r: Role):
                async def callback(interaction: Interaction):
                    await self.registration_register(interaction, r)
                return callback
            
            button = Button(
                label=configured.role.name,
                style=ButtonStyle.primary,
                row=row
            )
            button.callback = gen_callback(configured.role)
            view.add_item(button)
            row += 1
            logger.debug(f"{self.log_context} Added registration role button for role {configured.role.id if configured.role else 'unknown'} to view.")
        return view

    def create_registration_message(self)->bool:
        try:
            self.configuration.embed = self.BotEmbed(
                title=self.configuration.title or "Anmeldung",
                description=self.configuration.description or "Melde dich hier für den nächsten WZ an.",
                color=self.client_color,
                client_avatar=self.client_avatar
            )
            self.configuration.view = self.gen_view()
            return True
        except Exception as e:
            logger.exception(f"{self.log_context} Failed to create registration message: {e}")
            return False

    async def sync_list_messages_from_db(self) -> bool:
        """Lädt bestehende Registrierungslisten-Nachrichten aus der DB und holt die Discord-Message-Objekte."""
        try:
            list_records = await self.services.wz.list.get(guild=self.guild)
            if not list_records:
                self.data.messages = []
                return True
            messages = []
            stale_ids = []
            for record in list_records:
                try:
                    channel = await fetch_channel(self.guild, record.channel)
                    if channel and not isinstance(channel, int):
                        msg = await fetch_message(channel, record.message)
                        if msg and not isinstance(msg, int):
                            messages.append(msg)
                        else:
                            stale_ids.append(record.message)
                    else:
                        stale_ids.append(record.message)
                except Exception:
                    stale_ids.append(record.message)
            for stale_id in stale_ids:
                await self.services.wz.list.remove(guild=self.guild, message=stale_id)
                logger.debug(f"{self.log_context} Removed stale list message {stale_id} from database.")
            self.data.messages = messages
            return True
        except Exception as e:
            logger.exception(f"{self.log_context} Failed to sync list messages from database: {e}")
            self.data.messages = []
            return False
        
    async def sync_configuration(self) -> None:
        await self.records.sync_configuration(self.services, self.guild)
        if self.records.is_configured:
            self.configuration.roles = []
            if self.records.is_configured:
                self.configuration.channel = await fetch_channel(self.guild, self.records.configuration.channel) 
                if self.configuration.has_channel:
                    for r in self.records.roles:
                        role = await fetch_role(self.guild, r.role)
                        if role is not None and isinstance(role, Role):
                            self.configuration.roles.append(RegistrationRole(role=role, score=r.score, permanent=r.permanent))

                    self.configuration.message = await fetch_message(self.configuration.channel, self.records.configuration.message) 
                    self.configuration.title = self.records.configuration.title
                    self.configuration.description = self.records.configuration.description

    async def sync_registrations(self) -> bool:
        """Lädt Registrierungsdaten aus DB und aktualisiert Listen, Embeds und Messages."""
        await self.records.sync_data(self.services, self.guild)
        
        # Reset data
        self.data.members = []
        self.data.messages = []
        
        if self.records.is_configured and self.records.has_registrations:
            try:
                for record in self.records.registrations:
                    member = await fetch_member(self.guild, record.member)
                    if member is not None and isinstance(member, Member):
                        role = next((r for r in self.configuration.roles if r.role.id == record.role), None)
                        if role is not None:
                            self.data.members.append(RegistrationMember(member=member, role=role))
    
                if self.records.has_registration_messages:
                    for record in self.records.registrations_messages:
                        message = await fetch_message(self.configuration.channel, record.message)
                        if message is not None and isinstance(message, Message):
                            self.data.messages.append(message)  

                self.stats.total = len(self.data.members)
                self.stats.permanent = len([m for m in self.data.members if m.role.permanent])
                self.stats.non_permanent = len([m for m in self.data.members if not m.role.permanent])

                # Aktualisiere Listen und Embeds
                await self.create_registrations_list()
                await self.create_registrations_embeds()

                return True      
            except Exception as e:
                logger.exception(f"Failed to sync registration members from database records: {e}")
                return False
        else:
            # Keine Registrierungen -> leere Listen/Embeds
            self.stats.total = 0
            self.stats.permanent = 0
            self.stats.non_permanent = 0
            await self.create_registrations_list()
            await self.create_registrations_embeds()
            return True    
            
    async def sync_discord(self) -> bool:
        def check_member_with_registration_role(roles : ConfigurationRoles, member: Member) -> bool:
            try:
                for configured in roles:
                    if configured.role in member.roles:
                        return True
                return False
            except Exception as e:
                logger.exception(f"{self.log_context} Failed to check user {member.id} for registration roles: {e}")
                return False
        try:
            raw_records = await self.services.wz.registrations.get(guild=self.guild)
            records = raw_records if raw_records is not None else []
            for member in self.guild.members:
                has_registration_role = check_member_with_registration_role(self.configuration.roles, member)
                registration_record = next((record for record in records if record.member == member.id), None)
                if member.bot:
                    continue
                if has_registration_role and not registration_record:
                    await self.services.wz.registrations.add(guild=self.guild, member=member.id, role=next((role for role in self.configuration.roles if role.role in member.roles), None).role.id)
                    logger.info(f"{self.log_context} Added registration record for member {member.id} with registration role.")
                elif not has_registration_role and registration_record:
                    await self.services.wz.registrations.remove(guild=self.guild, member=member.id)
                    logger.info(f"{self.log_context} Removed registration record for member {member.id} without registration role.")
            return True
        except Exception as e:
            logger.exception(f"{self.log_context} Failed to sync registrations from discord: {e}")
            return False

    async def sync_startup(self) -> bool:
        await self.sync_configuration()
        await self.sync_discord()
        await self.sync_registrations()

    async def sync(self, startup: bool = False, sync_data: bool = False, sync_config: bool = False, sync_discord: bool = False) -> bool:
        try:
            await self.wait_while_syncing()
            self.sync_start()

            # Default zu startup wenn keine Flags gesetzt
            if not any((startup, sync_data, sync_config, sync_discord)):
                startup = True

            if startup:
                await self.sync_startup()
            else:
                if sync_config:
                    await self.sync_configuration()
                
                if sync_discord:
                    await self.sync_discord()
                    
                if sync_data or sync_discord:
                    await self.sync_registrations()

            if self.configuration.is_valid:
                self.create_registration_message()
                
                # Bei sync_data: Messages aktualisieren
                if sync_data or sync_discord or startup:
                    await self.update_registrations()
            else:
                logger.info(f"{self.log_context} Registration overview is not properly configured. Sync will be skipped.")
                return False
            logger.info(f"{self.log_context} Registration Overview: synced successfully.")
            return True
        except Exception as e:
            logger.exception(f"{self.log_context} Failed to sync registration overview: {e}")
            return False
        finally:
            self.on_startup = False
            self.discord_member_changed = False
            self.database_registrations_changed = False
            self.database_configuration_changed = False
            await self.sync_stop()

    async def ensure(self) -> bool:
        try:
            if self.configuration.is_valid:
                if await self.update():
                    return True
                await self.delete()
                for attempt in range(3):
                    try:
                        return await self.send()
                    except Exception as e:
                        logger.exception(f"{self.log_context} Failed to send registration overview during ensure attempt {attempt+1}: {e}")
                        await self.sleep(300)
        except Exception as e:
            logger.exception(f"{self.log_context} Failed to ensure registration overview: {e}")
            return False

    async def send(self) -> bool:
        try:
            await self.wait_while_busy()
            self.work_start()
            if not self.configuration.is_valid:
                logger.info(f"{self.log_context} Cannot send registration overview: Invalid configuration.")
                return False
            
            if self.configuration.has_message:
                await self.delete()

            self.configuration.message = await self.configuration.channel.send(embed=self.configuration.embed, view=self.configuration.view)

            await self.services.wz.registration.setup_registration(
                guild=self.guild,
                message=self.configuration.message.id,
            )
            
            await self.update_registrations()
            logger.info(f"{self.log_context} Registration overview sent successfully.")
            return True
        except Forbidden:
            logger.warning(f"{self.log_context} Missing permissions to send message in registration channel {self.configuration.channel.id}.")
            return False
        except NotFound:
            logger.warning(f"{self.log_context} Registration channel {self.configuration.channel.id} not found for sending message.")
            return False
        except HTTPException as e:
            logger.warning(f"{self.log_context} HTTP error while sending message in registration channel {self.configuration.channel.id}: {e}")
            return False
        except Exception as e:
            logger.exception(f"{self.log_context} Failed to send registration overview: {e}")
            return False
        finally:
            await self.work_stop()
    
    async def update(self) -> bool:
        try:
            await self.wait_while_busy()
            self.work_start()   

            if not self.configuration.is_valid:
                logger.info(f"{self.log_context} Cannot update registration overview: Invalid configuration.")
                return False
            
            if not self.configuration.has_message:
                logger.info(f"{self.log_context} Cannot update registration overview: No existing message.")
                return False
      
            await self.configuration.message.edit(embed=self.configuration.embed, view=self.configuration.view)

            logger.info(f"{self.log_context} Registration overview updated successfully.")
            return True
        except Forbidden:
            logger.warning(f"{self.log_context} Missing permissions to edit message in registration channel {self.configuration.channel.id}.")
            return False
        except NotFound:
            logger.warning(f"{self.log_context} Registration channel {self.configuration.channel.id} or message not found for updating.")
            return False
        except HTTPException as e:
            logger.warning(f"{self.log_context} HTTP error while updating message in registration channel {self.configuration.channel.id}: {e}")
            return False   
        except Exception as e:
            logger.exception(f"{self.log_context} Failed to update registration overview: {e}")
            return False
        finally:
            await self.work_stop()
        
    async def clean(self) -> bool:
        try:
            await self.wait_while_busy()
            self.work_start()

            if not self.configuration.is_valid:
                return False

            await self.configuration.channel.purge(limit=999, check=lambda m: m.author.id != self.client.user.id and m.pinned == False)
            return True
        except Forbidden:
            logger.warning(f"{self.log_context} Missing permissions to purge messages in registration channel {self.configuration.channel.id}.")
            return False
        except NotFound:
            logger.warning(f"{self.log_context} Registration channel {self.configuration.channel.id} not found for purging messages.")
            return False     
        except Exception as e:
            logger.exception(f"{self.log_context} Failed to clean registration channel: {e}")
            return False
        finally:            
            await self.work_stop()

    async def delete(self) -> bool:
        try:
            await self.wait_while_deleting()
            self.delete_start()

            if not self.configuration.is_valid:
                return False
            if self.configuration.has_message:
                await self.configuration.channel.purge(limit=999, check=lambda m: m.author.id == self.client.user.id and m.id != self.configuration.message.id)
            else:
                await self.configuration.channel.purge(limit=999, check=lambda m: m.author.id == self.client.user.id)
            return True
        except Forbidden:
            logger.warning(f"{self.log_context} Missing permissions to delete messages in registration channel {self.configuration.channel.id}.")
            return False
        except HTTPException as e:
            logger.warning(f"{self.log_context} HTTP error while deleting messages in registration channel {self.configuration.channel.id}: {e}")
            return False
        except Exception as e:
            logger.exception(f"{self.log_context} Failed to delete registration messages: {e}")
            return False
        finally:
            await self.delete_stop()

    async def on_message_delete(self, payload: RawMessageDeleteEvent) -> bool:
        if self.IS_DELETING:
            await self.wait_while_deleting()
            return False
        await self.sync(sync_config=True)
        await self.ensure()
        return True