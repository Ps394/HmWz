from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.app_commands import checks, locale_str

from hmwz.i18n import t
from hmwz.ui.components.ephemeral_view import EphemeralView
from hmwz.modules.queue.module import QueueModule
from hmwz.modules.queue.wizard import (
    QueueConfigView,
    create_draft,
    panel_content,
)

_logger = logging.getLogger(__name__)


class QueueSeasonResetConfirmation(EphemeralView):
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
            t(interaction, "queue.wizard.owner_only"),
            ephemeral=True,
            delete_after=5,
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
        try:
            succeeded = await self.reset_view.module.reset_season_queue(
                self.reset_view.channel_id
            )
        except Exception:
            _logger.exception(
                "%s Failed to reset the queue season.",
                self.reset_view.module.guild.name,
            )
            succeeded = False
        self.reset_view.stop()
        response_text = t(
            interaction,
            "queue.season.reset" if succeeded else "queue.error.reset_failed",
        )
        await self.reset_view.finish(interaction, response_text)


class QueueSeasonResetCancelButton(discord.ui.Button):
    def __init__(self, view: QueueSeasonResetConfirmation) -> None:
        super().__init__(
            label=t(view.module.guild, "queue.season.reset_cancel"),
            style=discord.ButtonStyle.secondary,
        )
        self.reset_view = view

    async def callback(self, interaction: discord.Interaction) -> None:
        self.reset_view.stop()
        await interaction.response.defer()
        await self.reset_view.finish(
            interaction, t(interaction, "queue.season.reset_cancelled")
        )


@checks.has_permissions(manage_channels=True)
@app_commands.command(
    name="setup",
    description=locale_str(
        "Configure a queue with an interactive dialog",
        key="queue.command.description.queue.setup",
    ),
)
async def setup(interaction: discord.Interaction) -> None:
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


@checks.has_permissions(manage_channels=True)
@app_commands.command(
    name="remove",
    description=locale_str(
        "Remove the queue configured in this channel",
        key="queue.command.description.queue.remove",
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


@checks.has_permissions(manage_channels=True)
@app_commands.command(
    name="reset",
    description=locale_str(
        "Reset season participation, goals, and queue messages",
        key="queue.command.description.queue.reset",
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
    view = QueueSeasonResetConfirmation(module, channel_id, interaction.user.id)
    await interaction.response.send_message(
        t(interaction, "queue.season.reset_prompt"),
        view=view,
        ephemeral=True,
    )
    view.message = await interaction.original_response()
