import logging

from discord import Interaction, app_commands
from i18n import CommandLocalizations, t

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
        logger.debug("Selectable channels for guild %s: %s", guild.id, [channel.name for channel in channels])

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
        logger.exception(f"WZ purge-channel-add failed: {e}")
        await interaction.followup.send(
            t(interaction, "wz.setup.purge_channel.error"), ephemeral=True
        )
