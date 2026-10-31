"""Command for removing an in-game account registration."""

from __future__ import annotations

import logging

import discord
from discord import Interaction, app_commands

from hmwz.i18n import CommandLocalizations, t
from hmwz.ui.messages import send_temporary_followup
from hmwz.utils.interactions import log_interaction

from .autocomplete import DISPLAY_NAME_ACCOUNT_VALUE, registered_accounts
from hmwz.modules.registration.module import RegistrationModule

logger = logging.getLogger(__name__)


@app_commands.command(
    name="deregister",
    description=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get(
            "command.description.wz.registration.deregister",
            "Deregister an in-game account from a WZ event",
        ),
        key="wz.registration.deregister.description",
    ),
)
@app_commands.describe(
    account=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get(
            "parameter.description.wz.registration.account", "In-game account name"
        ),
        key="wz.registration.account.description",
    ),
)
@app_commands.checks.cooldown(1, 10, key=lambda interaction: interaction.user.id)
@app_commands.autocomplete(account=registered_accounts)
async def deregister(interaction: Interaction, account: str) -> None:
    """Remove the invoking member's account registration from the current channel.

    Args:
        interaction: The interaction that invoked the command.
        account: Linked in-game account or display-name registration to remove.
    """
    await interaction.response.defer(ephemeral=True)
    account = account.strip()
    try:
        guild = interaction.guild
        member = interaction.user
        manager = getattr(interaction.client, "module_manager", None)
        if guild is None or not isinstance(member, discord.Member) or manager is None:
            await send_temporary_followup(
                interaction,
                t(interaction, "wz.registration.account.error"),
                ephemeral=True,
            )
            return

        module: RegistrationModule = await manager.get_module(guild, RegistrationModule)
        channel_id = interaction.channel_id
        if channel_id is None:
            await send_temporary_followup(
                interaction,
                t(interaction, "wz.registration.account.error"),
                ephemeral=True,
            )
            return
        is_display_name = account == DISPLAY_NAME_ACCOUNT_VALUE
        if is_display_name:
            canonical_account = ""
            account_label = member.display_name
        else:
            linked_accounts = await module.game_accounts.get(
                guild=guild, member=member.id, account=account
            )
            if not linked_accounts:
                await send_temporary_followup(
                    interaction,
                    t(interaction, "wz.registration.account.not_linked"),
                    ephemeral=True,
                )
                return
            canonical_account = linked_accounts[0].account
            account_label = canonical_account
        registrations = await module.registrations.get(
            guild=guild,
            member=member.id,
            account=canonical_account,
            channel_id=channel_id,
        )
        current = registrations[0] if registrations else None
        if current is None or current.role is None:
            await send_temporary_followup(
                interaction,
                t(
                    interaction,
                    "wz.registration.account.not_registered",
                    account=account_label,
                ),
                ephemeral=True,
            )
            return
        role = guild.get_role(current.role)
        remaining = await module.registrations.get(guild=guild, member=member.id)
        other_accounts_use_role = any(
            record.role == current.role
            and (
                record.channel_id != channel_id
                or record.account.casefold() != canonical_account.casefold()
            )
            for record in remaining or ()
        )
        if role is not None and not other_accounts_use_role and role in member.roles:
            await member.remove_roles(role, reason="WZ game account deregistration")
        if not await module.registrations.remove(
            guild=guild,
            member=member.id,
            account=canonical_account,
            channel_id=channel_id,
        ):
            await send_temporary_followup(
                interaction,
                t(interaction, "wz.registration.account.error"),
                ephemeral=True,
            )
            return

        await module.export_registration_snapshot(channel_id, "deregistration")
        await module.compose_registration_overview(force=True, channel_id=channel_id)
        await send_temporary_followup(
            interaction,
            t(
                interaction,
                "wz.registration.account.deregistered",
                account=account_label,
                role_name=role.name if role is not None else str(current.role),
            ),
            ephemeral=True,
        )
    except discord.HTTPException:
        logger.exception(
            "%s Failed to remove registration for account %r.",
            log_interaction(interaction),
            account,
        )
        await send_temporary_followup(
            interaction, t(interaction, "wz.registration.account.error"), ephemeral=True
        )
    except Exception:
        logger.exception(
            "%s Failed to deregister account %r.",
            log_interaction(interaction),
            account,
        )
        await send_temporary_followup(
            interaction, t(interaction, "wz.registration.account.error"), ephemeral=True
        )
