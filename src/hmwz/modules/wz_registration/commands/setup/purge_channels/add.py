import logging

from discord import Interaction, app_commands

from hmwz import utils
from hmwz.i18n import CommandLocalizations, t

from ....models import PurgeChannel
from ....module import WzRegistrationModule
from .selection import PurgeChannelSelection, get_selectable_channels

logger = logging.getLogger(__name__)


@app_commands.command(
    name="purge-channel-add",
    description=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get(
            "command.description.wz.setup.purge_channel.add", "-"
        ),
        key="wz.setup.purge_channel.add.description",
    ),
)
async def add(interaction: Interaction) -> None:
    await interaction.response.defer(ephemeral=True)
    try:
        guild = interaction.guild
        if guild is None:
            await interaction.followup.send(
                t(interaction, "wz.setup.purge_channel.error"), ephemeral=True
            )
            return

        manager = getattr(interaction.client, "module_manager", None)
        if manager is None:
            await interaction.followup.send(
                t(interaction, "wz.setup.purge_channel.error"), ephemeral=True
            )
            return

        module: WzRegistrationModule = await manager.get_module(
            guild, WzRegistrationModule
        )
        channels = await get_selectable_channels(
            guild=guild, module=module, action="add"
        )
        logger.debug(
            "Selectable channels for guild %s (%s): %s",
            guild.name,
            guild.id,
            [f"{channel.name} ({channel.id})" for channel in channels],
        )

        if not channels:
            await interaction.followup.send(
                t(interaction, "wz.setup.purge_channel.no_available_channels"),
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            t(interaction, "wz.setup.purge_channel.select.add"),
            view=PurgeChannelSelection(
                guild=guild,
                module=module,
                owner_id=interaction.user.id,
                action="add",
                channels=channels,
                max_values=PurgeChannel.MAX_PER_GUILD,
            ),
            ephemeral=True,
        )
    except Exception as e:
        logger.exception(
            "%s WZ purge-channel-add failed: %s", utils.log_interaction(interaction), e
        )
        await interaction.followup.send(
            t(interaction, "wz.setup.purge_channel.error"), ephemeral=True
        )
