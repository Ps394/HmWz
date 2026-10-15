import io
import logging

import hmUtils
from discord import File, Interaction, app_commands
from i18n import CommandLocalizations, t

from ...module import WzRegistrationModule

logger = logging.getLogger(__name__)


@app_commands.checks.has_permissions(moderate_members=True, manage_messages=True)
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
@app_commands.checks.cooldown(1, 120, key=lambda i: i.guild_id)
async def csv(interaction: Interaction, ephemeral: bool = True):
    await interaction.response.defer(ephemeral=ephemeral)
    try:
        if not interaction.guild:
            await interaction.followup.send(
                t(interaction, "wz.registration.csv.error"), ephemeral=True
            )
            return

        manager = getattr(interaction.client, "module_manager", None)
        if manager is None:
            await interaction.followup.send(
                t(interaction, "wz.registration.csv.error"), ephemeral=True
            )
            return

        module: WzRegistrationModule = await manager.get_module(
            interaction.guild, WzRegistrationModule
        )
        registrations = await module.registrations.get(guild=interaction.guild)
        if not registrations:
            await interaction.followup.send(
                t(interaction, "wz.registration.csv.no_registrations"), ephemeral=True
            )
            return

        roles = await module.roles.get(guild=interaction.guild)
        role_map = {r.role: r for r in roles} if roles else {}

        rows = ["NR; Discord_Name; Guild_Name; Role; Timestamp; Score; Comment"]
        index = 1
        for reg in registrations:
            member = (
                await hmUtils.fetch_member(interaction.guild, reg.member)
                if reg.member
                else None
            )
            role_obj = role_map.get(reg.role) if reg.role is not None else None
            role = (
                interaction.guild.get_role(reg.role)
                if reg.role
                else None
            )

            user_name = member.name if member else "null"
            member_name = member.display_name if member else "null"
            role_name = role.name if role else "Unknown Role"
            score = role_obj.score if role_obj else 0
            timestamp = reg.timestamp if reg.timestamp else "Unknown Timestamp"
            rows.append(
                f"{index}; {user_name}; {member_name}; {role_name}; {timestamp}; {score};"
            )
            index += 1

        csv_content = "\n".join(rows) + "\n"
        bio = io.BytesIO(csv_content.encode("utf-8-sig"))
        bio.seek(0)
        try:
            csv_file = File(
                fp=bio, filename=f"wz_registrations_{interaction.guild.id}.csv"
            )
            await interaction.followup.send(
                content=t(interaction, "wz.registration.csv.success"),
                file=csv_file,
                ephemeral=ephemeral,
            )
        finally:
            bio.close()
    except Exception as e:
        logger.exception(f"WZ registration csv failed: {e}")
        await interaction.followup.send(
            t(interaction, "wz.registration.csv.error"), ephemeral=True
        )
