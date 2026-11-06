from __future__ import annotations

import logging

from discord import Interaction, app_commands

from hmwz.ui.messages import send_followup
from hmwz.i18n import CommandLocalizations, t
from hmwz.utils.interactions import log_interaction

from .common import command_description, get_member_context

logger = logging.getLogger(__name__)


@app_commands.command(
    name="account-add",
    description=command_description(
        "command.description.wz.registration.account_add",
        "Link an in-game account to your Discord member",
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
async def account_add(interaction: Interaction, account: str) -> None:
    await interaction.response.defer(ephemeral=True)
    account = account.strip()
    if not account or len(account) > 100:
        await send_followup(
            interaction,
            t(interaction, "wz.registration.account.invalid"),
            ephemeral=True,
        )
        return
    try:
        context = await get_member_context(interaction)
        if context is None:
            await send_followup(
                interaction,
                t(interaction, "wz.registration.account.error"),
                ephemeral=True,
            )
            return
        guild, member, module = context
        existing = await module.game_accounts.get(guild=guild, account=account)
        if existing:
            key = (
                "wz.registration.account.already_linked"
                if existing[0].member == member.id
                else "wz.registration.account.owned_by_other"
            )
            await send_followup(interaction, t(interaction, key), ephemeral=True)
            return
        if not await module.game_accounts.add(
            guild=guild, member=member.id, account=account
        ):
            await send_followup(
                interaction,
                t(interaction, "wz.registration.account.error"),
                ephemeral=True,
            )
            return
        await send_followup(
            interaction,
            t(interaction, "wz.registration.account.added", account=account),
            ephemeral=True,
        )
    except Exception:
        logger.exception(
            "%s Failed to link game account %r.",
            log_interaction(interaction),
            account,
        )
        await send_followup(
            interaction, t(interaction, "wz.registration.account.error"), ephemeral=True
        )
