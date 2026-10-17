import logging

from discord import Interaction, Role, TextChannel, app_commands
from discord.app_commands import checks

from hmwz.configuration import config
from hmwz.i18n import CommandLocalizations, t

from ...module import WzRegistrationModule

logger = logging.getLogger(__name__)


@checks.has_permissions(manage_roles=True, manage_messages=True, manage_channels=True)
@app_commands.command(
    name="configure",
    description=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get(
            "command.description.wz.setup.configure", "-"
        ),
        key="wz.setup.configure.description",
    ),
)
@app_commands.describe(
    channel=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get(
            "parameter.description.wz.setup.configure.channel", "-"
        ),
        key="wz.setup.configure.channel.description",
    ),
    role=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get(
            "parameter.description.wz.setup.configure.role", "-"
        ),
        key="wz.setup.configure.role.description",
    ),
)
async def configure(
    interaction: Interaction, channel: TextChannel, role: Role | None = None
):
    await interaction.response.defer(ephemeral=True)
    try:
        if not interaction.guild:
            await interaction.followup.send(
                t(interaction, "wz.setup.configure.error"), ephemeral=True
            )
            return

        manager = getattr(interaction.client, "module_manager", None)
        if manager is None:
            await interaction.followup.send(
                t(interaction, "wz.setup.configure.error"), ephemeral=True
            )
            return

        module: WzRegistrationModule = await manager.get_module(
            interaction.guild, WzRegistrationModule
        )

        if role and interaction.guild.me and role >= interaction.guild.me.top_role:
            await interaction.followup.send(
                t(interaction, "wz.setup.configure.error_role_hierarchy"),
                ephemeral=True,
            )
            return

        role_count = await module.roles.count(guild=interaction.guild)
        if role is None and role_count == 0:
            await interaction.followup.send(
                t(interaction, "wz.setup.configure.error_no_configured_role"),
                ephemeral=True,
            )
            return

        max_roles = int(
            config.get("wz_registration", {}).get("max_registration_roles", 4)
        )
        if role is not None and role_count >= max_roles:
            await interaction.followup.send(
                t(interaction, "wz.setup.roles.add.max_roles", max_roles=max_roles),
                ephemeral=True,
            )
            return

        ok = await module.registration.upsert(
            guild=interaction.guild, channel_id=channel.id
        )
        if role is not None:
            ok = (
                await module.roles.add(
                    guild=interaction.guild, role=role.id, permanent=False, score=1
                )
            ) and ok

        if not ok:
            await interaction.followup.send(
                t(interaction, "wz.setup.configure.error"), ephemeral=True
            )
            return

        if not await module.purge_channels.remove(
            guild=interaction.guild, channel_id=channel.id
        ):
            logger.error(
                "Failed to remove registration channel %s from the purge list in guild %s.",
                channel.id,
                interaction.guild.id,
            )
            await interaction.followup.send(
                t(interaction, "wz.setup.configure.error"), ephemeral=True
            )
            return

        await module.compose_registration_overview(force=True)
        await interaction.followup.send(
            t(interaction, "wz.setup.configure.success", channel_name=channel.name),
            ephemeral=True,
        )
    except Exception as e:
        logger.exception(f"WZ setup configure failed: {e}")
        await interaction.followup.send(
            t(interaction, "wz.setup.configure.error"), ephemeral=True
        )
