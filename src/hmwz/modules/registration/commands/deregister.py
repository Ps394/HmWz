from __future__ import annotations

import logging

import discord
from discord import Interaction, app_commands

from hmwz import utils
from hmwz.i18n import CommandLocalizations, t

from .autocomplete import DISPLAY_NAME_ACCOUNT_VALUE, registered_accounts
from hmwz.modules.hs.wz.module import WzRegistrationModule

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
    await interaction.response.defer(ephemeral=True)
    account = account.strip()
    try:
        guild = interaction.guild
        member = interaction.user
        manager = getattr(interaction.client, "module_manager", None)
        if guild is None or not isinstance(member, discord.Member) or manager is None:
            await interaction.followup.send(
                t(interaction, "wz.registration.account.error"), ephemeral=True
            )
            return

        module: WzRegistrationModule = await manager.get_module(
            guild, WzRegistrationModule
        )
        channel_id = interaction.channel_id
        if channel_id is None:
            await interaction.followup.send(
                t(interaction, "wz.registration.account.error"), ephemeral=True
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
                await interaction.followup.send(
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
            await interaction.followup.send(
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
            await interaction.followup.send(
                t(interaction, "wz.registration.account.error"), ephemeral=True
            )
            return

        await module.export_registration_snapshot(channel_id, "deregistration")
        await module.compose_registration_overview(force=True, channel_id=channel_id)
        await interaction.followup.send(
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
            utils.log_interaction(interaction),
            account,
        )
        await interaction.followup.send(
            t(interaction, "wz.registration.account.error"), ephemeral=True
        )
    except Exception:
        logger.exception(
            "%s Failed to deregister account %r.",
            utils.log_interaction(interaction),
            account,
        )
        await interaction.followup.send(
            t(interaction, "wz.registration.account.error"), ephemeral=True
        )
