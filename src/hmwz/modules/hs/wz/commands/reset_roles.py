from __future__ import annotations

import logging

import discord
from discord import app_commands

from hmwz.configuration import MODERATOR_ROLES
from hmwz.i18n import CommandLocalizations, t
from hmwz.ui.components.entity_selection import EntitySelectionView
from hmwz.ui.embeds import create_embed
from hmwz.ui.messages import (
    edit_interaction_response,
    send_followup,
    send_temporary_followup,
)
from hmwz.utils.interactions import log_guild, log_interaction
from hmwz.modules.hs.wz.module import WzModule

_logger = logging.getLogger(__name__)
_MAX_ROLE_LIST_LENGTH = 700


def _role_names(
    guild: discord.Guild,
    role_ids: list[int],
    context: discord.Interaction,
    empty_key: str,
) -> str:
    names = [
        role.mention
        for role_id in role_ids
        if (role := guild.get_role(role_id)) is not None
    ]
    if not names:
        return t(context, empty_key)

    visible_names: list[str] = []
    for name in names:
        candidate = "\n".join([*visible_names, name])
        if len(candidate) > _MAX_ROLE_LIST_LENGTH:
            break
        visible_names.append(name)
    hidden_count = len(names) - len(visible_names)
    if hidden_count:
        visible_names.append(
            t(context, "wz.reset_roles.more_roles", count=hidden_count)
        )
    return "\n".join(visible_names)


class ResetRolesConfirmation(EntitySelectionView):
    def __init__(
        self,
        *,
        guild: discord.Guild,
        owner_id: int,
        role_ids: list[int],
        context: discord.Interaction,
    ) -> None:
        roles = [guild.get_role(role_id) for role_id in role_ids]
        options = [
            discord.SelectOption(
                label=role.name[:100] if role is not None else str(role_id),
                value=str(role_id),
            )
            for role_id, role in zip(role_ids, roles)
        ]
        super().__init__(
            owner_id=owner_id,
            kind="role",
            allowed_ids=role_ids,
            max_selected=len(role_ids),
            options=options,
            placeholder=t(context, "wz.reset_roles.select_exceptions"),
            owner_message=t(context, "wz.reset_roles.confirmation_owner"),
            invalid_message=t(context, "wz.reset.invalid_exceptions"),
        )
        self.guild = guild
        self.owner_id = owner_id
        self.role_ids = role_ids
        self.confirm_button: discord.ui.Button[ResetRolesConfirmation] | None = None
        for item in self.children:
            if not isinstance(item, discord.ui.Button):
                continue
            if item.custom_id == "wz_reset_roles_confirm":
                item.label = t(context, "wz.reset_roles.confirm_button")
                self.confirm_button = item
            elif item.custom_id == "wz_reset_roles_cancel":
                item.label = t(context, "wz.reset_roles.cancel_button")
        self._update_confirm_button()

    def confirmation_embed(self, context: discord.Interaction) -> discord.Embed:
        reset_ids = [
            role_id for role_id in self.role_ids if role_id not in self.selected_ids
        ]
        embed = create_embed(
            title=t(context, "wz.reset_roles.preview_title"),
            description=t(context, "wz.reset.preview_instructions"),
        )
        embed.add_field(
            name=t(context, "wz.reset_roles.affected", count=len(reset_ids)),
            value=_role_names(
                self.guild, reset_ids, context, "wz.reset_roles.no_roles_to_reset"
            ),
            inline=False,
        )
        embed.add_field(
            name=t(context, "wz.reset.ignored", count=len(self.selected_ids)),
            value=_role_names(
                self.guild,
                sorted(self.selected_ids),
                context,
                "wz.reset_roles.no_exceptions",
            ),
            inline=False,
        )
        return embed

    def _update_confirm_button(self) -> None:
        if self.confirm_button is not None:
            self.confirm_button.disabled = not (self.allowed_ids - self.selected_ids)

    async def on_selection_changed(self, interaction: discord.Interaction) -> None:
        """Show ignored roles separately and disable resets with no targets."""
        self._update_confirm_button()
        await edit_interaction_response(
            interaction,
            content=None,
            embed=self.confirmation_embed(interaction),
            view=self,
        )

    @discord.ui.button(
        label="Reset roles",
        style=discord.ButtonStyle.danger,
        custom_id="wz_reset_roles_confirm",
        row=1,
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
                module: WzModule = await manager.get_module(self.guild, WzModule)
                configured_roles = await module.roles.get(guild=self.guild)
                configured_ids = {record.role for record in configured_roles or ()}
                roles = [
                    role
                    for role_id in self.role_ids
                    if role_id in configured_ids
                    and role_id not in self.selected_ids
                    and (role := self.guild.get_role(role_id)) is not None
                    and not role.is_default()
                    and not role.managed
                ]
                if not roles:
                    content = t(interaction, "wz.reset_roles.no_roles_to_reset")
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
                                _logger.exception(
                                    "%s Failed to remove WZ roles %s from member %s.",
                                    log_guild(self.guild),
                                    [role.id for role in held_roles],
                                    member.id,
                                )
                    except discord.HTTPException:
                        member_fetch_failed = True
                        _logger.exception(
                            "%s Could not fetch all members for the WZ role reset.",
                            log_interaction(interaction),
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
            _logger.exception(
                "%s Could not fetch all members for the WZ role reset.",
                log_interaction(interaction),
            )
            content = t(interaction, "wz.reset_roles.error")
        except Exception:
            _logger.exception(
                "%s WZ reset-roles failed.",
                log_interaction(interaction),
            )
            content = t(interaction, "wz.reset_roles.error")
        await self.finish(interaction, content)

    @discord.ui.button(
        label="Cancel",
        style=discord.ButtonStyle.secondary,
        custom_id="wz_reset_roles_cancel",
        row=1,
    )
    async def cancel(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.stop()
        await self.finish(interaction, t(interaction, "wz.reset_roles.cancelled"))

@app_commands.command(
    name="reset-roles",
    description=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get(
            "command.description.wz.reset_roles", "-"
        ),
        key="wz.reset_roles.description",
    ),
)
@app_commands.checks.has_any_role(*MODERATOR_ROLES)
@app_commands.checks.bot_has_permissions(manage_roles=True)
async def reset_roles(interaction: discord.Interaction) -> None:
    await interaction.response.defer(ephemeral=True)
    try:
        guild = interaction.guild
        manager = getattr(interaction.client, "module_manager", None)
        if guild is None or manager is None:
            await send_temporary_followup(
                interaction, t(interaction, "wz.reset_roles.error")
            )
            return

        module: WzModule = await manager.get_module(guild, WzModule)
        configured_roles = await module.roles.get(guild=guild)
        roles = [
            role
            for record in configured_roles or ()
            if (role := guild.get_role(record.role)) is not None
            and not role.is_default()
            and not role.managed
        ]
        if not roles:
            await send_temporary_followup(
                interaction, t(interaction, "wz.reset_roles.no_roles")
            )
            return

        roles.sort(key=lambda role: (role.name.casefold(), role.id))
        role_ids = [role.id for role in roles]
        view = ResetRolesConfirmation(
            guild=guild,
            owner_id=interaction.user.id,
            role_ids=role_ids,
            context=interaction,
        )
        message = await send_followup(
            interaction,
            embed=view.confirmation_embed(interaction),
            view=view,
            ephemeral=True,
            wait=True,
        )
        view.message = message
    except Exception as error:
        _logger.exception(
            "%s WZ reset-roles preparation failed: %s",
            log_interaction(interaction),
            error,
        )
        await send_temporary_followup(
            interaction, t(interaction, "wz.reset_roles.error")
        )
