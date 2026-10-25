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


class _QsChannelSelection(EphemeralView):
    def __init__(
        self, *, owner_id: int, action: str, context: discord.Interaction
    ) -> None:
        super().__init__(timeout=180)
        self.owner_id = owner_id
        self.action = action
        for item in self.children:
            if isinstance(item, discord.ui.ChannelSelect):
                item.placeholder = t(
                    context,
                    "qs.setup.menu.add_channel"
                    if action == "add"
                    else "qs.setup.menu.remove_channel",
                )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        await self.send_temporary_response(
            interaction, t(interaction, "qs.setup.menu.owner")
        )
        return False

    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        channel_types=[discord.ChannelType.text],
        min_values=1,
        max_values=25,
        placeholder="Select QS channels",
    )
    async def select(
        self, interaction: discord.Interaction, select: discord.ui.ChannelSelect
    ) -> None:
        self.stop()
        guild = interaction.guild
        manager = getattr(interaction.client, "module_manager", None)
        if guild is None or manager is None:
            await self.finish(interaction, t(interaction, "qs.setup.error"))
            return
        try:
            module: QsRegistrationModule = await manager.get_module(
                guild, QsRegistrationModule
            )
            configured = set(await module.purge_channels.get(guild=guild) or ())
            registrations = await module.registration.get_all(guild=guild)
            registration_ids = {
                record.channel
                for record in registrations or ()
                if record.channel is not None
            }
            selected = [
                channel
                for channel in select.values
                if isinstance(channel, discord.TextChannel)
                and (
                    channel.id not in registration_ids
                    if self.action == "add"
                    else channel.id in configured
                )
            ]
            if not selected:
                await self.finish(
                    interaction, t(interaction, "qs.setup.menu.no_channel_changes")
                )
                return
            confirmation = _QsChannelConfirmation(
                owner_id=self.owner_id,
                action=self.action,
                channel_ids=[channel.id for channel in selected],
                context=interaction,
            )
            confirmation.message = interaction.message
            confirmation_key = (
                "qs.setup.menu.confirmation_add"
                if self.action == "add"
                else "qs.setup.menu.confirmation_remove"
            )
            self.stop()
            await interaction.response.edit_message(
                content=t(
                    interaction,
                    confirmation_key,
                    channel_names="\n".join(channel.mention for channel in selected),
                ),
                view=confirmation,
            )
        except Exception:
            _logger.exception(
                "%s QS channel setup failed.", log_interaction(interaction)
            )
            await self.finish(interaction, t(interaction, "qs.setup.error"))


