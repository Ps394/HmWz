from __future__ import annotations

import logging

import discord
from discord import Interaction, app_commands

from hmwz import utils
from hmwz.i18n import CommandLocalizations, t

from .autocomplete import (
    DISPLAY_NAME_ACCOUNT_VALUE,
    linked_accounts,
    registration_roles,
)
from ...module import WzRegistrationModule

logger = logging.getLogger(__name__)


@app_commands.command(
    name="register",
    description=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get(
            "command.description.wz.registration.register",
            "Register an in-game account for a WZ event",
        ),
        key="wz.registration.register.description",
    ),
)
@app_commands.describe(
    account=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get(
            "parameter.description.wz.registration.account", "In-game account name"
        ),
        key="wz.registration.account.description",
    ),
    role=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get(
            "parameter.description.wz.registration.register.role",
            "Registration role to assign",
        ),
        key="wz.registration.register.role.description",
    ),
)
@app_commands.autocomplete(account=linked_accounts, role=registration_roles)
@app_commands.checks.cooldown(1, 10, key=lambda interaction: interaction.user.id)
async def register(interaction: Interaction, account: str, role: str) -> None:
    await interaction.response.defer(ephemeral=True)
    account = account.strip()
    role_id = 0
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
        configured_roles = await module.roles.get(guild=guild)
        try:
            role_id = int(role)
        except ValueError:
            role_id = 0
        if not configured_roles or role_id not in {
            configured.role for configured in configured_roles
        }:
            await interaction.followup.send(
                t(interaction, "wz.registration.account.invalid_role"),
                ephemeral=True,
            )
            return
        selected_role = guild.get_role(role_id)
        if selected_role is None:
            await interaction.followup.send(
                t(interaction, "wz.registration.account.invalid_role"),
                ephemeral=True,
            )
            return

        if is_display_name:
            await module._handle_registration(
                interaction, selected_role, response_deferred=True
            )
            return

        registrations = await module.registrations.get(guild=guild, member=member.id)
        current = next(
            (
                record
                for record in registrations or ()
                if record.account.casefold() == canonical_account.casefold()
            ),
            None,
        )
        if current is not None and current.role == selected_role.id:
            repaired_role = selected_role not in member.roles
            if repaired_role:
                await member.add_roles(
                    selected_role, reason="WZ game account registration"
                )
                await module.compose_registration_overview(force=True)
            await interaction.followup.send(
                t(
                    interaction,
                    (
                        "wz.registration.account.registered"
                        if repaired_role
                        else "wz.registration.account.already_registered"
                    ),
                    account=account_label,
                    role_name=selected_role.name,
                ),
                ephemeral=True,
            )
            return

        if not await module.registrations.add(
            guild=guild,
            member=member.id,
            account=canonical_account,
            role=selected_role.id,
        ):
            await interaction.followup.send(
                t(interaction, "wz.registration.account.error"), ephemeral=True
            )
            return

        if current is not None and current.role is not None:
            other_uses_of_old_role = any(
                record.account.casefold() != canonical_account.casefold()
                and record.role == current.role
                for record in registrations or ()
            )
            old_role = guild.get_role(current.role)
            if not other_uses_of_old_role and old_role is not None:
                await member.remove_roles(
                    old_role, reason="WZ game account registration updated"
                )
        if selected_role not in member.roles:
            await member.add_roles(selected_role, reason="WZ game account registration")

        await module.compose_registration_overview(force=True)
        await interaction.followup.send(
            t(
                interaction,
                "wz.registration.account.registered",
                account=account_label,
                role_name=selected_role.name,
            ),
            ephemeral=True,
        )
    except discord.HTTPException:
        logger.exception(
            "%s Failed to assign registration role %s to account %r.",
            utils.log_interaction(interaction),
            role_id,
            account,
        )
        await interaction.followup.send(
            t(interaction, "wz.registration.account.error"), ephemeral=True
        )
    except Exception:
        logger.exception(
            "%s Failed to register account %r for role %s.",
            utils.log_interaction(interaction),
            account,
            role_id,
        )
        await interaction.followup.send(
            t(interaction, "wz.registration.account.error"), ephemeral=True
        )
