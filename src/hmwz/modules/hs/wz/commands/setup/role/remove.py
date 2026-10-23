import logging

import discord
from discord import app_commands

from hmwz import utils
from hmwz.configuration import wz_registration_config
from hmwz.i18n import CommandLocalizations, t
from hmwz.modules.hs.wz.module import WzRegistrationModule

from .selection import SetupRoleSelection

logger = logging.getLogger(__name__)


@app_commands.checks.has_any_role("Offiziere", "Moderator")
@app_commands.command(
    name="remove",
    description=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get(
            "command.description.wz.role.remove", "-"
        ),
        key="wz.role.remove.description",
    ),
)
async def remove(interaction: discord.Interaction) -> None:
    await interaction.response.defer(ephemeral=True)
    try:
        guild = interaction.guild
        channel_id = interaction.channel_id
        manager = getattr(interaction.client, "module_manager", None)
        if guild is None or channel_id is None or manager is None:
            await interaction.followup.send(
                t(interaction, "wz.setup.role.error"), ephemeral=True
            )
            return

        module: WzRegistrationModule = await manager.get_module(
            guild, WzRegistrationModule
        )
        if await module.registration.get(guild=guild, channel_id=channel_id) is None:
            await interaction.followup.send(
                t(interaction, "wz.setup.role.registration_required"),
                ephemeral=True,
            )
            return

        configured_roles = await module.roles.get(guild=guild, channel_id=channel_id)
        roles = [
            role
            for record in configured_roles or ()
            if (role := guild.get_role(record.role)) is not None
        ]
        min_roles = int(wz_registration_config().get("min_registration_roles", 1))
        if not roles:
            await interaction.followup.send(
                t(interaction, "wz.setup.role.no_configured_roles"),
                ephemeral=True,
            )
            return
        max_selected = len(roles) - min_roles
        if max_selected <= 0:
            await interaction.followup.send(
                t(interaction, "wz.setup.role.min_roles"), ephemeral=True
            )
            return

        roles.sort(key=lambda role: (role.name.casefold(), role.id))
        await interaction.followup.send(
            t(interaction, "wz.setup.role.select.remove"),
            view=SetupRoleSelection(
                guild=guild,
                module=module,
                owner_id=interaction.user.id,
                action="remove",
                channel_id=channel_id,
                roles=roles,
                max_selected=max_selected,
                permanent=False,
                context=interaction,
            ),
            ephemeral=True,
        )
    except Exception as error:
        logger.exception(
            "%s WZ setup role remove failed: %s",
            utils.log_interaction(interaction),
            error,
        )
        await interaction.followup.send(
            t(interaction, "wz.setup.role.error"), ephemeral=True
        )
