import logging

from discord import Forbidden, HTTPException, Interaction, app_commands
from discord.app_commands import checks

from hmwz.configuration import config
from hmwz.i18n import CommandLocalizations, t

from ....module import WzRegistrationModule

logger = logging.getLogger(__name__)


async def remove_autocomplete(
    interaction: Interaction, current: str
) -> list[app_commands.Choice[str]]:
    if not interaction.guild:
        return []

    manager = getattr(interaction.client, "module_manager", None)
    if manager is None:
        return []

    try:
        module: WzRegistrationModule = await manager.get_module(
            interaction.guild, WzRegistrationModule
        )
        configured_roles = await module.roles.get(guild=interaction.guild)
        if not configured_roles:
            return []

        out: list[app_commands.Choice[str]] = []
        for configured in configured_roles:
            role = interaction.guild.get_role(configured.role)
            if role is None:
                continue
            if current.lower() in role.name.lower():
                out.append(app_commands.Choice(name=role.name, value=str(role.id)))
        return out[:25]
    except Exception:
        return []


@checks.has_permissions(manage_roles=True, manage_messages=True, manage_channels=True)
@app_commands.command(
    name="role-remove",
    description=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get(
            "command.description.wz.setup.roles.remove", "-"
        ),
        key="wz.setup.roles.remove.description",
    ),
)
@app_commands.describe(
    role=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get(
            "parameter.description.wz.setup.roles.remove.role", "-"
        ),
        key="wz.setup.roles.remove.role.description",
    )
)
@app_commands.autocomplete(role=remove_autocomplete)
async def remove(interaction: Interaction, role: str):
    await interaction.response.defer(ephemeral=True)
    try:
        if not interaction.guild:
            await interaction.followup.send(
                t(interaction, "wz.setup.roles.remove.error"), ephemeral=True
            )
            return

        manager = getattr(interaction.client, "module_manager", None)
        if manager is None:
            await interaction.followup.send(
                t(interaction, "wz.setup.roles.remove.error"), ephemeral=True
            )
            return

        module: WzRegistrationModule = await manager.get_module(
            interaction.guild, WzRegistrationModule
        )
        role_to_remove = interaction.guild.get_role(int(role))
        if role_to_remove is None:
            await interaction.followup.send(
                t(interaction, "wz.setup.roles.remove.unknown_role"), ephemeral=True
            )
            return

        configured_roles = await module.roles.get(guild=interaction.guild)
        configured_ids = (
            {r.role for r in configured_roles} if configured_roles else set()
        )
        if role_to_remove.id not in configured_ids:
            await interaction.followup.send(
                t(interaction, "wz.setup.roles.remove.unknown_role"), ephemeral=True
            )
            return

        min_roles = int(
            config.get("wz_registration", {}).get("min_registration_roles", 1)
        )
        if len(configured_ids) <= min_roles:
            await interaction.followup.send(
                t(interaction, "wz.setup.roles.remove.min_roles"), ephemeral=True
            )
            return

        for member in interaction.guild.members:
            if member.bot:
                continue
            if role_to_remove in member.roles:
                try:
                    await member.remove_roles(
                        role_to_remove, reason="WZ Registration Role Removal"
                    )
                except (HTTPException, Forbidden) as e:
                    logger.warning(
                        f"Failed removing role {role_to_remove.id} from member {member.id}: {e}"
                    )

        await module.roles.remove(guild=interaction.guild, role=role_to_remove.id)
        await module.registrations.remove(
            guild=interaction.guild, role=role_to_remove.id
        )
        await module.compose_registration_overview(force=True)

        await interaction.followup.send(
            t(
                interaction,
                "wz.setup.roles.remove.success",
                role_name=role_to_remove.name,
            ),
            ephemeral=True,
        )
    except Exception as e:
        logger.exception(f"WZ setup role-remove failed: {e}")
        await interaction.followup.send(
            t(interaction, "wz.setup.roles.remove.unexpected"), ephemeral=True
        )
