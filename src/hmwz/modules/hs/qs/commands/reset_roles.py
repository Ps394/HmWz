from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import cast

import discord
from discord import app_commands

from hmwz import utils
from hmwz.i18n import CommandLocalizations, t
from hmwz.modules.hs.ephemeral_view import EphemeralView
from hmwz.modules.hs.qs.module import QsRegistrationModule
from hmwz.modules.hs.wz.commands.reset_roles import reset_roles

_logger = logging.getLogger(__name__)


class QsRolesResetConfirmation(EphemeralView):
    def __init__(
        self, *, guild: discord.Guild, channel_id: int, owner_id: int
    ) -> None:
        super().__init__(timeout=180)
        self.guild = guild
        self.channel_id = channel_id
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        await self.send_temporary_response(
            interaction, t(interaction, "qs.reset_roles.owner")
        )
        return False

    @discord.ui.button(
        label="Confirm reset",
        style=discord.ButtonStyle.danger,
        custom_id="qs_reset_roles_confirm",
    )
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.defer()
        self.stop()
        try:
            manager = getattr(interaction.client, "module_manager", None)
            if manager is None:
                content = t(interaction, "qs.reset_roles.error")
            else:
                module: QsRegistrationModule = await manager.get_module(
                    self.guild, QsRegistrationModule
                )
                configured = await module.roles.get(
                    guild=self.guild, channel_id=self.channel_id
                )
                roles = [
                    role
                    for record in configured or ()
                    if (role := self.guild.get_role(record.role)) is not None
                    and not role.is_default()
                    and not role.managed
                ]
                if not roles:
                    content = t(interaction, "qs.reset_roles.no_roles")
                else:
                    removed_members = 0
                    failed_members = 0
                    fetch_failed = False
                    try:
                        async for member in self.guild.fetch_members(limit=None):
                            held_roles = [role for role in roles if role in member.roles]
                            if not held_roles:
                                continue
                            try:
                                await member.remove_roles(
                                    *held_roles, reason="QS Reset Roles"
                                )
                                removed_members += 1
                            except discord.HTTPException:
                                failed_members += 1
                                _logger.exception(
                                    "Failed to remove QS roles from member %s in guild %s.",
                                    member.id,
                                    self.guild.id,
                                )
                    except discord.HTTPException:
                        fetch_failed = True
                        _logger.exception(
                            "%s Could not fetch all members for the QS role reset.",
                            utils.log_interaction(interaction),
                        )
                    content = t(
                        interaction,
                        "qs.reset_roles.fetch_failure"
                        if fetch_failed
                        else "qs.reset_roles.partial_failure"
                        if failed_members
                        else "qs.reset_roles.success",
                        removed_members=removed_members,
                        failed_members=failed_members,
                    )
        except Exception:
            _logger.exception(
                "%s QS role reset failed.", utils.log_interaction(interaction)
            )
            content = t(interaction, "qs.reset_roles.error")
        await self.finish(interaction, content)

    @discord.ui.button(
        label="Cancel",
        style=discord.ButtonStyle.secondary,
        custom_id="qs_reset_roles_cancel",
    )
    async def cancel(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.finish(interaction, t(interaction, "qs.reset_roles.cancelled"))


@app_commands.command(
    name="reset-wz-roles",
    description=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get(
            "command.description.qs.reset_wz_roles", "Reset configured WZ roles"
        ),
        key="qs.reset_wz_roles.description",
    ),
)
@app_commands.checks.has_any_role("Offiziere", "Moderator")
@app_commands.checks.bot_has_permissions(manage_roles=True)
async def reset_wz_roles(interaction: discord.Interaction) -> None:
    callback = cast(
        Callable[[discord.Interaction], Awaitable[None]], reset_roles.callback
    )
    await callback(interaction)


@app_commands.command(
    name="reset-qs-roles",
    description=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get(
            "command.description.qs.reset_qs_roles", "Reset configured QS roles"
        ),
        key="qs.reset_qs_roles.description",
    ),
)
@app_commands.checks.has_any_role("Offiziere", "Moderator")
@app_commands.checks.bot_has_permissions(manage_roles=True)
async def reset_qs_roles(interaction: discord.Interaction) -> None:
    guild = interaction.guild
    channel_id = interaction.channel_id
    manager = getattr(interaction.client, "module_manager", None)
    if guild is None or channel_id is None or manager is None:
        await interaction.response.send_message(
            t(interaction, "qs.reset_roles.error"), ephemeral=True
        )
        return
    try:
        module: QsRegistrationModule = await manager.get_module(
            guild, QsRegistrationModule
        )
        registration = await module.registration.get(
            guild=guild, channel_id=channel_id
        )
        if registration is None:
            await interaction.response.send_message(
                t(interaction, "qs.reset_roles.not_configured"), ephemeral=True
            )
            return
        configured = await module.roles.get(guild=guild, channel_id=channel_id)
        roles = [
            role
            for record in configured or ()
            if (role := guild.get_role(record.role)) is not None
            and not role.is_default()
            and not role.managed
        ]
        if not roles:
            await interaction.response.send_message(
                t(interaction, "qs.reset_roles.no_roles"), ephemeral=True
            )
            return
        role_names = "\n".join(role.mention for role in roles)
        view = QsRolesResetConfirmation(
            guild=guild, channel_id=channel_id, owner_id=interaction.user.id
        )
        await interaction.response.send_message(
            t(interaction, "qs.reset_roles.confirmation", role_names=role_names),
            view=view,
            ephemeral=True,
        )
        view.message = await interaction.original_response()
    except Exception:
        _logger.exception(
            "%s QS role reset preparation failed.", utils.log_interaction(interaction)
        )
        if interaction.response.is_done():
            await interaction.followup.send(
                t(interaction, "qs.reset_roles.error"), ephemeral=True
            )
        else:
            await interaction.response.send_message(
                t(interaction, "qs.reset_roles.error"), ephemeral=True
            )
