import io
import logging

from discord import File, Interaction, app_commands

from hmwz.i18n import CommandLocalizations, t
from hmwz.utils.loaders import fetch_member
from hmwz.utils.interactions import log_interaction

from hmwz.modules.hs.wz.module import WzRegistrationModule

from ..responses import send_temporary_followup

logger = logging.getLogger(__name__)


@app_commands.checks.bot_has_permissions(attach_files=True)
@app_commands.command(
    name="csv",
    description=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get(
            "command.description.wz.registration.csv", "-"
        ),
        key="wz.registration.csv.description",
    ),
)
@app_commands.describe(
    ephemeral=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get("parameter.description.ephemeral", "-"),
        key="ephemeral.description",
    )
)
@app_commands.checks.cooldown(1, 60, key=lambda i: i.guild_id)
async def csv(interaction: Interaction, ephemeral: bool = True):
    await interaction.response.defer(ephemeral=ephemeral)
    try:
        if not interaction.guild:
            await send_temporary_followup(
                interaction, t(interaction, "wz.registration.csv.error"), ephemeral=True
            )
            return

        manager = getattr(interaction.client, "module_manager", None)
        if manager is None:
            await send_temporary_followup(
                interaction, t(interaction, "wz.registration.csv.error"), ephemeral=True
            )
            return

        module: WzRegistrationModule = await manager.get_module(
            interaction.guild, WzRegistrationModule
        )
        channel_id = interaction.channel_id
        if channel_id is None:
            await send_temporary_followup(
                interaction, t(interaction, "wz.registration.csv.error"), ephemeral=True
            )
            return
        registrations = await module.registrations.get(
            guild=interaction.guild, channel_id=channel_id
        )
        if not registrations:
            await send_temporary_followup(
                interaction,
                t(interaction, "wz.registration.csv.no_registrations"),
                ephemeral=True,
            )
            return

        roles = await module.roles.get(guild=interaction.guild, channel_id=channel_id)
        role_map = {r.role: r for r in roles} if roles else {}

        rows = [
            "NR; Discord_Name; Guild_Name; Account; Role; Timestamp; Score; Comment"
        ]
        index = 1
        for reg in registrations:
            member = (
                await fetch_member(interaction.guild, reg.member)
                if reg.member
                else None
            )
            role_obj = role_map.get(reg.role) if reg.role is not None else None
            role = interaction.guild.get_role(reg.role) if reg.role else None

            user_name = member.name if member else "null"
            member_name = member.display_name if member else "null"
            role_name = role.name if role else "Unknown Role"
            score = role_obj.score if role_obj else 0
            timestamp = reg.timestamp if reg.timestamp else "Unknown Timestamp"
            rows.append(
                f"{index}; {user_name}; {member_name}; {reg.account}; "
                f"{role_name}; {timestamp}; {score};"
            )
            index += 1

        csv_content = "\n".join(rows) + "\n"
        bio = io.BytesIO(csv_content.encode("utf-8-sig"))
        bio.seek(0)
        try:
            csv_file = File(
                fp=bio,
                filename=f"wz_registrations_{interaction.guild.id}_{channel_id}.csv",
            )
            await send_temporary_followup(
                interaction,
                content=t(interaction, "wz.registration.csv.success"),
                file=csv_file,
                ephemeral=ephemeral,
            )
        finally:
            bio.close()
    except Exception as e:
        logger.exception(
            "%s WZ registration csv failed: %s", log_interaction(interaction), e
        )
        await send_temporary_followup(
            interaction, t(interaction, "wz.registration.csv.error"), ephemeral=True
        )
