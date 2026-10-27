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


async def _send_ephemeral_status(
    interaction: discord.Interaction, translation_key: str
) -> None:
    try:
        message = t(interaction, translation_key)
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
    except discord.HTTPException:
        _logger.exception(
            "Could not report queue command result for guild %s, channel %s.",
            interaction.guild_id,
            interaction.channel_id,
        )


@checks.has_permissions(manage_channels=True, manage_roles=True)
@app_commands.command(
    name="reset",
    description=locale_str(
        "Reset a completed QS eruption and schedule the next start",
        key="queue.command.description.queue.reset",
    ),
)
async def reset(interaction: discord.Interaction) -> None:
    try:
        await _reset_command(interaction)
    except Exception:
        _logger.exception(
            "QS reset command failed for guild %s, channel %s.",
            interaction.guild_id,
            interaction.channel_id,
        )
        await _send_ephemeral_status(interaction, "queue.reset.failed")


async def _reset_command(interaction: discord.Interaction) -> None:
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
    open_job = await module.queues.get_cleanup_job(guild=guild, channel_id=channel_id)
    if open_job is not None and open_job.operation == "reset":
        if configuration is None:
            await interaction.response.send_message(
                t(interaction, "queue.reset.failed"), ephemeral=True
            )
            return
        try:
            result = await module.resume_reset(configuration, open_job)
        except Exception:
            _logger.exception(
                "%s Could not resume QS reset job %s in channel %s.",
                guild.name,
                open_job.id,
                channel_id,
            )
            result = "failed"
        await interaction.response.send_message(
            t(interaction, f"queue.reset.{result}"), ephemeral=True
        )
        return
    if open_job is not None:
        await interaction.response.send_message(
            t(interaction, "queue.remove.partial"), ephemeral=True
        )
        return
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
            discord_time=(
                discord.utils.format_dt(
                    datetime.fromtimestamp(configuration.next_start_at, timezone.utc),
                    style="F",
                )
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
    try:
        await _remove_command(interaction)
    except Exception:
        _logger.exception(
            "QS remove command failed for guild %s, channel %s.",
            interaction.guild_id,
            interaction.channel_id,
        )
        await _send_ephemeral_status(interaction, "queue.remove.failed")


async def _remove_command(interaction: discord.Interaction) -> None:
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
    try:
        result = await module.remove_queue(channel_id)
    except Exception:
        _logger.error(
            "%s Queue removal failed unexpectedly in channel %s.",
            guild.name,
            channel_id,
            exc_info=True,
        )
        result = "failed"
    await interaction.response.send_message(
        t(interaction, f"queue.remove.{result}"),
        ephemeral=True,
    )
