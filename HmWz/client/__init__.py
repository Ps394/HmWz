from __future__ import annotations
import logging
import asyncio
import os
import discord

from typing import Optional
from discord import AutoShardedClient as DiscordClient, Intents, app_commands, Interaction, AuditLogAction, abc

from HmWz.client.overviews.registration import RegistrationOverview

from . import overviews
from . import commands
from .. import services
from ..i18n import CommandTranslator, t
from ..configuration import Monitoring
from ..emojis import Emojis
from ..types import Guild, TextChannel, Message, Member, Role
from ..exception import HTTPException, Forbidden, NotFound, InteractionResponded
from ..event import RawMessageDeleteEvent

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
        self._commands_initialized = False

    async def update_loop(self, interval: int = 3600):
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
                    await self.overview_manager.sync(guild=guild, sync_data=True, sync_discord=True)
                    await asyncio.sleep(1)
                except Exception as e:
                    logger.exception(f"{guild.name} (ID: {guild.id}) - Error updating overviews: {e}")
            await asyncio.sleep(interval)
    
    async def resource_monitor_loop(self, interval: int = Monitoring.INTERVAL.value):
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
                mem_info = psutil.virtual_memory()
                temp_info = psutil.sensors_temperatures() if hasattr(psutil, "sensors_temperatures") else None
                storage_info = psutil.disk_usage('/')
                cpu_info =  psutil.cpu_times_percent(interval=None)
                process.memory_full_info()
                cpu_percent = process.cpu_percent(interval=1)

                if temp_info:
                    for name, entries in temp_info.items():
                        for entry in entries:
                            if entry.current >= Monitoring.TEMPERATURE_THRESHOLD.value:
                                logger.warning(f"High temperature detected: {entry.label or name} at {entry.current:.1f}°C")
                
                if cpu_info.user > Monitoring.CPU_THRESHOLD.value or cpu_info.system >Monitoring.CPU_THRESHOLD.value:
                    logger.warning(f"High CPU usage detected: {cpu_percent:.1f}%")

                if mem_info.percent > Monitoring.MEMORY_THRESHOLD.value:
                    logger.warning(f"High RAM usage detected: {mem_info.percent:.1f}% ({mem_info.used / 1024 / 1024:.1f} MB used of {mem_info.total / 1024 / 1024:.1f} MB)")

                if storage_info.percent > Monitoring.DISK_THRESHOLD.value:
                    logger.warning(f"High disk usage detected: {storage_info.percent:.1f}% ({storage_info.used / 1024 / 1024 / 1024:.1f} GB used of {storage_info.total / 1024 / 1024 / 1024:.1f} GB)")

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


        @self.tree.error
        async def tree_on_error(interaction: Interaction, error: app_commands.AppCommandError):
            """
            Globaler Fehlerhandler für Befehlsfehler. Versucht, die Fehlerbehandlung des Clients aufzurufen und protokolliert alle Fehler.
            """
            try:
                await self.on_application_command_error(interaction, error)
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
            
            if not self.global_command_sync:
                logger.info("Clearing global commands...")
                self.tree.clear_commands(guild=None)
                await self.tree.sync()
            else:
                logger.info("Clearing guild-specific commands...")
                for guild in self.guilds:
                    logger.info(f"{guild.name} (ID: {guild.id}) - Clearing commands...")
                    self.tree.clear_commands(guild=guild)
                    await self.tree.sync(guild=guild)
        
            logger.info("All commands cleared successfully.")
        except Exception as e:
            logger.exception(f"Failed to clear commands: {e}")

    async def setup_hook(self):
        """
        Führt die Einrichtung des Clients durch, einschließlich der Registrierung von Befehlen und der Synchronisierung globaler Befehle.
        """
        await self.services.setup()

        await self.tree.set_translator(CommandTranslator())

        await self.register_commands()

        asyncio.create_task(self.resource_monitor_loop())

        return await super().setup_hook()

    async def on_ready(self):
        """
        Wird aufgerufen, wenn der Bot bereit ist. Protokolliert die Anmeldeinformationen und fügt alle Gilden zur Datenbank hinzu.
        """
        logger.info(f'Logged in as {self.user} (ID: {self.user.id})')
        logger.info('------')

        if not self._commands_initialized:
            await self.clear_commands()
            await self.sync_commands_guilds()
            await self.sync_commands_global()
            self._commands_initialized = True

        for guild in self.guilds: 
            await self.services.servers.add(guild=guild)

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


    async def on_guild_channel_delete(self, channel: abc.GuildChannel):
        """
        Wird aufgerufen, wenn ein Kanal in einer Gilde gelöscht wird. Leitet das Ereignis an den Overview-Manager weiter.

        :param channel: Der gelöschte Kanal
        :type channel: discord.TextChannel
        """
        pass

    async def on_guild_channel_update(self, before: abc.GuildChannel, after: abc.GuildChannel):
        """
        Wird aufgerufen, wenn ein Kanal in einer Gilde aktualisiert wird. Leitet das Ereignis an den Overview-Manager weiter.

        :param before: Der Kanal vor der Aktualisierung
        :type before: discord.TextChannel
        :param after: Der Kanal nach der Aktualisierung
        :type after: discord.TextChannel
        """
        pass

    async def on_guild_channel_create(self, channel: abc.GuildChannel):
        """
        Wird aufgerufen, wenn ein Kanal in einer Gilde erstellt wird. Leitet das Ereignis an den Overview-Manager weiter.

        :param channel: Der erstellte Kanal
        :type channel: discord.TextChannel
        """
        pass

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
            views : overviews.Instances = await self.overview_manager.get_instances(guild=guild)

            if views:
                for overview in views:
                    if isinstance(overview, RegistrationOverview):
                        await overview.sync(sync_config=True)
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
        
            await asyncio.gather(*tasks)

            views : overviews.Instances = await self.overview_manager.get_instances(guild=guild)
            if views:
                for overview in views:
                    await overview.sync(sync_config=True)
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
                views : overviews.Instances = await self.overview_manager.get_instances(guild=guild)
                if views:
                    for overview in views:
                        await overview.sync(sync_data=True)
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
        await asyncio.sleep(1) 
        if after.roles != before.roles:
            try:
                async for entry in after.guild.audit_logs(limit=5, action=AuditLogAction.member_role_update):
                    if entry.user.id == self.user.id and entry.target.id == after.id:
                        return
            except Forbidden:
                # Bot doesn't have permission to view audit logs, continue anyway
                pass
        guild = before.guild
        try:
            instance : overviews.registration.RegistrationOverview = await self.overview_manager.get_instance(guild=guild, instance_type=overviews.registration.RegistrationOverview)
            configuration : overviews.registration.Configuration = instance.configuration if instance else None
            data : overviews.registration.Data = instance.data if instance else None

            if not instance or not configuration or not data:
                return
            if configuration.is_valid == False:
                return
            
            config_role_ids = {r.role.id for r in configuration.roles}

            has_before = config_role_ids & {r.id for r in before.roles} 
            has_after = config_role_ids & {r.id for r in after.roles}

            if len(has_after) > 1:
                await self.services.wz.registrations.remove(guild=guild, member=before.id)
                await after.remove_roles(*[r.role for r in configuration.roles if r.role.id in has_before], reason="Wz-Registrierung - Rolle entfernt")

            if after in [m.member for m in data.members] or has_after or has_before:
                await instance.sync(sync_data=True, sync_discord=True)
                await instance.ensure()
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

    async def on_application_command_error(self, interaction: Interaction, error: app_commands.AppCommandError):
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
                message = t(interaction, "command.error.permissions")
                logger.warning(f"{log_context} - User missing permissions: {error}")
            elif isinstance(error, app_commands.BotMissingPermissions):
                message = t(interaction, "command.error.bot_permissions")
                logger.error(f"{log_context} - Bot missing permissions: {error}")
            elif isinstance(error, app_commands.CommandOnCooldown):
                message = t(interaction, "command.error.cooldown", retry_after=f"{error.retry_after:.1f}")
                logger.info(f"{log_context} - Command on cooldown: {error}")
            
            else:
                message = t(interaction, "command.error.unexpected")
                logger.exception(f"{log_context} - Unexpected error: {error}")
            await send(message, ephemeral=True)
        except Exception as e:
            logger.exception(f"{log_context} - Failed to send error message: {e}")

