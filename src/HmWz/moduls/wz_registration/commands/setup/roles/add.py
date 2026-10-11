import logging

from configuration import config
from discord import Interaction, Role, app_commands
from i18n import CommandLocalizations, t

from ....module import WzRegistrationModule

logger = logging.getLogger(__name__)


@app_commands.command(
    name="role-add",
    description=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get(
            "command.description.wz.setup.roles.add", "-"
        ),
        key="wz.setup.roles.add.description",
    ),
)
@app_commands.describe(
    role=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get(
            "parameter.description.wz.setup.roles.add.role", "-"
        ),
        key="wz.setup.roles.add.role.description",
    ),
    permanent=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get(
            "parameter.description.wz.setup.roles.add.permanent", "-"
        ),
        key="wz.setup.roles.add.permanent.description",
    ),
)
async def add(interaction: Interaction, role: Role, permanent: bool | None = False):
    await interaction.response.defer(ephemeral=True)
    try:
        if not interaction.guild:
            await interaction.followup.send(
                t(interaction, "wz.setup.roles.add.error"), ephemeral=True
            )
            return

        if interaction.guild.me and role >= interaction.guild.me.top_role:
            await interaction.followup.send(
                t(interaction, "wz.setup.roles.add.error.role_hierarchy"),
                ephemeral=True,
            )
            return

        manager = getattr(interaction.client, "module_manager", None)
        if manager is None:
            await interaction.followup.send(
                t(interaction, "wz.setup.roles.add.error"), ephemeral=True
            )
            return

        module: WzRegistrationModule = await manager.get_module(
            interaction.guild, WzRegistrationModule
        )
        max_roles = int(
            config.get("wz_registration", {}).get("max_registration_roles", 4)
        )
        role_count = await module.roles.count(guild=interaction.guild)

        if role_count >= max_roles:
            await interaction.followup.send(
                t(interaction, "wz.setup.roles.add.max_roles", max_roles=max_roles),
                ephemeral=True,
            )
            return

        if await module.roles.add(
            guild=interaction.guild, role=role.id, permanent=bool(permanent), score=1
        ):
            await module.compose_registration_overview(force=True)
            await interaction.followup.send(
                t(interaction, "wz.setup.roles.add.success", role_name=role.name),
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            t(interaction, "wz.setup.roles.add.error"), ephemeral=True
        )
    except Exception as e:
        logger.exception(f"WZ setup role-add failed: {e}")
        await interaction.followup.send(
            t(interaction, "wz.setup.roles.add.error"), ephemeral=True
        )
