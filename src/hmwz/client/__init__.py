"""Discord client implementation and command registration."""

from __future__ import annotations

import asyncio
import logging
from asyncio.log import logger

import discord

from hmwz import events, exceptions, modules, sqlite_db
from hmwz.configuration import config
from hmwz.emojis import EmojiUploader
from hmwz.i18n import CommandTranslator, t
from hmwz.ui.messages import send_followup, send_initial_response
from hmwz.utils.interactions import log_interaction

from . import commands, monitoring, repositories

_logger = logging.getLogger(__name__)

__all__ = [
    "Client",
    "commands",
    "events",
    "exceptions",
    "repositories",
    "sqlite_db",
]


class Client(discord.Client):
    """Discord client that manages persistence, commands, and guild modules."""

    registered_commands: int = 0

    def __init__(
        self,
        *,
        intents: discord.Intents = discord.Intents.default(),
        global_command_sync: bool | None = True,
        **options,
    ):
        super().__init__(intents=intents, **options)
        self.emoji_uploader = EmojiUploader(self)
        self._database: sqlite_db.Database = sqlite_db.Database(
            folder=config["database"]["folder"], filename=config["database"]["filename"]
        )
        self._servers: repositories.ServerRepository = repositories.ServerRepository(
            self._database
        )
        self.module_manager = modules.Manager(self)

        self.CommandTree = discord.app_commands.CommandTree(self)
        self.global_command_sync = global_command_sync
        self._commands_initialized = False

    async def setup_hook(self):
        """
        Prepare persistence, translations, commands, and background monitoring.
        """
        if not await self._database.execute(self._servers.table):
            raise RuntimeError("Failed to create the server database table.")
        if not await self._servers.ensure_schema():
            raise RuntimeError("Failed to migrate the server database schema.")
        if not await self._database.remove_legacy_tables():
            raise RuntimeError("Failed to remove legacy database tables.")
        if not await self._servers.migrate_legacy_servers():
            raise RuntimeError("Failed to migrate legacy server records.")
        await self.CommandTree.set_translator(CommandTranslator())

        await self.emoji_uploader.sync()
        await self.register_commands()

        asyncio.create_task(monitoring.resource_monitor_loop())

        return await super().setup_hook()

    async def close(self) -> None:
        """Stop module workers before disconnecting the Discord client."""
        await self.module_manager.close()
        await super().close()

    async def get_guild_timezone(self, guild_id: int) -> str:
        """Return the configured IANA timezone for a guild."""
        return await self._servers.get_timezone(guild_id)

    async def set_guild_timezone(
        self, guild: discord.Guild, timezone_name: str
    ) -> bool:
        """Set the configured IANA timezone for a guild."""
        return await self._servers.set_timezone(guild, timezone_name)

    async def on_guild_timezone_update(self, guild: discord.Guild) -> bool:
        """Refresh guild modules that render local schedule information."""
        return await self.module_manager.on_guild_timezone_update(guild)

    async def on_disconnect(self) -> None:
        """Prevent module workers from catching up missed gateway deadlines."""
        await self.module_manager.on_disconnect()

    async def on_ready(self):
        """
        Initialize guild modules after the Discord client becomes ready.
        """
        if self.user is None:
            raise RuntimeError("Client became ready without an authenticated user.")

        _logger.info(
            "Logged in as %s / %s (ID: %s)",
            self.user.name,
            self.user.display_name,
            self.user.id,
        )
        _logger.info("------")

        if not self._commands_initialized:
            await self.clear_commands()
            await self.sync_commands_guilds()
            await self.sync_commands_global()
            self._commands_initialized = True

        for guild in self.guilds:
            if not await self._servers.add(guild=guild):
                _logger.error(
                    "%s Failed to save guild name.", self._servers.log_prefix(guild)
                )
                continue
        await self.module_manager.startup()

    async def on_guild_join(self, guild: discord.Guild):
        """
        Persist a guild and initialize its modules when the bot joins it.

        Args:
            guild: The guild joined by the bot.
        """
        try:
            if not await self._servers.add(guild=guild):
                raise RuntimeError("Failed to save guild name.")
            await self.module_manager.on_guild_join(guild)
            _logger.info(f"{guild.name} ({guild.id}) - Guild added to database.")
        except Exception as e:
            _logger.exception(
                f"{guild.name} ({guild.id}) - Failed to add guild to database: {e}"
            )

    async def on_guild_remove(self, guild: discord.Guild):
        """
        Notify modules and remove a guild when the bot leaves it.

        Args:
            guild: The guild left by the bot.
        """
        try:
            await self.module_manager.on_guild_remove(guild)
            await self._servers.remove(guild=guild)
            _logger.info(f"{guild.name} ({guild.id}) - Guild removed from database.")
        except Exception as e:
            _logger.exception(
                f"{guild.name} ({guild.id}) - Failed to remove guild from database: {e}"
            )

    async def on_guild_update(self, before: discord.Guild, after: discord.Guild):
        """Persist guild name changes and notify guild modules.

        Args:
            before: The guild state before the update.
            after: The guild state after the update.
        """
        if not await self._servers.add(guild=after):
            _logger.error(
                "%s Failed to update guild name from %s.",
                self._servers.log_prefix(after),
                before.name,
            )
            return
        await self.module_manager.on_guild_update(before, after)

    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        """
        Notify modules that a guild channel was deleted.

        Args:
            channel: The deleted guild channel.
        """
        _logger.info(
            "%s Channel deleted: %s (%s).",
            self._servers.log_prefix(channel.guild),
            channel.name,
            channel.id,
        )
        await self.module_manager.on_guild_channel_delete(channel)

    async def on_guild_channel_update(
        self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel
    ):
        """
        Notify modules that a guild channel was updated.

        Args:
            before: The channel state before the update.
            after: The channel state after the update.
        """
        await self.module_manager.on_guild_channel_update(before, after)

    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        """
        Notify modules that a guild channel was created.

        Args:
            channel: The newly created guild channel.
        """
        await self.module_manager.on_guild_channel_create(channel)

    async def on_guild_role_update(self, before: discord.Role, after: discord.Role):
        """
        Notify modules that a guild role was updated.

        Args:
            before: The role state before the update.
            after: The role state after the update.
        """
        await self.module_manager.on_guild_role_update(before, after)

    async def on_guild_role_delete(self, role: discord.Role):
        """
        Notify modules that a guild role was deleted.

        Args:
            role: The deleted guild role.
        """
        await self.module_manager.on_guild_role_delete(role)

    async def on_raw_member_remove(self, payload: events.RawMemberRemoveEvent):
        """
        Notify modules that a member left or was removed from a guild.

        Args:
            payload: The raw member-removal event.
        """
        await self.module_manager.on_raw_member_remove(payload)

    async def on_member_update(self, before: discord.Member, after: discord.Member):
        """
        Notify modules that a guild member was updated.

        Args:
            before: The member state before the update.
            after: The member state after the update.
        """
        await self.module_manager.on_member_update(before, after)

    async def on_raw_thread_delete(self, payload: events.RawThreadDeleteEvent) -> None:
        """Notify modules that a persistent thread was deleted."""
        await self.module_manager.on_raw_thread_delete(payload)

    async def on_raw_message_delete(self, payload: events.RawMessageDeleteEvent):
        """
        Notify modules that a message was deleted.

        Args:
            payload: The raw message-deletion event.
        """
        await self.module_manager.on_raw_message_delete(payload)

    async def on_raw_bulk_message_delete(
        self, payload: events.RawBulkMessageDeleteEvent
    ):
        """
        Notify modules that multiple messages were deleted.

        Args:
            payload: The raw bulk message-deletion event.
        """
        await self.module_manager.on_raw_bulk_message_delete(payload)

    async def on_application_command_error(
        self,
        interaction: discord.Interaction,
        error: discord.app_commands.AppCommandError,
    ):
        """
        Log an application-command error and send a localized response.

        Args:
            interaction: Interaction that raised the error.
            error: Application-command error to handle.
        """
        log_context = f"{log_interaction(interaction)} - Command: {interaction.command}"

        send = (
            send_followup if interaction.response.is_done() else send_initial_response
        )
        try:
            if isinstance(error, discord.app_commands.MissingPermissions):
                message = t(interaction, "command.error.permissions")
                logger.warning(f"{log_context} - User missing permissions: {error}")
            elif isinstance(error, discord.app_commands.BotMissingPermissions):
                message = t(interaction, "command.error.bot_permissions")
                logger.error(f"{log_context} - Bot missing permissions: {error}")
            elif isinstance(error, discord.app_commands.CommandOnCooldown):
                message = t(
                    interaction,
                    "command.error.cooldown",
                    retry_after=f"{error.retry_after:.1f}",
                )
                logger.info(f"{log_context} - Command on cooldown: {error}")

            else:
                message = t(interaction, "command.error.unexpected")
                logger.exception(f"{log_context} - Unexpected error: {error}")
            await send(interaction, message, ephemeral=True)
        except discord.HTTPException as e:
            if e.code in (10062, 40060):
                logger.warning(
                    "%s - Could not send error response because the interaction "
                    "is expired or already acknowledged: %s",
                    log_context,
                    e,
                )
            else:
                logger.exception(
                    "%s - Failed to send error message: %s", log_context, e
                )
        except Exception as e:
            logger.exception(f"{log_context} - Failed to send error message: {e}")

    def add_command(
        self,
        command: discord.app_commands.Command
        | discord.app_commands.Group
        | discord.app_commands.ContextMenu,
    ) -> None:
        """
        Add a command, group, or context menu to the command tree.

        Args:
            command: Application command to register.
        """
        if isinstance(command, discord.app_commands.Group):
            for subcommand in command.commands:
                if isinstance(subcommand, discord.app_commands.Command):
                    _logger.debug(
                        f"Registered subcommand: {subcommand.name} in group {command.name}"
                    )
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
        Register built-in commands and install the global error handler.
        """
        from hmwz.modules.hs.account.commands import AccountGroup
        from hmwz.modules.donation.commands import DonationGroup
        from hmwz.modules.hs.qs.commands import QsGroup
        from hmwz.modules.hs.wz.commands import WzGroup
        #from hmwz.modules.queue.commands import QueueGroup
        from hmwz.modules.registration.commands import RegistrationGroup

        _logger.info("Registering commands...")

        self.add_command(commands.AboutBot)
        self.add_command(commands.Purge)
        self.add_command(commands.SetTimezone)
        self.add_command(AccountGroup())
        self.add_command(WzGroup())
        self.add_command(QsGroup())
        self.add_command(RegistrationGroup())
        self.add_command(DonationGroup())
        #self.add_command(QueueGroup())

        @self.CommandTree.error
        async def tree_on_error(
            interaction: discord.Interaction,
            error: discord.app_commands.AppCommandError,
        ):
            """
            Delegate command-tree failures to the client's error handler.

            Args:
                interaction: Interaction that raised the error.
                error: Application-command error to handle.
            """
            try:
                await self.on_application_command_error(interaction, error)
            except Exception:
                _logger.exception(f"Error while handling app command error: {error}")

        _logger.info(f"Total commands registered: {self.registered_commands}")

    async def sync_commands_global(self):
        """Synchronize application commands globally when configured."""
        if self.global_command_sync is True:
            try:
                await self.CommandTree.sync()
                _logger.info("Global commands synced successfully.")
            except Exception as e:
                _logger.exception(f"Failed to sync global commands: {e}")

    async def sync_commands_guilds(self):
        """
        Synchronize application commands separately for each guild when configured.
        """
        if self.global_command_sync is False:
            for guild in self.guilds:
                try:
                    self.CommandTree.copy_global_to(guild=guild)
                    await self.CommandTree.sync(guild=guild)
                    _logger.info(
                        f"{guild.name} (ID: {guild.id}) - Commands synced successfully."
                    )
                except Exception as e:
                    _logger.exception(
                        f"{guild.name} (ID: {guild.id}) - Failed to sync commands: {e}"
                    )

    async def clear_commands(self):
        """
        Clear global or guild-specific commands before registering current commands.
        """
        try:
            if not self.global_command_sync:
                _logger.info("Clearing global commands...")
                self.CommandTree.clear_commands(guild=None)
                await self.CommandTree.sync()
            else:
                _logger.info("Clearing guild-specific commands...")
                for guild in self.guilds:
                    _logger.info(
                        f"{guild.name} (ID: {guild.id}) - Clearing commands..."
                    )
                    self.CommandTree.clear_commands(guild=guild)
                    await self.CommandTree.sync(guild=guild)

            _logger.info("All commands cleared successfully.")
        except Exception as e:
            _logger.exception(f"Failed to clear commands: {e}")
