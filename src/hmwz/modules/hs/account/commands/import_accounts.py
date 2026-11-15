"""Moderator command for importing game accounts from JSON."""

from __future__ import annotations

import io
import logging

import discord
from discord import Interaction, app_commands

from hmwz.configuration import MODERATOR_ROLES
from hmwz.i18n import CommandLocalizations, t
from hmwz.modules.hs.account.importer import import_entries, parse_entries
from hmwz.ui.messages import send_followup
from hmwz.utils.interactions import log_interaction

from .common import command_description, get_member_context

logger = logging.getLogger(__name__)
MAX_IMPORT_SIZE = 2 * 1024 * 1024


@app_commands.command(
    name="import",
    description=command_description(
        "command.description.wz.registration.account_import",
        "Import game accounts from a JSON file",
    ),
)
@app_commands.guild_only()
@app_commands.checks.has_any_role(*MODERATOR_ROLES)
@app_commands.describe(
    file=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get(
            "parameter.description.wz.registration.account_import.file", "JSON file"
        ),
        key="wz.registration.account_import.file.description",
    )
)
@app_commands.checks.cooldown(1, 60, key=lambda interaction: interaction.guild_id)
async def account_import(interaction: Interaction, file: discord.Attachment) -> None:
    """Import account mappings into the current server."""
    await interaction.response.defer(ephemeral=True)
    if not file.filename.lower().endswith(".json") or file.size > MAX_IMPORT_SIZE:
        await send_followup(interaction, t(interaction, "wz.account_import.invalid"))
        return
    try:
        content = await file.read()
        if len(content) > MAX_IMPORT_SIZE:
            raise ValueError("File exceeds size limit")
        entries = parse_entries(content)
    except (ValueError, UnicodeDecodeError, RecursionError):
        await send_followup(interaction, t(interaction, "wz.account_import.invalid"))
        return
    except discord.HTTPException:
        logger.exception(
            "%s Failed to download account import.", log_interaction(interaction)
        )
        await send_followup(interaction, t(interaction, "wz.account_import.error"))
        return

    try:
        context = await get_member_context(interaction)
        if context is None:
            await send_followup(interaction, t(interaction, "wz.account_import.error"))
            return
        guild, _, module = context
        result = await import_entries(guild, module.game_accounts, entries)
        summary = t(
            interaction,
            "wz.account_import.result",
            imported=result.imported,
            existing=result.existing,
            skipped=result.skipped,
        )
        await send_followup(interaction, summary)
        if result.issues:
            report = io.BytesIO(("\n".join(result.issues) + "\n").encode("utf-8"))
            try:
                await send_followup(
                    interaction,
                    file=discord.File(report, filename="account-import-report.txt"),
                )
            except discord.HTTPException:
                logger.exception(
                    "%s Failed to send import report.", log_interaction(interaction)
                )
                await send_followup(
                    interaction, t(interaction, "wz.account_import.report_error")
                )
    except Exception:
        logger.exception("%s Account import failed.", log_interaction(interaction))
        await send_followup(interaction, t(interaction, "wz.account_import.error"))
