import logging

from discord import Forbidden, HTTPException, Interaction, app_commands
from hmwz import utils
from hmwz.configuration import wz_registration_config
from hmwz.i18n import CommandLocalizations, t

from hmwz.modules.hs.wz.module import WzRegistrationModule

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
        configured_roles = await module.roles.get(
            guild=interaction.guild, channel_id=interaction.channel_id
        )
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


@app_commands.checks.has_any_role("Offiziere", "Moderator")
@app_commands.command(
    name="roles-delete",
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
        channel_id = interaction.channel_id
        if channel_id is None:
            await interaction.followup.send(
                t(interaction, "wz.setup.roles.remove.error"), ephemeral=True
            )
            return
        role_to_remove = interaction.guild.get_role(int(role))
        if role_to_remove is None:
            await interaction.followup.send(
                t(interaction, "wz.setup.roles.remove.unknown_role"), ephemeral=True
            )
            return

        configured_roles = await module.roles.get(
            guild=interaction.guild, channel_id=channel_id
        )
        configured_ids = (
            {r.role for r in configured_roles} if configured_roles else set()
        )
        if role_to_remove.id not in configured_ids:
            await interaction.followup.send(
                t(interaction, "wz.setup.roles.remove.unknown_role"), ephemeral=True
            )
            return

        min_roles = int(wz_registration_config().get("min_registration_roles", 1))
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
                        f"Failed removing role {role_to_remove.name} "
                        f"({role_to_remove.id}) from member {member.name} / "
                        f"{member.display_name} ({member.id}) in guild "
                        f"{interaction.guild.name} ({interaction.guild.id}): {e}"
                    )

        await module.roles.remove(
            guild=interaction.guild,
            role=role_to_remove.id,
            channel_id=channel_id,
        )
        await module.registrations.remove(
            guild=interaction.guild,
            role=role_to_remove.id,
            channel_id=channel_id,
        )
        await module.compose_registration_overview(force=True, channel_id=channel_id)

        await interaction.followup.send(
            t(
                interaction,
                "wz.setup.roles.remove.success",
                role_name=role_to_remove.name,
            ),
            ephemeral=True,
        )
    except Exception as e:
        logger.exception(
            "%s WZ setup role-remove failed: %s", utils.log_interaction(interaction), e
        )
        await interaction.followup.send(
            t(interaction, "wz.setup.roles.remove.unexpected"), ephemeral=True
        )