class _QsChannelConfirmation(EphemeralView):
    def __init__(
        self,
        *,
        owner_id: int,
        action: str,
        channel_ids: list[int],
        context: discord.Interaction,
    ) -> None:
        super().__init__(timeout=120)
        self.owner_id = owner_id
        self.action = action
        self.channel_ids = channel_ids
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                if item.custom_id == "qs_setup_channel_confirm":
                    item.label = t(context, "qs.setup.menu.confirm_button")
                elif item.custom_id == "qs_setup_channel_cancel":
                    item.label = t(context, "qs.setup.menu.cancel_button")

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        await self.send_temporary_response(
            interaction, t(interaction, "qs.setup.menu.owner")
        )
        return False

    @discord.ui.button(
        label="Confirm",
        style=discord.ButtonStyle.primary,
        custom_id="qs_setup_channel_confirm",
    )
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.defer()
        self.stop()
        try:
            guild = interaction.guild
            manager = getattr(interaction.client, "module_manager", None)
            if guild is None or manager is None:
                content = t(interaction, "qs.setup.error")
            else:
                module: QsRegistrationModule = await manager.get_module(
                    guild, QsRegistrationModule
                )
                configured = set(await module.purge_channels.get(guild=guild) or ())
                registrations = await module.registration.get_all(guild=guild)
                registration_ids = {
                    record.channel
                    for record in registrations or ()
                    if record.channel is not None
                }
                eligible_ids = [
                    channel_id
                    for channel_id in self.channel_ids
                    if (
                        channel_id not in configured
                        and channel_id not in registration_ids
                        if self.action == "add"
                        else channel_id in configured
                    )
                ]
                if self.action == "add":
                    results = [
                        await module.purge_channels.add(
                            guild=guild, channel_id=channel_id
                        )
                        for channel_id in eligible_ids
                    ]
                else:
                    results = [
                        await module.purge_channels.remove(
                            guild=guild, channel_id=channel_id
                        )
                        for channel_id in eligible_ids
                    ]
                changed = sum(results)
                failed = len(results) - changed
                if failed:
                    _logger.warning(
                        "%s QS channel setup had %s failed channel changes.",
                        log_interaction(interaction),
                        failed,
                    )
                action_key = (
                    "channels_added" if self.action == "add" else "channels_removed"
                )
                content = t(interaction, f"qs.setup.menu.{action_key}", count=changed)
                if failed:
                    content = t(
                        interaction,
                        "qs.setup.menu.channels_partial",
                        count=changed,
                        failed=failed,
                    )
                elif not eligible_ids:
                    content = t(interaction, "qs.setup.menu.no_channel_changes")
        except Exception:
            _logger.exception(
                "%s QS channel setup confirmation failed.",
                log_interaction(interaction),
            )
            content = t(interaction, "qs.setup.error")
        await self.finish(interaction, content)

    @discord.ui.button(
        label="Cancel",
        style=discord.ButtonStyle.secondary,
        custom_id="qs_setup_channel_cancel",
    )
    async def cancel(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.finish(interaction, t(interaction, "qs.setup.menu.cancelled"))


class QsSetupMenu(EphemeralView):
    def __init__(self, *, owner_id: int, context: discord.Interaction) -> None:
        super().__init__(timeout=180)
        self.owner_id = owner_id
        labels = {
            "qs_setup_add_channel": "qs.setup.menu.add_channel",
            "qs_setup_remove_channel": "qs.setup.menu.remove_channel",
            "qs_setup_add_role": "qs.setup.menu.add_role",
            "qs_setup_remove_role": "qs.setup.menu.remove_role",
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

    async def _show_channel_selection(
        self, interaction: discord.Interaction, action: str
    ) -> None:
        guild = interaction.guild
        manager = getattr(interaction.client, "module_manager", None)
        if guild is None or manager is None:
            await self.send_temporary_response(
                interaction, t(interaction, "qs.setup.error")
            )
            return
        try:
            module: QsRegistrationModule = await manager.get_module(
                guild, QsRegistrationModule
            )
            configured = set(await module.purge_channels.get(guild=guild) or ())
            registration_channels = await module.registration.get_all(guild=guild)
            registration_ids = {
                record.channel
                for record in registration_channels or ()
                if record.channel is not None
            }
            available = (
                [
                    channel
                    for channel in guild.text_channels
                    if channel.id not in registration_ids
                    and channel.id not in configured
                ]
                if action == "add"
                else [
                    channel
                    for channel in guild.text_channels
                    if channel.id in configured
                ]
            )
            if not available:
                await self.send_temporary_response(
                    interaction,
                    t(
                        interaction,
                        "qs.setup.menu.no_available_channels"
                        if action == "add"
                        else "qs.setup.menu.no_channels",
                    ),
                )
                return
            view = _QsChannelSelection(
                owner_id=self.owner_id, action=action, context=interaction
            )
            await interaction.response.send_message(
                t(
                    interaction,
                    "qs.setup.menu.add_channel"
                    if action == "add"
                    else "qs.setup.menu.remove_channel",
                ),
                view=view,
                ephemeral=True,
            )
            view.message = await interaction.original_response()
        except Exception:
            _logger.exception(
                "%s QS channel selection preparation failed.",
                log_interaction(interaction),
            )
            if interaction.response.is_done():
                await send_temporary_followup(
                    interaction, t(interaction, "qs.setup.error")
                )
            else:
                await self.send_temporary_response(
                    interaction, t(interaction, "qs.setup.error")
                )

    @discord.ui.button(
        label="Add QS channel",
        style=discord.ButtonStyle.primary,
        custom_id="qs_setup_add_channel",
    )
    async def add_channel_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._show_channel_selection(interaction, "add")

    @discord.ui.button(
        label="Remove QS channel",
        style=discord.ButtonStyle.secondary,
        custom_id="qs_setup_remove_channel",
    )
    async def remove_channel_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._show_channel_selection(interaction, "remove")

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
    try:
        guild = interaction.guild
        manager = getattr(interaction.client, "module_manager", None)
        if guild is None or manager is None:
            content = t(interaction, "qs.setup.error")
        else:
            module: QsRegistrationModule = await manager.get_module(
                guild, QsRegistrationModule
            )
            registrations = await module.registration.get_all(guild=guild)
            roles = await module.roles.get(guild=guild)
            channels = await module.purge_channels.get(guild=guild)
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
                roles="\n".join(role_names) or t(interaction, "qs.setup.menu.none"),
                channels="\n".join(f"<#{channel_id}>" for channel_id in channels or ())
                or t(interaction, "qs.setup.menu.none"),
            )
    except Exception:
        _logger.exception(
            "%s QS setup configuration failed.", log_interaction(interaction)
        )
        content = t(interaction, "qs.setup.error")
    await interaction.response.send_message(content, view=view, ephemeral=True)
    view.message = await interaction.original_response()
