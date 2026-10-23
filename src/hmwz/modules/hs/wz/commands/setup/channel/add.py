import logging

from discord import Interaction, app_commands

from hmwz import utils
from hmwz.i18n import CommandLocalizations, t

from ....models import PurgeChannel
from ....module import WzRegistrationModule
from .selection import PurgeChannelSelection, get_selectable_channels

logger = logging.getLogger(__name__)


@app_commands.checks.has_any_role("Offiziere", "Moderator")
@app_commands.command(
    name="add",
    description=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get(
            "command.description.wz.channel.add", "-"
        ),
        key="wz.channel.add.description",
    ),
)
async def add(interaction: Interaction) -> None:
    await interaction.response.defer(ephemeral=True)
    try:
        guild = interaction.guild
        channel_id = interaction.channel_id
        manager = getattr(interaction.client, "module_manager", None)
        if guild is None or channel_id is None or manager is None:
            await interaction.followup.send(
                t(interaction, "wz.setup.channel.error"), ephemeral=True
            )
            return

        module: WzRegistrationModule = await manager.get_module(
            guild, WzRegistrationModule
        )
        if await module.registration.get(guild=guild, channel_id=channel_id) is None:
            await interaction.followup.send(
                t(interaction, "wz.setup.channel.error"), ephemeral=True
            )
            return

        channels = await get_selectable_channels(
            guild=guild,
            module=module,
            action="add",
            registration_channel_id=channel_id,
        )
        configured_count = await module.purge_channels.count(
            guild=guild, registration_channel_id=channel_id
        )
        max_values = min(
            len(channels),
            PurgeChannel.MAX_PER_REGISTRATION - configured_count,
        )
        if max_values <= 0:
            await interaction.followup.send(
                t(interaction, "wz.setup.channel.no_available_channels"),
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            t(interaction, "wz.setup.channel.select.add"),
            view=PurgeChannelSelection(
                guild=guild,
                module=module,
                owner_id=interaction.user.id,
                action="add",
                channels=channels,
                max_values=max_values,
                registration_channel_id=channel_id,
            ),
            ephemeral=True,
        )
    except Exception as error:
        logger.exception(
            "%s WZ setup channel add failed: %s",
            utils.log_interaction(interaction),
            error,
        )
        await interaction.followup.send(
            t(interaction, "wz.setup.channel.error"), ephemeral=True
        )
