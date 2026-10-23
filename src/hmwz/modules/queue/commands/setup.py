from __future__ import annotations

import discord
from discord import app_commands
from discord.app_commands import Group, checks, locale_str

from hmwz.i18n import t
from hmwz.modules.queue.module import QueueModule


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
        self.add_command(configure)
        self.add_command(remove)


@app_commands.command(
    name="configure",
    description=locale_str(
        "Configure a queue in this channel",
        key="queue.command.description.queue.setup.configure",
    ),
)
@app_commands.describe(
    name=locale_str("Queue name", key="queue.parameter.description.queue.name"),
    max_players=locale_str(
        "Members per run (1-100)",
        key="queue.parameter.description.queue.max_players",
    ),
    min_players=locale_str(
        "Set to 0 or equal to the maximum",
        key="queue.parameter.description.queue.min_players",
    ),
    confirmation_delay_minutes=locale_str(
        "Minutes after run start before confirmations open",
        key="queue.parameter.description.queue.confirmation_delay_minutes",
    ),
    reminder_interval_minutes=locale_str(
        "Minutes between thread reminders",
        key="queue.parameter.description.queue.reminder_interval_minutes",
    ),
)
async def configure(
    interaction: discord.Interaction,
    name: app_commands.Range[str, 1, 100],
    max_players: app_commands.Range[int, 1, 100],
    min_players: app_commands.Range[int, 0, 100] = 0,
    confirmation_delay_minutes: app_commands.Range[int, 0, 10080] = 30,
    reminder_interval_minutes: app_commands.Range[int, 1, 1440] = 15,
) -> None:
    await interaction.response.defer(ephemeral=True)
    guild = interaction.guild
    channel = interaction.channel
    manager = getattr(interaction.client, "module_manager", None)
    cleaned_name = name.strip()
    if (
        guild is None
        or manager is None
        or not isinstance(channel, discord.TextChannel)
        or not cleaned_name
        or min_players not in (0, max_players)
    ):
        await interaction.followup.send(
            t(interaction, "queue.error.invalid_configuration"), ephemeral=True
        )
        return

    module: QueueModule = await manager.get_module(guild, QueueModule)
    if not await module.configure(
        channel_id=channel.id,
        name=cleaned_name,
        min_players=min_players,
        max_players=max_players,
        confirmation_delay_minutes=confirmation_delay_minutes,
        reminder_interval_minutes=reminder_interval_minutes,
    ):
        await interaction.followup.send(
            t(interaction, "queue.error.configuration_failed"), ephemeral=True
        )
        return
    await interaction.followup.send(
        t(
            interaction,
            "queue.setup.configured",
            name=cleaned_name,
            channel=channel.mention,
        ),
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
