from __future__ import annotations

import logging

from discord import Interaction, app_commands

from hmwz.configuration import MODERATOR_ROLES
from hmwz.i18n import CommandLocalizations, t
from hmwz.ui.messages import send_followup, send_temporary_followup
from hmwz.utils.interactions import log_interaction

from ....models import Channel
from ....module import WzModule
from .selection import ChannelSelection, get_selectable_channels

_logger = logging.getLogger(__name__)


@app_commands.checks.has_any_role(*MODERATOR_ROLES)
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
        manager = getattr(interaction.client, "module_manager", None)
        if guild is None or manager is None:
            await send_temporary_followup(
                interaction, t(interaction, "wz.setup.channel.error")
            )
            return

        module: WzModule = await manager.get_module(guild, WzModule)
        channels = await get_selectable_channels(
            guild=guild,
            module=module,
            action="add",
        )
        configured_count = await module.channels.count(guild=guild)
        max_values = min(
            len(channels),
            Channel.MAX_PER_GUILD - configured_count,
        )
        if max_values <= 0:
            await send_temporary_followup(
                interaction, t(interaction, "wz.setup.channel.no_available_channels")
            )
            return

        view = ChannelSelection(
            guild=guild,
            module=module,
            owner_id=interaction.user.id,
            action="add",
            channels=channels,
            max_values=max_values,
            context=interaction,
        )
        view.message = await send_followup(
            interaction,
            embed=view.selection_embed(interaction),
            view=view,
            ephemeral=True,
            wait=True,
        )
    except Exception as error:
        _logger.exception(
            "%s WZ setup channel add failed: %s",
            log_interaction(interaction),
            error,
        )
        await send_temporary_followup(
            interaction, t(interaction, "wz.setup.channel.error")
        )
