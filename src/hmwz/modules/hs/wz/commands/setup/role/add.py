import logging

import discord
from discord import app_commands

from hmwz.configuration import wz_registration_config
from hmwz.i18n import CommandLocalizations, t
from hmwz.utils.interactions import log_interaction
from hmwz.modules.hs.wz.module import WzRegistrationModule

from .selection import SetupRoleSelection

logger = logging.getLogger(__name__)


@app_commands.checks.has_any_role("Offiziere", "Moderator")
@app_commands.command(
    name="add",
    description=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get("command.description.wz.role.add", "-"),
        key="wz.role.add.description",
    ),
)
@app_commands.describe(
    permanent=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get(
            "parameter.description.wz.role.add.permanent", "-"
        ),
        key="wz.role.add.permanent.description",
    )
)
async def add(interaction: discord.Interaction, permanent: bool = False) -> None:
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

        configured_roles = await module.roles.get(guild=guild)
        configured_ids = {record.role for record in configured_roles or ()}
        current_roles = await module.roles.get(guild=guild, channel_id=channel_id)
        current_ids = {record.role for record in current_roles or ()}
        max_roles = int(wz_registration_config().get("max_registration_roles", 4))
        available_roles = [
            role
            for role in guild.roles
            if role.id not in configured_ids
            and not role.is_default()
            and not role.managed
            and (guild.me is None or role < guild.me.top_role)
        ]
        available_roles.sort(key=lambda role: (role.name.casefold(), role.id))
        slots = max_roles - len(current_ids)
        if not available_roles or slots <= 0:
            await interaction.followup.send(
                t(
                    interaction,
                    "wz.setup.role.no_available_roles"
                    if slots > 0
                    else "wz.setup.role.max_roles",
                    max_roles=max_roles,
                ),
                ephemeral=True,
            )
            return

        view = SetupRoleSelection(
            guild=guild,
            module=module,
            owner_id=interaction.user.id,
            action="add",
            channel_id=channel_id,
            roles=available_roles,
            max_selected=slots,
            permanent=permanent,
            context=interaction,
        )
        view.message = await interaction.followup.send(
            t(interaction, "wz.setup.role.select.add"),
            view=view,
            ephemeral=True,
            wait=True,
        )
    except Exception as error:
        logger.exception(
            "%s WZ setup role add failed: %s",
            log_interaction(interaction),
            error,
        )
        await interaction.followup.send(
            t(interaction, "wz.setup.role.error"), ephemeral=True
        )
