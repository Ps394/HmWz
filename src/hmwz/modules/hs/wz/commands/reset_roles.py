from __future__ import annotations

import logging

import discord
from discord import app_commands

from hmwz.i18n import CommandLocalizations, t
from hmwz.ui.components.ephemeral_view import EphemeralView
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


class ResetRolesConfirmation(EphemeralView):
    def __init__(
        self,
        *,
        guild: discord.Guild,
        owner_id: int,
        role_ids: list[int],
        context: discord.Interaction,
    ) -> None:
        super().__init__(timeout=180)
        self.guild = guild
        self.owner_id = owner_id
        self.role_ids = role_ids
        self.exception_ids: set[int] = set()
        self.page = 0
        self.select: _RoleExceptionSelect | None = None
        self.confirm_button: discord.ui.Button[ResetRolesConfirmation] | None = None
        for item in self.children:
            if not isinstance(item, discord.ui.Button):
                continue
            if item.custom_id == "wz_reset_roles_confirm":
                item.label = t(context, "wz.reset_roles.confirm_button")
                self.confirm_button = item
            elif item.custom_id == "wz_reset_roles_cancel":
                item.label = t(context, "wz.reset_roles.cancel_button")
            elif item.custom_id == "wz_reset_roles_previous":
                item.label = t(context, "wz.reset_roles.previous_page")
            elif item.custom_id == "wz_reset_roles_next":
                item.label = t(context, "wz.reset_roles.next_page")
        self._refresh_components(context)

    def confirmation_content(self, context: discord.Interaction) -> str:
        reset_ids = [
            role_id for role_id in self.role_ids if role_id not in self.exception_ids
        ]
        return t(
            context,
            "wz.reset_roles.confirmation",
            role_names=_role_names(
                self.guild, reset_ids, context, "wz.reset_roles.no_roles_to_reset"
            ),
            excluded_role_names=_role_names(
                self.guild,
                sorted(self.exception_ids),
                context,
                "wz.reset_roles.no_exceptions",
            ),
        )

    def _refresh_components(self, context: discord.Interaction) -> None:
        if self.select is not None:
            self.remove_item(self.select)
        page_roles = self.role_ids[self.page * 25 : (self.page + 1) * 25]
        roles = [
            role
            for role_id in page_roles
            if (role := self.guild.get_role(role_id)) is not None
        ]
        if roles:
            self.select = _RoleExceptionSelect(
                view=self,
                roles=roles,
                selected_ids=self.exception_ids,
                placeholder=t(context, "wz.reset_roles.select_exceptions"),
            )
            self.add_item(self.select)
        else:
            self.select = None

        for item in self.children:
            if not isinstance(item, discord.ui.Button):
                continue
            if item.custom_id == "wz_reset_roles_previous":
                item.disabled = self.page == 0
            elif item.custom_id == "wz_reset_roles_next":
                item.disabled = (self.page + 1) * 25 >= len(self.role_ids)
            elif item.custom_id == "wz_reset_roles_confirm":
                item.disabled = not any(
                    role_id not in self.exception_ids for role_id in self.role_ids
                )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        await self.send_temporary_response(
            interaction, t(interaction, "wz.reset_roles.confirmation_owner")
        )
        return False

    async def update_exceptions(
        self, interaction: discord.Interaction, selected_ids: list[int]
    ) -> None:
        page_ids = set(self.role_ids[self.page * 25 : (self.page + 1) * 25])
        self.exception_ids.difference_update(page_ids)
        self.exception_ids.update(selected_ids)
        self._refresh_components(interaction)
        await edit_interaction_response(
            interaction, content=self.confirmation_content(interaction), view=self
        )

    @discord.ui.button(
        label="Previous",
        style=discord.ButtonStyle.secondary,
        custom_id="wz_reset_roles_previous",
        row=1,
    )
    async def previous_page(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.page -= 1
        self._refresh_components(interaction)
        await edit_interaction_response(
            interaction, content=self.confirmation_content(interaction), view=self
        )

    @discord.ui.button(
        label="Next",
        style=discord.ButtonStyle.secondary,
        custom_id="wz_reset_roles_next",
        row=1,
    )
    async def next_page(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.page += 1
        self._refresh_components(interaction)
        await edit_interaction_response(
            interaction, content=self.confirmation_content(interaction), view=self
        )

    @discord.ui.button(
        label="Reset roles",
        style=discord.ButtonStyle.danger,
        custom_id="wz_reset_roles_confirm",
        row=2,
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
                    and role_id not in self.exception_ids
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
        row=2,
    )
    async def cancel(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.stop()
        await self.finish(interaction, t(interaction, "wz.reset_roles.cancelled"))


class _RoleExceptionSelect(discord.ui.Select):
    def __init__(
        self,
        *,
        view: ResetRolesConfirmation,
        roles: list[discord.Role],
        selected_ids: set[int],
        placeholder: str,
    ) -> None:
        super().__init__(
            placeholder=placeholder,
            min_values=0,
            max_values=len(roles),
            options=[
                discord.SelectOption(
                    label=role.name[:100],
                    value=str(role.id),
                    default=role.id in selected_ids,
                )
                for role in roles
            ],
            row=0,
        )
        self.reset_view = view

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.reset_view.update_exceptions(
            interaction, [int(value) for value in self.values]
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
            view.confirmation_content(interaction),
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
