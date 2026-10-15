import logging

from discord import Interaction, app_commands
from i18n import CommandLocalizations, t

from ....models import PurgeChannel
from ....module import WzRegistrationModule
from .selection import PurgeChannelSelection, get_selectable_channels

logger = logging.getLogger(__name__)


@app_commands.command(
    name="purge-channel-remove",
    description=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get(
            "command.description.wz.setup.purge_channel.remove", "-"
        ),
        key="wz.setup.purge_channel.remove.description",
    ),
)
async def remove(interaction: Interaction) -> None:
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
        configured_channels = await module.purge_channels.get(guild=guild)
        if not configured_channels:
            await interaction.followup.send(
                t(interaction, "wz.setup.purge_channel.no_channels"),
                ephemeral=True,
            )
            return

        channels = await get_selectable_channels(
            guild=guild, module=module, action="remove"
        )
        if not channels:
            await interaction.followup.send(
                t(interaction, "wz.setup.purge_channel.no_valid_channels"),
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            t(interaction, "wz.setup.purge_channel.select.remove"),
            view=PurgeChannelSelection(
                guild=guild,
                module=module,
                owner_id=interaction.user.id,
                action="remove",
                channels=channels,
                max_values=PurgeChannel.MAX_PER_GUILD,
            ),
            ephemeral=True,
        )
    except Exception as e:
        logger.exception(f"WZ purge-channel-remove failed: {e}")
        await interaction.followup.send(
            t(interaction, "wz.setup.purge_channel.error"), ephemeral=True
        )
