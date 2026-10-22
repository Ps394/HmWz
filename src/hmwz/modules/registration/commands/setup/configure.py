import logging

from discord import Interaction, Role, app_commands
from hmwz import utils
from hmwz.configuration import wz_registration_config
from hmwz.i18n import CommandLocalizations, t

from hmwz.modules.hs.wz.module import WzRegistrationModule

logger = logging.getLogger(__name__)


@app_commands.checks.has_any_role("Offiziere", "Moderator")
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
    role=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get(
            "parameter.description.wz.setup.configure.role", "-"
        ),
        key="wz.setup.configure.role.description",
    ),
    permanent=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get(
            "parameter.description.wz.setup.configure.permanent", "-"
        ),
        key="wz.setup.configure.permanent.description",
    ),
)
async def configure(
    interaction: Interaction, role: Role, permanent: bool = False
) -> None:
    await interaction.response.defer(ephemeral=True)
    try:
        guild = interaction.guild
        channel_id = interaction.channel_id
        if guild is None or channel_id is None:
            await interaction.followup.send(
                t(interaction, "wz.setup.configure.error"),
                ephemeral=True,
            )
            return

        manager = getattr(interaction.client, "module_manager", None)
        if manager is None:
            await interaction.followup.send(
                t(interaction, "wz.setup.configure.error"),
                ephemeral=True,
            )
            return

        module: WzRegistrationModule = await manager.get_module(
            guild, WzRegistrationModule
        )

        if await module.registration.get(guild=guild, channel_id=channel_id):
            await interaction.followup.send(
                t(interaction, "wz.setup.configure.already_configured"),
                ephemeral=True,
            )
            return

        if guild.me and role >= guild.me.top_role:
            await interaction.followup.send(
                t(interaction, "wz.setup.configure.error_role_hierarchy"),
                ephemeral=True,
            )
            return

        configured_role_count = await module.roles.count(
            guild=guild, roles=[role.id], channel_id=channel_id
        )
        max_roles = int(wz_registration_config().get("max_registration_roles", 4))
        role_count = await module.roles.count(guild=guild, channel_id=channel_id)
        if configured_role_count == 0 and role_count >= max_roles:
            await interaction.followup.send(
                t(interaction, "wz.setup.roles.add.max_roles", max_roles=max_roles),
                ephemeral=True,
            )
            return

        ok = await module.registration.create(guild=guild, channel_id=channel_id)
        if not ok and await module.registration.get(guild=guild, channel_id=channel_id):
            await interaction.followup.send(
                t(interaction, "wz.setup.configure.already_configured"),
                ephemeral=True,
            )
            return
        if not ok:
            await interaction.followup.send(
                t(interaction, "wz.setup.configure.error"),
                ephemeral=True,
            )
            return

        if not await module.roles.add(
            guild=guild,
            role=role.id,
            permanent=permanent,
            score=1,
            channel_id=channel_id,
        ):
            await module.registration.remove(guild=guild, channel_id=channel_id)
            await interaction.followup.send(
                t(interaction, "wz.setup.configure.error"),
                ephemeral=True,
            )
            return

        if not await module.purge_channels.remove(guild=guild, channel_id=channel_id):
            logger.error(
                "Failed to remove registration channel %s from the purge list "
                "in guild %s (%s).",
                channel_id,
                guild.name,
                guild.id,
            )
            await interaction.followup.send(
                t(interaction, "wz.setup.configure.error"),
                ephemeral=True,
            )
            return

        if not await module.compose_registration_overview(
            force=True, channel_id=channel_id
        ):
            await interaction.followup.send(
                t(
                    interaction,
                    "wz.setup.configure.overview_failed",
                    channel_name=f"<#{channel_id}>",
                ),
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            t(
                interaction,
                "wz.setup.configure.success",
                channel_name=f"<#{channel_id}>",
            ),
            ephemeral=True,
        )
    except Exception as e:
        logger.exception(
            "%s WZ setup configure failed: %s", utils.log_interaction(interaction), e
        )
        await interaction.followup.send(
            t(interaction, "wz.setup.configure.error"),
            ephemeral=True,
        )
