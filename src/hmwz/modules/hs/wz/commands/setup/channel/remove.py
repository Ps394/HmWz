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
    name="channel-remove",
    description=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get(
            "command.description.wz.setup.channel.remove", "-"
        ),
        key="wz.setup.channel.remove.description",
    ),
)
async def remove(interaction: Interaction) -> None:
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
            action="remove",
            registration_channel_id=channel_id,
        )
        if not channels:
            await interaction.followup.send(
                t(interaction, "wz.setup.channel.no_channels"),
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            t(interaction, "wz.setup.channel.select.remove"),
            view=PurgeChannelSelection(
                guild=guild,
                module=module,
                owner_id=interaction.user.id,
                action="remove",
                channels=channels,
                max_values=min(len(channels), PurgeChannel.MAX_PER_REGISTRATION),
                registration_channel_id=channel_id,
            ),
            ephemeral=True,
        )
    except Exception as error:
        logger.exception(
            "%s WZ setup channel remove failed: %s",
            utils.log_interaction(interaction),
            error,
        )
        await interaction.followup.send(
            t(interaction, "wz.setup.channel.error"), ephemeral=True
        )
