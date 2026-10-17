from __future__ import annotations

import logging

import discord
from discord import Interaction, app_commands

from hmwz import utils
from hmwz.i18n import CommandLocalizations, t

from ...module import WzRegistrationModule

logger = logging.getLogger(__name__)


def _command_description(key: str, fallback: str) -> app_commands.locale_str:
    return app_commands.locale_str(
        CommandLocalizations.get("en", {}).get(key, fallback),
        key=f"{key.removeprefix('command.description.')}.description",
    )


async def _get_member_context(
    interaction: Interaction,
) -> tuple[discord.Guild, discord.Member, WzRegistrationModule] | None:
    guild = interaction.guild
    member = interaction.user
    manager = getattr(interaction.client, "module_manager", None)
    if guild is None or not isinstance(member, discord.Member) or manager is None:
        return None
    module: WzRegistrationModule = await manager.get_module(guild, WzRegistrationModule)
    return guild, member, module


@app_commands.command(
    name="account-add",
    description=_command_description(
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
        await interaction.followup.send(
            t(interaction, "wz.registration.account.invalid"), ephemeral=True
        )
        return
    try:
        context = await _get_member_context(interaction)
        if context is None:
            await interaction.followup.send(
                t(interaction, "wz.registration.account.error"), ephemeral=True
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
            await interaction.followup.send(t(interaction, key), ephemeral=True)
            return
        if not await module.game_accounts.add(
            guild=guild, member=member.id, account=account
        ):
            await interaction.followup.send(
                t(interaction, "wz.registration.account.error"), ephemeral=True
            )
            return
        await interaction.followup.send(
            t(interaction, "wz.registration.account.added", account=account),
            ephemeral=True,
        )
    except Exception:
        logger.exception(
            "%s Failed to link game account %r.",
            utils.log_interaction(interaction),
            account,
        )
        await interaction.followup.send(
            t(interaction, "wz.registration.account.error"), ephemeral=True
        )


@app_commands.command(
    name="account-remove",
    description=_command_description(
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
async def account_remove(interaction: Interaction, account: str) -> None:
    await interaction.response.defer(ephemeral=True)
    try:
        context = await _get_member_context(interaction)
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


@app_commands.command(
    name="account-list",
    description=_command_description(
        "command.description.wz.registration.account_list",
        "List your linked in-game accounts",
    ),
)
@app_commands.checks.cooldown(1, 10, key=lambda interaction: interaction.user.id)
async def account_list(interaction: Interaction) -> None:
    await interaction.response.defer(ephemeral=True)
    try:
        context = await _get_member_context(interaction)
        if context is None:
            await interaction.followup.send(
                t(interaction, "wz.registration.account.error"), ephemeral=True
            )
            return
        guild, member, module = context
        accounts = await module.game_accounts.get(guild=guild, member=member.id)
        if not accounts:
            await interaction.followup.send(
                t(interaction, "wz.registration.account.none"), ephemeral=True
            )
            return
        names = ", ".join(record.account for record in accounts)
        if len(names) > 1800:
            names = f"{names[:1797]}..."
        await interaction.followup.send(
            t(
                interaction,
                "wz.registration.account.list",
                accounts=names,
            ),
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )
    except Exception:
        logger.exception(
            "%s Failed to list linked game accounts.",
            utils.log_interaction(interaction),
        )
        await interaction.followup.send(
            t(interaction, "wz.registration.account.error"), ephemeral=True
        )
