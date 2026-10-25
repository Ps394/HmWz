from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.app_commands import Group, checks, locale_str

from hmwz.i18n import t
from hmwz.modules.queue.module import QueueModule
from hmwz.modules.queue.wizard import (
    QueueConfigView,
    create_draft,
    panel_content,
)

_logger = logging.getLogger(__name__)


class QueueSeasonResetConfirmation(discord.ui.View):
    def __init__(self, module: QueueModule, channel_id: int, owner_id: int) -> None:
        super().__init__(timeout=180)
        self.module = module
        self.channel_id = channel_id
        self.owner_id = owner_id
        self.add_item(QueueSeasonResetButton(self))
        self.add_item(QueueSeasonResetCancelButton(self))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        await interaction.response.send_message(
            t(interaction, "queue.wizard.owner_only"), ephemeral=True
        )
        return False


class QueueSeasonResetButton(discord.ui.Button):
    def __init__(self, view: QueueSeasonResetConfirmation) -> None:
        super().__init__(
            label=t(view.module.guild, "queue.season.reset_confirm"),
            style=discord.ButtonStyle.danger,
        )
        self.reset_view = view

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        succeeded = await self.reset_view.module.reset_season_queue(
            self.reset_view.channel_id
        )
        self.reset_view.stop()
        response_text = t(
            interaction,
            "queue.season.reset" if succeeded else "queue.error.reset_failed",
        )
        message = interaction.message
        if message is None:
            await interaction.followup.send(response_text, ephemeral=True)
            return
        try:
            await message.edit(content=response_text, view=None)
        except discord.NotFound:
            await interaction.followup.send(response_text, ephemeral=True)
        except discord.HTTPException:
            _logger.exception(
                "%s Failed to update the season reset confirmation message.",
                self.reset_view.module.guild.name,
            )
            await interaction.followup.send(response_text, ephemeral=True)


class QueueSeasonResetCancelButton(discord.ui.Button):
    def __init__(self, view: QueueSeasonResetConfirmation) -> None:
        super().__init__(
            label=t(view.module.guild, "queue.season.reset_cancel"),
            style=discord.ButtonStyle.secondary,
        )
        self.reset_view = view

    async def callback(self, interaction: discord.Interaction) -> None:
        self.reset_view.stop()
        await interaction.response.edit_message(
            content=t(interaction, "queue.season.reset_cancelled"),
            view=None,
        )


@checks.has_permissions(manage_channels=True)
class QueueSetupGroup(Group):
    def __init__(self) -> None:
        super().__init__(
            name="setup",
            description=locale_str(
                "Configure queues",
                key="queue.group.description.queue.setup",
            ),
        )
        self.add_command(config)
        self.add_command(remove)
        self.add_command(reset)


@app_commands.command(
    name="config",
    description=locale_str(
        "Configure a queue with an interactive dialog",
        key="queue.command.description.queue.setup.config",
    ),
)
async def config(interaction: discord.Interaction) -> None:
    guild = interaction.guild
    channel = interaction.channel
    manager = getattr(interaction.client, "module_manager", None)
    if guild is None or manager is None or not isinstance(channel, discord.TextChannel):
        await interaction.response.send_message(
            t(interaction, "queue.error.invalid_configuration"), ephemeral=True
        )
        return

    module: QueueModule = await manager.get_module(guild, QueueModule)
    if not await module.sync():
        await interaction.response.send_message(
            t(interaction, "queue.error.configuration_failed"), ephemeral=True
        )
        return
    configuration = await module.queues.get(guild=guild, channel_id=channel.id)
    draft = await create_draft(
        module,
        channel.id,
        interaction.user.id,
        configuration.mode if configuration is not None else "continuous",
        configuration,
    )
    await interaction.response.send_message(
        panel_content(draft, interaction),
        view=QueueConfigView(draft),
        ephemeral=True,
    )


@app_commands.command(
    name="remove",
    description=locale_str(
        "Remove the queue configured in this channel",
        key="queue.command.description.queue.setup.remove",
    ),
)
async def remove(interaction: discord.Interaction) -> None:
    await interaction.response.defer(ephemeral=True)
    guild = interaction.guild
    channel_id = interaction.channel_id
    manager = getattr(interaction.client, "module_manager", None)
    if guild is None or channel_id is None or manager is None:
        await interaction.followup.send(
            t(interaction, "queue.error.not_configured"), ephemeral=True
        )
        return
    module: QueueModule = await manager.get_module(guild, QueueModule)
    configuration = await module.queues.get(guild=guild, channel_id=channel_id)
    if configuration is not None and any(
        run.channel_id == channel_id
        for run in await module.queues.get_active_runs(guild=guild)
    ):
        await interaction.followup.send(
            t(interaction, "queue.error.active_runs"), ephemeral=True
        )
        return
    if not await module.remove_queue(channel_id):
        await interaction.followup.send(
            t(interaction, "queue.error.not_configured"), ephemeral=True
        )
        return
    await interaction.followup.send(
        t(interaction, "queue.setup.removed"), ephemeral=True
    )


@app_commands.command(
    name="reset",
    description=locale_str(
        "Reset season participation, goals, and queue messages",
        key="queue.command.description.queue.setup.reset",
    ),
)
async def reset(interaction: discord.Interaction) -> None:
    guild = interaction.guild
    channel_id = interaction.channel_id
    manager = getattr(interaction.client, "module_manager", None)
    if guild is None or channel_id is None or manager is None:
        await interaction.response.send_message(
            t(interaction, "queue.error.not_configured"), ephemeral=True
        )
        return
    module: QueueModule = await manager.get_module(guild, QueueModule)
    configuration = await module.queues.get(guild=guild, channel_id=channel_id)
    if configuration is None or configuration.mode != "seasons":
        await interaction.response.send_message(
            t(interaction, "queue.error.seasons_only"), ephemeral=True
        )
        return
    await interaction.response.send_message(
        t(interaction, "queue.season.reset_prompt"),
        view=QueueSeasonResetConfirmation(module, channel_id, interaction.user.id),
        ephemeral=True,
    )
