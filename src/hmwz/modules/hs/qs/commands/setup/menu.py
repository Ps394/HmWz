from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import cast

import discord
from discord import app_commands

from hmwz.i18n import CommandLocalizations, t
from hmwz.modules.hs.ephemeral_view import (
    EphemeralView,
    delete_temporary_message,
    send_temporary_followup,
)
from hmwz.modules.hs.qs.module import QsRegistrationModule
from hmwz.utils import log_interaction

from . import configure as configure_module
from . import message as message_module
from . import role_remove as role_remove_module

_logger = logging.getLogger(__name__)


class _QsRoleSelection(EphemeralView):
    def __init__(
        self, *, owner_id: int, action: str, context: discord.Interaction
    ) -> None:
        super().__init__(timeout=180)
        self.owner_id = owner_id
        self.action = action
        placeholder = t(
            context,
            "qs.setup.menu.add_role"
            if action == "add"
            else "qs.setup.menu.remove_role",
        )
        for item in self.children:
            if isinstance(item, discord.ui.RoleSelect):
                item.placeholder = placeholder

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        await self.send_temporary_response(
            interaction, t(interaction, "qs.setup.menu.owner")
        )
        return False

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="Select a role")
    async def select(
        self, interaction: discord.Interaction, select: discord.ui.RoleSelect
    ) -> None:
        role = select.values[0]
        self.stop()
        if self.action == "add":
            callback = cast(
                Callable[[discord.Interaction, discord.Role], Awaitable[None]],
                configure_module.configure.callback,
            )
        else:
            callback = cast(
                Callable[[discord.Interaction, discord.Role], Awaitable[None]],
                role_remove_module.role_remove.callback,
            )
        await callback(interaction, role)
        self.stop()
        await delete_temporary_message(interaction.message)


class _QsMessageModal(discord.ui.Modal):
    def __init__(self, context: discord.Interaction) -> None:
        super().__init__(title=t(context, "qs.setup.menu.edit_message"))
        self.title_input: discord.ui.TextInput[discord.ui.Modal] = discord.ui.TextInput(
            label=t(context, "qs.setup.menu.title_label"),
            required=False,
            max_length=256,
        )
        self.description_input: discord.ui.TextInput[
            discord.ui.Modal
        ] = discord.ui.TextInput(
            label=t(context, "qs.setup.menu.description_label"),
            required=False,
            style=discord.TextStyle.paragraph,
            max_length=4000,
        )
        self.add_item(self.title_input)
        self.add_item(self.description_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        title = self.title_input.value or None
        description = self.description_input.value or None
        if title is None and description is None:
            await interaction.response.send_message(
                t(interaction, "qs.setup.menu.message_required"), ephemeral=True
            )
            return
        callback = cast(
            Callable[
                [discord.Interaction, str | None, str | None], Awaitable[None]
            ],
            message_module.message.callback,
        )
        await callback(interaction, title, description)


class QsSetupMenu(EphemeralView):
    def __init__(self, *, owner_id: int, context: discord.Interaction) -> None:
        super().__init__(timeout=180)
        self.owner_id = owner_id
        labels = {
            "qs_setup_add_role": "qs.setup.menu.add_role",
            "qs_setup_remove_role": "qs.setup.menu.remove_role",
            "qs_setup_edit_message": "qs.setup.menu.edit_message",
            "qs_setup_overview": "qs.setup.menu.overview",
        }
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                if item.custom_id is None:
                    continue
                label = labels.get(item.custom_id)
                if label is not None:
                    item.label = t(context, label)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        await self.send_temporary_response(
            interaction, t(interaction, "qs.setup.menu.owner")
        )
        return False

    async def _show_role_selection(
        self, interaction: discord.Interaction, action: str
    ) -> None:
        view = _QsRoleSelection(
            owner_id=self.owner_id, action=action, context=interaction
        )
        await interaction.response.send_message(
            t(
                interaction,
                "qs.setup.menu.add_role"
                if action == "add"
                else "qs.setup.menu.remove_role",
            ),
            view=view,
            ephemeral=True,
        )
        view.message = await interaction.original_response()

    @discord.ui.button(
        label="Add role",
        style=discord.ButtonStyle.primary,
        custom_id="qs_setup_add_role",
    )
    async def add_role_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._show_role_selection(interaction, "add")

    @discord.ui.button(
        label="Remove role",
        style=discord.ButtonStyle.secondary,
        custom_id="qs_setup_remove_role",
    )
    async def remove_role_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._show_role_selection(interaction, "remove")

    @discord.ui.button(
        label="Edit overview",
        style=discord.ButtonStyle.secondary,
        custom_id="qs_setup_edit_message",
    )
    async def edit_message_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.send_modal(_QsMessageModal(interaction))

    @discord.ui.button(
        label="Overview",
        style=discord.ButtonStyle.secondary,
        custom_id="qs_setup_overview",
    )
    async def overview_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            guild = interaction.guild
            channel_id = interaction.channel_id
            manager = getattr(interaction.client, "module_manager", None)
            if guild is None or channel_id is None or manager is None:
                content = t(interaction, "qs.setup.error")
            else:
                module: QsRegistrationModule = await manager.get_module(
                    guild, QsRegistrationModule
                )
                registrations = await module.registration.get_all(guild=guild)
                roles = await module.roles.get(guild=guild)
                registration_channels = [
                    f"<#{record.channel}>"
                    for record in registrations or ()
                    if record.channel is not None
                ]
                role_names = [
                    f"{role.mention} — <#{record.channel_id}>"
                    for record in roles or ()
                    if (role := guild.get_role(record.role)) is not None
                ]
                content = t(
                    interaction,
                    "qs.setup.menu.overview_content",
                    registration_channels="\n".join(registration_channels)
                    or t(interaction, "qs.setup.menu.none"),
                    roles="\n".join(role_names)
                    or t(interaction, "qs.setup.menu.none"),
                )
        except Exception:
            _logger.exception(
                "%s QS setup overview failed.", log_interaction(interaction)
            )
            content = t(interaction, "qs.setup.error")
        await send_temporary_followup(interaction, content)


@app_commands.command(
    name="setup",
    description=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get(
            "command.description.qs.setup", "Configure QS channels and roles"
        ),
        key="qs.setup.description",
    ),
)
@app_commands.checks.has_any_role("Offiziere", "Moderator")
async def setup(interaction: discord.Interaction) -> None:
    view = QsSetupMenu(owner_id=interaction.user.id, context=interaction)
    await interaction.response.send_message(
        t(interaction, "qs.setup.menu.title"), view=view, ephemeral=True
    )
    view.message = await interaction.original_response()
