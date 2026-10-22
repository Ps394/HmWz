from __future__ import annotations

import logging

import discord
from discord import Interaction, app_commands

from hmwz import utils
from hmwz.i18n import CommandLocalizations, t

from hmwz.modules.registrations.commands.wz.registration.autocomplete import (
    linked_accounts,
)
from .common import command_description, get_member_context

logger = logging.getLogger(__name__)


@app_commands.command(
    name="account-remove",
    description=command_description(
        "command.description.wz.registration.account_remove",
        "Unlink one of your in-game accounts",
    ),
)
@app_commands.describe(
    account=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get(
            "parameter.description.wz.registration.account", "In-game account name"
        ),
        key="wz.registration.account.description",
    )
)
@app_commands.checks.cooldown(1, 10, key=lambda interaction: interaction.user.id)
@app_commands.autocomplete(account=linked_accounts)
async def account_remove(interaction: Interaction, account: str) -> None:
    await interaction.response.defer(ephemeral=True)
    try:
        context = await get_member_context(interaction)
        if context is None:
            await interaction.followup.send(
                t(interaction, "wz.registration.account.error"), ephemeral=True
            )
            return
        guild, member, module = context
        linked = await module.game_accounts.get(
            guild=guild, member=member.id, account=account.strip()
        )
        if not linked:
            await interaction.followup.send(
                t(interaction, "wz.registration.account.not_found"), ephemeral=True
            )
            return

        registrations = await module.registrations.get(
            guild=guild, member=member.id, account=linked[0].account
        )
        all_registrations = await module.registrations.get(
            guild=guild, member=member.id
        )
        role_ids = {
            record.role for record in registrations or () if record.role is not None
        }
        other_role_ids = {
            record.role
            for record in all_registrations or ()
            if record.account.casefold() != linked[0].account.casefold()
            and record.role is not None
        }
        for role_id in role_ids - other_role_ids:
            role = guild.get_role(role_id)
            if role is not None and role in member.roles:
                await member.remove_roles(role, reason="WZ game account unlinked")

        if registrations and not await module.registrations.remove(
            guild=guild, member=member.id, account=linked[0].account
        ):
            await interaction.followup.send(
                t(interaction, "wz.registration.account.error"), ephemeral=True
            )
            return

        if not await module.game_accounts.remove(
            guild=guild, member=member.id, account=linked[0].account
        ):
            await interaction.followup.send(
                t(interaction, "wz.registration.account.error"), ephemeral=True
            )
            return

        await interaction.followup.send(
            t(
                interaction,
                "wz.registration.account.removed",
                account=linked[0].account,
            ),
            ephemeral=True,
        )
        await module.compose_registration_overview(force=True)
    except discord.HTTPException:
        logger.exception(
            "%s Failed to remove Discord roles for game account %r.",
            utils.log_interaction(interaction),
            account,
        )
        await interaction.followup.send(
            t(interaction, "wz.registration.account.error"), ephemeral=True
        )
    except Exception:
        logger.exception(
            "%s Failed to unlink game account %r.",
            utils.log_interaction(interaction),
            account,
        )
        await interaction.followup.send(
            t(interaction, "wz.registration.account.error"), ephemeral=True
        )
