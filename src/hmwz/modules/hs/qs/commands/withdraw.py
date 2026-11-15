"""Moderator command for withdrawing a player's base report."""

from __future__ import annotations

import discord
from discord import app_commands

from hmwz.configuration import MODERATOR_ROLES

from .report import report_dialog


@app_commands.command(
    name="withdraw",
    description=app_commands.locale_str(
        "Retract a player's base report", key="qs.admin.withdraw"
    ),
)
@app_commands.checks.has_any_role(*MODERATOR_ROLES)
async def withdraw(
    interaction: discord.Interaction, player: discord.Member
) -> None:
    """Confirm withdrawal of a player's report from this channel's eruption."""
    await report_dialog(interaction, player, None)
