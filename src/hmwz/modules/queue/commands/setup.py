from __future__ import annotations

import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.app_commands import checks, locale_str

from hmwz.i18n import t
from hmwz.modules.queue.module import QueueModule
from hmwz.modules.queue.reset import QueueResetDraft, QueueResetView
from hmwz.modules.queue.wizard import QueueSetupDraft, QueueSetupView, setup_content

_logger = logging.getLogger(__name__)


@checks.has_permissions(manage_channels=True, manage_roles=True)
@app_commands.command(
    name="reset",
    description=locale_str(
        "Reset a completed QS eruption and schedule the next start",
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
    eruption = await module.queues.get_latest_eruption(
        guild=guild, channel_id=channel_id
    )
    if configuration is None or eruption is None:
        await interaction.response.send_message(
            t(interaction, "queue.error.not_configured"), ephemeral=True
        )
        return
    if eruption.ends_at > discord.utils.utcnow().timestamp():
        await interaction.response.send_message(
            t(interaction, "queue.error.active_eruption"), ephemeral=True
        )
        return
    draft = QueueResetDraft(
        module=module,
        configuration=configuration,
        eruption=eruption,
        owner_id=interaction.user.id,
    )
    await interaction.response.send_message(
        t(
            interaction,
            "queue.reset.panel",
            start=(
                datetime.fromtimestamp(configuration.next_start_at, timezone.utc)
                .astimezone(ZoneInfo(configuration.timezone))
                .strftime("%Y-%m-%d %H:%M")
                if configuration.next_start_at is not None
                else t(interaction, "queue.reset.not_set")
            ),
            timezone=configuration.timezone,
        ),
        view=QueueResetView(draft),
        ephemeral=True,
    )


@checks.has_permissions(manage_channels=True, manage_roles=True)
@app_commands.command(
    name="setup",
    description=locale_str(
        "Configure QS eruption phases",
        key="queue.command.description.queue.setup",
    ),
)
async def setup(interaction: discord.Interaction) -> None:
    guild = interaction.guild
    channel = interaction.channel
    manager = getattr(interaction.client, "module_manager", None)
    if guild is None or manager is None or not isinstance(channel, discord.TextChannel):
        await interaction.response.send_message(
            t(interaction, "queue.error.invalid_configuration"),
            ephemeral=True,
        )
        return

    module: QueueModule = await manager.get_module(guild, QueueModule)
    if not await module.sync():
        await interaction.response.send_message(
            t(interaction, "queue.error.configuration_failed"),
            ephemeral=True,
        )
        return
    configuration = await module.queues.get(guild=guild, channel_id=channel.id)
    draft = QueueSetupDraft(
        module=module,
        channel_id=channel.id,
        owner_id=interaction.user.id,
        configuration=configuration,
    )
    view = QueueSetupView(draft)
    await interaction.response.send_message(
        setup_content(draft, interaction),
        view=view,
        ephemeral=True,
    )


@checks.has_permissions(manage_channels=True)
@app_commands.command(
    name="remove",
    description=locale_str(
        "Remove the QS phase queue configuration in this channel",
        key="queue.command.description.queue.remove",
    ),
)
async def remove(interaction: discord.Interaction) -> None:
    guild = interaction.guild
    channel_id = interaction.channel_id
    manager = getattr(interaction.client, "module_manager", None)
    if guild is None or channel_id is None or manager is None:
        await interaction.response.send_message(
            t(interaction, "queue.error.not_configured"),
            ephemeral=True,
        )
        return
    module: QueueModule = await manager.get_module(guild, QueueModule)
    configuration = await module.queues.get(guild=guild, channel_id=channel_id)
    if configuration is None or configuration.mode != "qs_phases":
        await interaction.response.send_message(
            t(interaction, "queue.error.not_configured"),
            ephemeral=True,
        )
        return
    current = await module.queues.get_current_eruption(
        guild=guild,
        channel_id=channel_id,
        now=discord.utils.utcnow().timestamp(),
    )
    if current is not None:
        await interaction.response.send_message(
            t(interaction, "queue.error.active_eruption"),
            ephemeral=True,
        )
        return
    if not await module.remove_queue(channel_id):
        _logger.error(
            "%s Failed to remove QS queue configuration in channel %s.",
            guild.name,
            channel_id,
        )
        await interaction.response.send_message(
            t(interaction, "queue.error.remove_failed"),
            ephemeral=True,
        )
        return
    await interaction.response.send_message(
        t(interaction, "queue.setup.removed"),
        ephemeral=True,
    )
