from __future__ import annotations

import logging

import discord
from discord import app_commands

from hmwz import utils
from hmwz.i18n import CommandLocalizations, t
from hmwz.modules.hs.wz.module import WzRegistrationModule

logger = logging.getLogger(__name__)


class ResetRolesConfirmation(discord.ui.View):
    def __init__(
        self,
        *,
        guild: discord.Guild,
        owner_id: int,
        role_ids: list[int],
        context: discord.Interaction,
    ) -> None:
        super().__init__(timeout=120)
        self.guild = guild
        self.owner_id = owner_id
        self.role_ids = role_ids
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.label = t(
                    context,
                    "wz.reset_roles.confirm_button"
                    if item.custom_id == "wz_reset_roles_confirm"
                    else "wz.reset_roles.cancel_button",
                )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        await interaction.response.send_message(
            t(interaction, "wz.reset_roles.confirmation_owner"), ephemeral=True
        )
        return False

    @discord.ui.button(
        label="Reset roles",
        style=discord.ButtonStyle.danger,
        custom_id="wz_reset_roles_confirm",
    )
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.defer()
        self.stop()
        try:
            manager = getattr(interaction.client, "module_manager", None)
            if manager is None:
                content = t(interaction, "wz.reset_roles.error")
            else:
                module: WzRegistrationModule = await manager.get_module(
                    self.guild, WzRegistrationModule
                )
                configured_roles = await module.roles.get(guild=self.guild)
                configured_ids = {record.role for record in configured_roles or ()}
                roles = [
                    role
                    for role_id in self.role_ids
                    if role_id in configured_ids
                    and (role := self.guild.get_role(role_id)) is not None
                    and not role.is_default()
                    and not role.managed
                ]
                if not roles:
                    content = t(interaction, "wz.reset_roles.no_roles")
                else:
                    removed_members = 0
                    failed_members = 0
                    member_fetch_failed = False
                    try:
                        async for member in self.guild.fetch_members(limit=None):
                            held_roles = [
                                role for role in roles if role in member.roles
                            ]
                            if not held_roles:
                                continue
                            try:
                                await member.remove_roles(
                                    *held_roles, reason="WZ Reset Roles"
                                )
                                removed_members += 1
                            except discord.HTTPException:
                                failed_members += 1
                                logger.exception(
                                    "Failed to remove WZ roles %s from member %s in guild %s.",
                                    [role.id for role in held_roles],
                                    member.id,
                                    self.guild.id,
                                )
                    except discord.HTTPException:
                        member_fetch_failed = True
                        logger.exception(
                            "%s Could not fetch all members for the WZ role reset.",
                            utils.log_interaction(interaction),
                        )
                    if member_fetch_failed:
                        content = t(
                            interaction,
                            "wz.reset_roles.fetch_failure",
                            removed_members=removed_members,
                            failed_members=failed_members,
                        )
                    else:
                        content = t(
                            interaction,
                            "wz.reset_roles.partial_failure"
                            if failed_members
                            else "wz.reset_roles.success",
                            removed_members=removed_members,
                            failed_members=failed_members,
                        )
        except discord.HTTPException:
            logger.exception(
                "%s Could not fetch all members for the WZ role reset.",
                utils.log_interaction(interaction),
            )
            content = t(interaction, "wz.reset_roles.error")
        except Exception:
            logger.exception(
                "%s WZ reset-roles failed.",
                utils.log_interaction(interaction),
            )
            content = t(interaction, "wz.reset_roles.error")
        self.stop()
        await interaction.edit_original_response(content=content, view=None)

    @discord.ui.button(
        label="Cancel",
        style=discord.ButtonStyle.secondary,
        custom_id="wz_reset_roles_cancel",
    )
    async def cancel(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.stop()
        await interaction.response.edit_message(
            content=t(interaction, "wz.reset_roles.cancelled"), view=None
        )


@app_commands.checks.has_any_role("Offiziere", "Moderator")
@app_commands.command(
    name="reset-roles",
    description=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get(
            "command.description.wz.reset_roles", "-"
        ),
        key="wz.reset_roles.description",
    ),
)
@app_commands.checks.bot_has_permissions(manage_roles=True)
async def reset_roles(interaction: discord.Interaction) -> None:
    await interaction.response.defer(ephemeral=True)
    try:
        guild = interaction.guild
        manager = getattr(interaction.client, "module_manager", None)
        if guild is None or manager is None:
            await interaction.followup.send(
                t(interaction, "wz.reset_roles.error"), ephemeral=True
            )
            return

        module: WzRegistrationModule = await manager.get_module(
            guild, WzRegistrationModule
        )
        configured_roles = await module.roles.get(guild=guild)
        roles = [
            role
            for record in configured_roles or ()
            if (role := guild.get_role(record.role)) is not None
            and not role.is_default()
            and not role.managed
        ]
        if not roles:
            await interaction.followup.send(
                t(interaction, "wz.reset_roles.no_roles"), ephemeral=True
            )
            return

        roles.sort(key=lambda role: (role.name.casefold(), role.id))
        role_names = [role.mention for role in roles[:60]]
        if len(roles) > len(role_names):
            role_names.append(
                t(
                    interaction,
                    "wz.reset_roles.more_roles",
                    count=len(roles) - len(role_names),
                )
            )
        await interaction.followup.send(
            t(
                interaction,
                "wz.reset_roles.confirmation",
                role_names="\n".join(role_names),
            ),
            view=ResetRolesConfirmation(
                guild=guild,
                owner_id=interaction.user.id,
                role_ids=[role.id for role in roles],
                context=interaction,
            ),
            ephemeral=True,
        )
    except Exception as error:
        logger.exception(
            "%s WZ reset-roles preparation failed: %s",
            utils.log_interaction(interaction),
            error,
        )
        await interaction.followup.send(
            t(interaction, "wz.reset_roles.error"), ephemeral=True
        )
