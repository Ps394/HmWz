from __future__ import annotations

import asyncio
import logging
import os
import typing
from asyncio.log import logger

import discord
import hmEvents
import hmExceptions
import hmUtils
import moduls
import sqlLiteDB
from configuration import config
from i18n import CommandTranslator, t

from . import commands, monitoring, recordsets

_logger = logging.getLogger(__name__)

__all__ = ["Client", "commands", "hmEvents", "hmExceptions", "hmUtils", "recordsets", "sqlLiteDB"]


class Client(discord.Client):
    registered_commands: int = 0

    def __init__(
        self,
        *,
        intents: discord.Intents = discord.Intents.default(),
        global_command_sync: bool | None = True,
        **options,
    ):
        super().__init__(intents=intents, **options)
        self._database: sqlLiteDB.Database = sqlLiteDB.Database(
            folder=config["database"]["folder"], filename=config["database"]["filename"]
        )
        self._servers: recordsets.Server = recordsets.Server(self._database)
        self.module_manager = moduls.Manager(self)

        self.CommandTree = discord.app_commands.CommandTree(self)
        self.global_command_sync = global_command_sync
        self._commands_initialized = False

    async def setup_hook(self):
        """
        Führt die Einrichtung des Clients durch, einschließlich der Registrierung von Befehlen und der Synchronisierung globaler Befehle.
        """
        await self._database.execute(self._servers.table)
        await self.CommandTree.set_translator(CommandTranslator())

        await self.register_commands()

        asyncio.create_task(monitoring.resource_monitor_loop())

        return await super().setup_hook()

    async def on_ready(self):
        """
        Wird aufgerufen, wenn der Bot bereit ist. Protokolliert die Anmeldeinformationen und fügt alle Gilden zur Datenbank hinzu.
        """
        _logger.info(f"Logged in as {self.user} (ID: {self.user.id})")
        _logger.info("------")

        if not self._commands_initialized:
            await self.clear_commands()
            await self.sync_commands_guilds()
            await self.sync_commands_global()
            self._commands_initialized = True

        for guild in self.guilds:
            await self._servers.add(guild=guild)

        await self.module_manager.startup()

    async def on_guild_join(self, guild: discord.Guild):
        """
        Wird aufgerufen, wenn der Bot einer neuen Gilde beitritt. Fügt die Gilde zur Datenbank hinzu.

        :param guild: Die Gilde, der der Bot beigetreten ist
        :type guild: discord.Guild
        """
        try:
            await self._servers.add(guild=guild)
            await self.module_manager.on_guild_join(guild)
            _logger.info(f"{guild.name} ({guild.id}) - Guild added to database.")
        except Exception as e:
            _logger.exception(f"{guild.name} ({guild.id}) - Failed to add guild to database: {e}")

    async def on_guild_remove(self, guild: discord.Guild):
        """
        Wird aufgerufen, wenn der Bot eine Gilde verlässt. Entfernt die Gilde aus der Datenbank.

        :param guild: Die Gilde, die der Bot verlassen hat
        :type guild: discord.Guild
        """
        try:
            await self.module_manager.on_guild_remove(guild)
            await self._servers.remove(guild=guild)
            _logger.info(f"{guild.name} ({guild.id}) - Guild removed from database.")
        except Exception as e:
            _logger.exception(f"{guild.name} ({guild.id}) - Failed to remove guild from database: {e}")

    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        """
        Wird aufgerufen, wenn ein Kanal in einer Gilde gelöscht wird. Leitet das Ereignis an den Overview-Manager weiter.

        :param channel: Der gelöschte Kanal
        :type channel: discord.TextChannel
        """
        await self.module_manager.on_guild_channel_delete(channel)

    async def on_guild_channel_update(self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel):
        """
        Wird aufgerufen, wenn ein Kanal in einer Gilde aktualisiert wird. Leitet das Ereignis an den Overview-Manager weiter.

        :param before: Der Kanal vor der Aktualisierung
        :type before: discord.TextChannel
        :param after: Der Kanal nach der Aktualisierung
        :type after: discord.TextChannel
        """
        await self.module_manager.on_guild_channel_update(before, after)

    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        """
        Wird aufgerufen, wenn ein Kanal in einer Gilde erstellt wird. Leitet das Ereignis an den Overview-Manager weiter.

        :param channel: Der erstellte Kanal
        :type channel: discord.TextChannel
        """
        await self.module_manager.on_guild_channel_create(channel)

    async def on_guild_role_update(self, before: discord.Role, after: discord.Role):
        """
        Wird aufgerufen, wenn eine Rolle in einer Gilde aktualisiert wird. Synchronisiert die entsprechenden Übersichten, wenn die Rolle registriert ist.

        :param before: Die Rolle vor der Aktualisierung
        :type before: discord.Role
        :param after: Die Rolle nach der Aktualisierung
        :type after: discord.Role
        """
        await self.module_manager.on_guild_role_update(before, after)

    async def on_guild_role_delete(self, role: discord.Role):
        """
        Wird aufgerufen, wenn eine Rolle in einer Gilde gelöscht wird. Entfernt die Rolle aus der Registrierung und synchronisiert die Übersichten, wenn sie registriert war.

        :param role: Die gelöschte Rolle
        :type role: discord.Role
        """
        await self.module_manager.on_guild_role_delete(role)

    async def on_raw_member_remove(self, payload: hmEvents.RawMemberRemoveEvent):
        """
        Wird aufgerufen, wenn ein Mitglied eine Gilde verlässt oder entfernt wird. Entfernt die Registrierung des Mitglieds und synchronisiert die Übersichten, wenn eine Registrierung vorhanden war.

        :param payload: Ereignis Payload des entfernen Benutzers
        :type payload: hmEvents.RawMemberRemoveEvent
        """
        await self.module_manager.on_raw_member_remove(payload)

    async def on_member_update(self, before: discord.Member, after: discord.Member):
        """
        Wird aufgerufen, wenn ein Mitglied in einer Gilde aktualisiert wird. Aktualisiert die Registrierung des Mitglieds und synchronisiert die Übersichten, wenn eine Registrierung vorhanden ist.

        :param before: Das Mitglied vor der Aktualisierung
        :type before: discord.Member
        :param after: Das Mitglied nach der Aktualisierung
        :type after: discord.Member
        """
        await self.module_manager.on_member_update(before, after)

    async def on_raw_message_delete(self, payload: hmEvents.RawMessageDeleteEvent):
        """
        Wird aufgerufen, wenn eine Nachricht gelöscht wird. Leitet das Ereignis an den Overview-Manager weiter.

        :param payload: Das Ereignis-Payload der gelöschten Nachricht
        :type payload: hmEvents.RawMessageDeleteEvent
        """
        await self.module_manager.on_raw_message_delete(payload)

    async def on_raw_bulk_message_delete(self, payload: hmEvents.RawBulkMessageDeleteEvent):
        """
        Wird aufgerufen, wenn mehrere Nachrichten auf einmal gelöscht werden (z. B. durch /purge). Leitet das Ereignis an den Overview-Manager weiter.

        :param payload: Das Ereignis-Payload der gelöschten Nachrichten
        :type payload: hmEvents.RawBulkMessageDeleteEvent
        """
        await self.module_manager.on_raw_bulk_message_delete(payload)

    async def on_application_command_error(
        self, interaction: discord.Interaction, error: discord.app_commands.AppCommandError
    ):
        """
        Globaler Fehlerhandler für Befehlsfehler. Sendet eine Fehlermeldung an den Benutzer und protokolliert den Fehler.

        :param interaction: Die Interaktion, die den Fehler ausgelöst hat
        :type interaction: discord.Interaction
        :param error: Der aufgetretene Fehler
        :type error: discord.app_commands.AppCommandError
        """
        log_context = f"u- {interaction.user} - Command: {interaction.command}"


        send = interaction.followup.send if interaction.response.is_done() else interaction.response.send_message
        try:
            if isinstance(error, discord.app_commands.MissingPermissions):
                message = t(interaction, "command.error.permissions")
                logger.warning(f"{log_context} - User missing permissions: {error}")
            elif isinstance(error, discord.app_commands.BotMissingPermissions):
                message = t(interaction, "command.error.bot_permissions")
                logger.error(f"{log_context} - Bot missing permissions: {error}")
            elif isinstance(error, discord.app_commands.CommandOnCooldown):
                message = t(interaction, "command.error.cooldown", retry_after=f"{error.retry_after:.1f}")
                logger.info(f"{log_context} - Command on cooldown: {error}")

            else:
                message = t(interaction, "command.error.unexpected")
                logger.exception(f"{log_context} - Unexpected error: {error}")
            await send(message, ephemeral=True)
        except discord.HTTPException as e:
            if e.code in (10062, 40060):
                logger.warning(
                    "%s - Could not send error response because the interaction "
                    "is expired or already acknowledged: %s",
                    log_context,
                    e,
                )
            else:
                logger.exception("%s - Failed to send error message: %s", log_context, e)
        except Exception as e:
            logger.exception(f"{log_context} - Failed to send error message: {e}")

    def add_command(
        self,
        command: discord.app_commands.Command
        | discord.app_commands.Group
        | discord.app_commands.ContextMenu,
    ) -> None:
        """
        Fügt einen Befehl zur Befehlsstruktur hinzu.

        :param command: Der Befehl, der hinzugefügt werden soll
        :type command: callable
        """
        if isinstance(command, discord.app_commands.Group):
            for subcommand in command.commands:
                if isinstance(subcommand, discord.app_commands.Command):
                    _logger.debug(f"Registered subcommand: {subcommand.name} in group {command.name}")
                    self.registered_commands += 1
                if isinstance(subcommand, discord.app_commands.Group):
                    _logger.debug(
                        f"Registered subcommand group: {subcommand.name} in group {command.name} with {len(subcommand.commands)} subcommands"
                    )
                    self.registered_commands += len(subcommand.commands)
        else:
            _logger.debug(f"Registered command: {getattr(command, 'name', command)}")
            self.registered_commands += 1
        self.CommandTree.add_command(command)

    async def register_commands(self):
        """
        Registriert die Befehle aus dem Commands-Modul.
        """
        _logger.info("Registering commands...")

        self.add_command(commands.AboutBot)
        self.add_command(commands.Purge)
        self.add_command(moduls.wz_registration.commands.WzGroup(self))

        @self.CommandTree.error
        async def tree_on_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
            """
            Globaler Fehlerhandler für Befehlsfehler. Versucht, die Fehlerbehandlung des Clients aufzurufen und protokolliert alle Fehler.
            """
            try:
                await self.on_application_command_error(interaction, error)
            except Exception:
                _logger.exception(f"Error while handling app command error: {error}")

        _logger.info(f"Total commands registered: {self.registered_commands}")

    async def sync_commands_global(self):
        """Synchronisiert die globalen Befehle, wenn global_command_sync aktiviert ist."""
        if self.global_command_sync == True:
            try:
                await self.CommandTree.sync()
                _logger.info("Global commands synced successfully.")
            except Exception as e:
                _logger.exception(f"Failed to sync global commands: {e}")

    async def sync_commands_guilds(self):
        """
        Synchronisiert die Befehle für alle Gilden, wenn global_command_sync deaktiviert ist.
        """
        if self.global_command_sync == False:
            for guild in self.guilds:
                try:
                    self.CommandTree.copy_global_to(guild=guild)
                    await self.CommandTree.sync(guild=guild)
                    _logger.info(f"{guild.name} (ID: {guild.id}) - Commands synced successfully.")
                except Exception as e:
                    _logger.exception(f"{guild.name} (ID: {guild.id}) - Failed to sync commands: {e}")

    async def clear_commands(self):
        """
        Entfernt alle registrierten Befehle, sowohl global als auch für alle Gilden.
        """
        try:
            if not self.global_command_sync:
                _logger.info("Clearing global commands...")
                self.CommandTree.clear_commands(guild=None)
                await self.CommandTree.sync()
            else:
                _logger.info("Clearing guild-specific commands...")
                for guild in self.guilds:
                    _logger.info(f"{guild.name} (ID: {guild.id}) - Clearing commands...")
                    self.CommandTree.clear_commands(guild=guild)
                    await self.CommandTree.sync(guild=guild)

            _logger.info("All commands cleared successfully.")
        except Exception as e:
            _logger.exception(f"Failed to clear commands: {e}")
