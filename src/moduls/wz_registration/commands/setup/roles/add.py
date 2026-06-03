import logging
from typing import Optional

from discord import app_commands, Interaction, Role
from discord.app_commands import checks

from configuration import config
from i18n import CommandLocalizations, t

from ....module import WzRegistrationModule

logger = logging.getLogger(__name__)


@checks.has_permissions(manage_roles=True, manage_messages=True, manage_channels=True)
@app_commands.command(
    name="role-add",
    description=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get("wz.setup.roles.add.description", "-"),
        key="wz.setup.roles.add.description",
    ),
)
@app_commands.describe(
    role=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get("wz.setup.roles.add.role.description", "-"),
        key="wz.setup.roles.add.role.description",
    ),
    permanent=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get("wz.setup.roles.add.permanent.description", "-"),
        key="wz.setup.roles.add.permanent.description",
    ),
)
async def add(interaction: Interaction, role: Role, permanent: Optional[bool] = False):
    await interaction.response.defer(ephemeral=True)
    try:
        if not interaction.guild:
            await interaction.followup.send(t(interaction, "wz.setup.roles.add.error"), ephemeral=True)
            return

        if interaction.guild.me and role >= interaction.guild.me.top_role:
            await interaction.followup.send(
                t(interaction, "wz.setup.roles.add.error.role_hierarchy"), ephemeral=True
            )
            return

        manager = getattr(interaction.client, "module_manager", None)
        if manager is None:
            await interaction.followup.send(t(interaction, "wz.setup.roles.add.error"), ephemeral=True)
            return

        module: WzRegistrationModule = await manager.get_module(interaction.guild, WzRegistrationModule)
        max_roles = int(config.get("wz_registration", {}).get("max_registration_roles", 4))
        role_count = await module.roles.count(guild=interaction.guild)

        if role_count >= max_roles:
            await interaction.followup.send(
                t(interaction, "wz.setup.roles.add.max_roles", max_roles=max_roles),
                ephemeral=True,
            )
            return

        if await module.roles.add(guild=interaction.guild, role=role.id, permanent=bool(permanent), score=1):
            await module.compose_registration_overview(force=True)
            await interaction.followup.send(
                t(interaction, "wz.setup.roles.add.success", role_name=role.name),
                ephemeral=True,
            )
            return

        await interaction.followup.send(t(interaction, "wz.setup.roles.add.error"), ephemeral=True)
    except Exception as e:
        logger.exception(f"WZ setup role-add failed: {e}")
        await interaction.followup.send(t(interaction, "wz.setup.roles.add.error"), ephemeral=True)
