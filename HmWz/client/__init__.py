from __future__ import annotations
import logging
import asyncio
import os

from typing import Optional
from discord import app_commands
from . import overviews
from . import commands
from .. import services
from ..emojis import Emojis

from discord import Client as DiscordClient, Intents, app_commands, Interaction, Guild, Member, Role, RawMessageDeleteEvent

logger = logging.getLogger(__name__)

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    logger.warning("psutil not available - resource monitoring disabled")  

class Client(DiscordClient):
    registered_commands : int = 0 
    def __init__(self, *, intents: Intents = Intents.default(), global_command_sync: Optional[bool]=True, **options):
        """
        Initialisiert den Client mit den erforderlichen Intents und Optionen.

        :param intents: Die Intents, die der Bot benötigt (Standard: discord.Intents.default())
        :type intents: discord.Intents
        :param global_command_sync: Ob die Befehle global synchronisiert werden sollen (Standard: True)
        :type global_command_sync: bool
        :param options: Zusätzliche Optionen für den Client
        :type options: dict
        """
        super().__init__(intents=intents, **options, logger=logger)
        self.services = services.Services()
        self.tree = app_commands.CommandTree(self)
        self.overview_manager = overviews.Manager(self)
        self.global_command_sync = global_command_sync

    async def update_loop(self, interval: int = 900):
        """
        Periodische Aktualisierungsschleife für die Übersichten.
        
        :param interval: Zeitintervall in Sekunden zwischen den Aktualisierungen (Standard: 900 Sekunden = 15 Minuten)
        :type interval: int
        """
        await self.wait_until_ready()
        while not self.is_closed():
            for guild in self.guilds:            
                try:
                    logger.info(f"{guild.name} (ID: {guild.id}) - Starting overview update.")
                    await self.overview_manager.update(guild=guild)
                    await asyncio.sleep(1)
                except Exception as e:
                    logger.exception(f"{guild.name} (ID: {guild.id}) - Error updating overviews: {e}")
            await asyncio.sleep(interval)
    
    async def resource_monitor_loop(self, interval: int = 60):
        """
        Periodische Überwachung der Ressourcen (CPU, Speicher, Festplatte).
        
        :param interval: Zeitintervall in Sekunden zwischen den Überprüfungen (Standard: 60 Sekunden)
        :type interval: int
        """
        if not PSUTIL_AVAILABLE:
            logger.info("Resource monitoring disabled (psutil not installed)")
            return
            
        await self.wait_until_ready()
        process = psutil.Process(os.getpid())
        
        while not self.is_closed():
            try:
                cpu_percent = process.cpu_percent(interval=1)
                memory_info = process.memory_info()
                storage = psutil.disk_usage('/')
                memory_mb = memory_info.rss / 1024 / 1024
                
                logger.info(
                    f"Resource Usage - CPU: {cpu_percent:.1f}%, "
                    f"Memory: {memory_mb:.1f} MB, "
                    f"Disk: {storage.percent}%"   
                )
            except Exception as e:
                logger.exception(f"Error monitoring resources: {e}")
            
            await asyncio.sleep(interval)

    def add_command(self, command: callable):
        """
        Fügt einen Befehl zur Befehlsstruktur hinzu.

        :param command: Der Befehl, der hinzugefügt werden soll
        :type command: callable
        """
        if isinstance(command, type) and issubclass(command, app_commands.Group):
            for subcommand in command.commands:
                if isinstance(subcommand, app_commands.Command):
                    logger.debug(f"Registered subcommand: {subcommand.name} in group {command.name}")
                    self.registered_commands += 1
                if isinstance(subcommand, app_commands.Group):
                    logger.debug(f"Registered subcommand group: {subcommand.name} in group {command.name} with {len(subcommand.commands)} subcommands")
                    self.registered_commands += len(subcommand.commands)
        else:
            logger.debug(f"Registered command: {getattr(command, 'name', command)}")
            self.registered_commands += 1
        self.tree.add_command(command)

    async def register_commands(self):
        """
        Registriert die Befehle aus dem Commands-Modul.
        """
        logger.info("Registering commands...")

        self.add_command(commands.wz.WzGroup(self))

        """
        [Deprecated] Registrierung von Befehlen aus dem Commands.REGISTRY - da es zu Problemen beim Synchronisieren der Befehle kam, wenn sie direkt in der REGISTRY registriert wurden, werden die Befehle jetzt direkt im Client hinzugefügt.

        for command in Commands.REGISTRY:
            try:
                if isinstance(command, type) and issubclass(command, app_commands.Group):
                    instance = command(self)
                
                    #self.tree.add_command(instance)
                    for subcommand in instance.commands:
                        if isinstance(subcommand, app_commands.Command):
                            logger.debug(f"Registered subcommand: {subcommand.name} in group {instance.name}")
                            self.registered_commands += 1
                        if isinstance(subcommand, app_commands.Group):
                            logger.debug(f"Registered subcommand group: {subcommand.name} in group {instance.name} with {len(subcommand.commands)} subcommands")
                            self.registered_commands += len(subcommand.commands)       
                else:
                    #self.tree.add_command(command)
                    self.registered_commands += 1
                    logger.debug(f"Registered command: {getattr(command, 'name', command)}")

            except app_commands.CommandAlreadyRegistered:
                logger.warning(f"Command already registered: {getattr(command, 'name', command)}")
            except Exception as e:
                logger.exception(
                    f"Failed to register command {getattr(command, 'name', command)} "
                    f"({type(command).__name__}): {e}"
                )
       
        """
        @self.tree.error
        async def tree_on_error(interaction: Interaction, error: app_commands.AppCommandError):
            """
            Globaler Fehlerhandler für Befehlsfehler. Versucht, die Fehlerbehandlung des Clients aufzurufen und protokolliert alle Fehler.
            """
            try:
                await self.on_appplication_command_error(interaction, error)
            except Exception:
                logger.exception(f"Error while handling app command error: {error}")

        logger.info(f"Total commands registered: {self.registered_commands}")

    async def sync_commands_global(self):
        """Synchronisiert die globalen Befehle, wenn global_command_sync aktiviert ist."""
        if self.global_command_sync == True:
            try:
                await self.tree.sync()
                logger.info("Global commands synced successfully.")
            except Exception as e:
                logger.exception(f"Failed to sync global commands: {e}")

    async def sync_commands_guilds(self):
        """
        Synchronisiert die Befehle für alle Gilden, wenn global_command_sync deaktiviert ist.
        """
        if self.global_command_sync == False:
            for guild in self.guilds:
                try:
                    self.tree.copy_global_to(guild=guild)
                    await self.tree.sync(guild=guild)
                    logger.info(f"{guild.name} (ID: {guild.id}) - Commands synced successfully.")
                except Exception as e:
                    logger.exception(f"{guild.name} (ID: {guild.id}) - Failed to sync commands: {e}")

    async def clear_commands(self):
        """
        Entfernt alle registrierten Befehle, sowohl global als auch für alle Gilden.
        """
        try:
            self.guilds
            self.tree.clear_commands(guild=None) 
            for guild in self.guilds:
                self.tree.clear_commands(guild=guild)
            await self.tree.sync()
            logger.info("All commands cleared successfully.")
        except Exception as e:
            logger.exception(f"Failed to clear commands: {e}")

    async def setup_hook(self):
        """
        Führt die Einrichtung des Clients durch, einschließlich der Registrierung von Befehlen und der Synchronisierung globaler Befehle.
        """
        await self.services.setup()

        
        await self.clear_commands()

        await self.register_commands()

        asyncio.create_task(self.resource_monitor_loop())

        return await super().setup_hook()

    async def on_ready(self):
        """
        Wird aufgerufen, wenn der Bot bereit ist. Protokolliert die Anmeldeinformationen und fügt alle Gilden zur Datenbank hinzu.
        """
        logger.info(f'Logged in as {self.user} (ID: {self.user.id})')
        logger.info('------')

        for guild in self.guilds: 
            await self.services.servers.add(guild=guild)

        await self.sync_commands_guilds()
        await self.sync_commands_global()

        await self.overview_manager.startup()
        logger.debug("Overview manager startup complete.")

    async def on_guild_join(self, guild: Guild):
        """
        Wird aufgerufen, wenn der Bot einer neuen Gilde beitritt. Fügt die Gilde zur Datenbank hinzu.
        
        :param guild: Die Gilde, der der Bot beigetreten ist
        :type guild: discord.Guild
        """
        if await self.services.servers.add(guild=guild):
            logger.info(f"{guild.name} (ID: {guild.id}) - Joined new guild and added to database.")
        else:
            logger.error(f"{guild.name} (ID: {guild.id}) - Failed to add new guild to database.")
    
    async def on_guild_remove(self, guild: Guild):
        """
        Wird aufgerufen, wenn der Bot eine Gilde verlässt. Entfernt die Gilde aus der Datenbank.
        
        :param guild: Die Gilde, die der Bot verlassen hat
        :type guild: discord.Guild
        """
        if await self.services.remove_guild_data(guild=guild):
            logger.info(f"{guild.name} (ID: {guild.id}) - Removed guild from database on leave.")
        else:
            logger.error(f"{guild.name} (ID: {guild.id}) - Failed to remove guild from database on leave.")

    async def on_guild_role_update(self, before: Role, after: Role):
        """
        Wird aufgerufen, wenn eine Rolle in einer Gilde aktualisiert wird. Synchronisiert die entsprechenden Übersichten, wenn die Rolle registriert ist.

        :param before: Die Rolle vor der Aktualisierung
        :type before: discord.Role
        :param after: Die Rolle nach der Aktualisierung
        :type after: discord.Role
        """
        guild = before.guild
        try:
            reg_roles = await self.services.wz.roles.get(guild=guild)
            if not reg_roles or before.id not in [r.role.id for r in reg_roles]:
                return
            overviews : Overviews.Instances = await self.overview_manager.get_instances(guild=guild)

            if overviews:
                for overview in overviews:
                    await overview.sync()
                    await overview.ensure()

        except Exception as e:
            logger.exception(f"{guild.name} (ID: {guild.id}) - Failed to handle role update for '{before.name}': {e}")

    async def on_guild_role_delete(self, role: Role):
        """
        Wird aufgerufen, wenn eine Rolle in einer Gilde gelöscht wird. Entfernt die Rolle aus der Registrierung und synchronisiert die Übersichten, wenn sie registriert war.
        
        :param role: Die gelöschte Rolle
        :type role: discord.Role
        """
        guild = role.guild
        try:
            try:
                configured_roles = await self.services.wz.roles.get(guild=guild)
                if not configured_roles or role.id not in [r.role.id for r in configured_roles]:
                    return
            except Exception as e:
                logger.exception(f"{guild.name} (ID: {guild.id}) - Failed to check if deleted role '{role.name}' was a WZ registration role: {e}")
            
            tasks = []
            tasks.append(self.services.wz.roles.remove(guild=guild, role=role.id))
            tasks.append(self.services.wz.registrations.remove(guild=guild, role=role.id))
        
            asyncio.gather(*tasks)

            overviews : Overviews.Instances = await self.overview_manager.get_instances(guild=guild)
            if overviews:
                for overview in overviews:
                    await overview.sync()
                    await overview.ensure()
        except Exception as e:
            logger.exception(f"{guild.name} (ID: {guild.id}) - Failed to remove deleted role '{role.name}' from WZ registration: {e}")

    async def on_raw_member_remove(self, member: Member):
        """
        Wird aufgerufen, wenn ein Mitglied eine Gilde verlässt oder entfernt wird. Entfernt die Registrierung des Mitglieds und synchronisiert die Übersichten, wenn eine Registrierung vorhanden war.

        :param member: Das Mitglied, das die Gilde verlassen hat
        :type member: discord.Member
        """
        guild = member.guild
        try:
            registration : services.wz.RegistrationsRecord = await self.services.wz.registrations.get(guild=guild, member=member.id)
            if registration:
                await self.services.wz.registrations.remove(guild=guild, member=member.id)
                overviews : Overviews.Instances = await self.overview_manager.get_instances(guild=guild)
                if overviews:
                    for overview in overviews:
                        await overview.sync()
                        await overview.ensure()
        except Exception as e:
            logger.exception(f"{guild.name} (ID: {guild.id}) - Failed to remove registration for departed member '{member}': {e}")

    async def on_member_update(self, before: Member, after: Member):
        """
        Wird aufgerufen, wenn ein Mitglied in einer Gilde aktualisiert wird. Aktualisiert die Registrierung des Mitglieds und synchronisiert die Übersichten, wenn eine Registrierung vorhanden ist.

        :param before: Das Mitglied vor der Aktualisierung
        :type before: discord.Member
        :param after: Das Mitglied nach der Aktualisierung
        :type after: discord.Member
        """
        guild = before.guild
        try:
            registration : services.wz.RegistrationsRecords = await self.services.wz.registrations.get(guild=guild, member=before.id)
            if not registration:
                return
            else:
                overviews : Overviews.Instances = await self.overview_manager.get_instances(guild=guild)
                if overviews:
                    for overview in overviews:
                        await overview.sync()
                        await overview.ensure()
        except Exception as e:
            logger.exception(f"{guild.name} (ID: {guild.id}) - Failed to update registration for member '{before}': {e}")

    async def on_raw_message_delete(self, payload: RawMessageDeleteEvent):
        """
        Wird aufgerufen, wenn eine Nachricht gelöscht wird. Leitet das Ereignis an den Overview-Manager weiter.

        :param payload: Das Ereignis-Payload der gelöschten Nachricht
        :type payload: discord.RawMessageDeleteEvent
        """
        guild = self.get_guild(payload.guild_id)
        if not guild:
            return
        await self.overview_manager.on_message_delete(payload)

    async def on_appplication_command_error(self, interaction: Interaction, error: app_commands.AppCommandError):
        """
        Globaler Fehlerhandler für Befehlsfehler. Sendet eine Fehlermeldung an den Benutzer und protokolliert den Fehler.
        
        :param interaction: Die Interaktion, die den Fehler ausgelöst hat
        :type interaction: discord.Interaction
        :param error: Der aufgetretene Fehler
        :type error: discord.app_commands.AppCommandError
        """
        log_context = f"{interaction.guild.name}({interaction.guild.id}) - {interaction.user} - Command: {interaction.command}"
        send = interaction.followup.send if interaction.response.is_done() else interaction.response.send_message
        try:
            if isinstance(error, app_commands.MissingPermissions):
                message = f"{Emojis.error.value} Du hast nicht die erforderlichen Berechtigungen, um diesen Befehl auszuführen."
                logger.warning(f"{log_context} - User missing permissions: {error}")
            elif isinstance(error, app_commands.BotMissingPermissions):
                message = f"{Emojis.error.value} Mir fehlen die erforderlichen Berechtigungen, um diesen Befehl auszuführen."
                logger.error(f"{log_context} - Bot missing permissions: {error}")
            elif isinstance(error, app_commands.CommandOnCooldown):
                message = f"{Emojis.error.value} Warte {error.retry_after:.1f} Sekunden, bevor du diesen Befehl erneut verwenden kannst."
                logger.info(f"{log_context} - Command on cooldown: {error}")
            
            else:
                message = f"{Emojis.error.value} Ein unerwarteter Fehler ist aufgetreten: {error}"
                logger.exception(f"{log_context} - Unexpected error: {error}")
            await send(message, ephemeral=True)
        except Exception as e:
            logger.exception(f"{log_context} - Failed to send error message: {e}")

