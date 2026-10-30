from __future__ import annotations

import logging

import discord
from discord import app_commands

from hmwz.i18n import CommandLocalizations, t
from hmwz.utils.loaders import fetch_channel, fetch_member
from hmwz.utils.interactions import log_interaction
from hmwz.ui.components.ephemeral_view import EphemeralView
from hmwz.modules.hs.wz.module import WzRegistrationModule

_logger = logging.getLogger(__name__)


class RegistrationRemoveConfirmation(EphemeralView):
    def __init__(
        self,
        *,
        owner_id: int,
        guild: discord.Guild,
        channel_id: int,
        context: discord.Interaction,
    ) -> None:
        super().__init__(timeout=120)
        self.owner_id = owner_id
        self.guild = guild
        self.channel_id = channel_id
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.label = t(
                    context,
                    "wz.setup.registration.remove.confirm_button"
                    if item.custom_id == "wz_registration_remove_confirm"
                    else "wz.setup.registration.remove.cancel_button",
                )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        await interaction.response.send_message(
            t(interaction, "wz.setup.registration.remove.confirmation_owner"),
            ephemeral=True,
            delete_after=5,
        )
        return False

    @discord.ui.button(
        label="Remove",
        style=discord.ButtonStyle.danger,
        custom_id="wz_registration_remove_confirm",
    )
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.defer()
        self._disable_buttons()
        try:
            manager = getattr(interaction.client, "module_manager", None)
            if manager is None:
                await self._finish(interaction, "error")
                return

            module: WzRegistrationModule = await manager.get_module(
                self.guild, WzRegistrationModule
            )
            registration = await module.registration.get(
                guild=self.guild, channel_id=self.channel_id
            )
            if registration is None:
                await self._finish(interaction, "not_configured")
                return

            registrations = await module.registrations.get(
                guild=self.guild, channel_id=self.channel_id
            )
            role_removal_failed = False
            if registrations:
                all_registrations = await module.registrations.get(guild=self.guild)
                if all_registrations is None:
                    role_removal_failed = True
                else:
                    roles_used_elsewhere = {
                        (record.member, record.role)
                        for record in all_registrations
                        if record.channel_id != self.channel_id
                    }
                    roles_to_remove = {
                        (record.member, record.role)
                        for record in registrations
                        if record.member is not None
                        and record.role is not None
                        and (record.member, record.role) not in roles_used_elsewhere
                    }
                    role_removal_failed = await self._remove_member_roles(
                        roles_to_remove
                    )

            list_messages = await module.list.get(
                guild=self.guild, channel=self.channel_id
            )
            message_ids = {record.message for record in list_messages or ()}
            if registration.message is not None:
                message_ids.add(registration.message)
            operations = (
                module.registrations.remove(
                    guild=self.guild, channel_id=self.channel_id
                ),
                module.roles.remove(guild=self.guild, channel_id=self.channel_id),
                module.list.remove(guild=self.guild, channel=self.channel_id),
                module.purge_channels.remove(
                    guild=self.guild, registration_channel_id=self.channel_id
                ),
                module.registration.remove(
                    guild=self.guild, channel_id=self.channel_id
                ),
            )
            for operation in operations:
                if not await operation:
                    await self._finish(interaction, "error")
                    return

            bot_user = interaction.client.user
            message_removal_failed = await self._remove_messages(
                message_ids, bot_id=bot_user.id if bot_user is not None else None
            )

            for message_id in message_ids:
                module._overview_for(self.channel_id).forget_message(message_id)

            await self._finish(
                interaction,
                "partial_failure"
                if role_removal_failed or message_removal_failed
                else "success",
            )
        except Exception:
            _logger.exception(
                "%s WZ registration removal failed.",
                log_interaction(interaction),
            )
            await self._finish(interaction, "error")

    async def _remove_member_roles(self, registrations: set[tuple[int, int]]) -> bool:
        failed = False
        for member_id, role_id in registrations:
            member = await fetch_member(self.guild, member_id)
            role = self.guild.get_role(role_id)
            if member is None or role is None or role not in member.roles:
                continue
            try:
                await member.remove_roles(role, reason="WZ Registration Removal")
            except discord.HTTPException:
                failed = True
                _logger.exception(
                    "Failed to remove registration role %s from member %s in guild %s.",
                    role_id,
                    member_id,
                    self.guild.id,
                )
        return failed

    async def _remove_messages(
        self, message_ids: set[int], *, bot_id: int | None
    ) -> bool:
        channel = await fetch_channel(self.guild, self.channel_id)
        if channel is None:
            _logger.warning(
                "Could not fetch registration channel %s in guild %s to remove "
                "its bot messages.",
                self.channel_id,
                self.guild.id,
            )
            return True

        failed = bot_id is None
        if bot_id is None:
            _logger.error(
                "Could not identify the bot user to remove its messages from "
                "channel %s in guild %s.",
                self.channel_id,
                self.guild.id,
            )

        handled_message_ids: set[int] = set()

        async def delete_message(message: discord.Message) -> None:
            nonlocal failed
            handled_message_ids.add(message.id)
            try:
                await message.delete()
            except discord.NotFound:
                pass
            except discord.HTTPException:
                failed = True
                _logger.exception(
                    "Failed to delete registration message %s in channel %s.",
                    message.id,
                    self.channel_id,
                )

        for message_id in message_ids:
            try:
                message = await channel.fetch_message(message_id)
            except discord.NotFound:
                handled_message_ids.add(message_id)
                continue
            except discord.HTTPException:
                failed = True
                _logger.exception(
                    "Failed to delete registration message %s in channel %s.",
                    message_id,
                    self.channel_id,
                )
                continue
            await delete_message(message)

        if bot_id is not None:
            try:
                async for message in channel.history(limit=None):
                    if (
                        message.id not in handled_message_ids
                        and message.author.id == bot_id
                    ):
                        await delete_message(message)
            except discord.HTTPException:
                failed = True
                _logger.exception(
                    "Failed to scan bot messages in registration channel %s.",
                    self.channel_id,
                )
        return failed

    def _disable_buttons(self) -> None:
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True

    async def _finish(self, interaction: discord.Interaction, result: str) -> None:
        message = await interaction.edit_original_response(
            content=t(interaction, f"wz.setup.registration.remove.{result}"),
            view=None,
        )
        await message.delete(delay=5)

    @discord.ui.button(
        label="Cancel",
        style=discord.ButtonStyle.secondary,
        custom_id="wz_registration_remove_cancel",
    )
    async def cancel(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self._disable_buttons()
        await interaction.response.edit_message(
            content=t(interaction, "wz.setup.registration.remove.cancelled"),
            view=None,
            delete_after=5,
        )


@app_commands.checks.has_any_role("Offiziere", "Moderator")
@app_commands.checks.has_permissions(
    manage_roles=True, manage_messages=True, manage_channels=True
)
@app_commands.default_permissions(
    manage_roles=True, manage_messages=True, manage_channels=True
)
@app_commands.command(
    name="remove",
    description=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get(
            "command.description.wz.setup.registration.remove",
            "Remove this registration and all its sign-ups",
        ),
        key="wz.setup.registration.remove.description",
    ),
)
async def remove(interaction: discord.Interaction) -> None:
    guild = interaction.guild
    channel_id = interaction.channel_id
    manager = getattr(interaction.client, "module_manager", None)
    if guild is None or channel_id is None or manager is None:
        await interaction.response.send_message(
            t(interaction, "wz.setup.registration.remove.error"),
            ephemeral=True,
            delete_after=5,
        )
        return

    try:
        module: WzRegistrationModule = await manager.get_module(
            guild, WzRegistrationModule
        )
        if await module.registration.get(guild=guild, channel_id=channel_id) is None:
            await interaction.response.send_message(
                t(interaction, "wz.registration.error.not_configured"),
                ephemeral=True,
                delete_after=5,
            )
            return

        view = RegistrationRemoveConfirmation(
            owner_id=interaction.user.id,
            guild=guild,
            channel_id=channel_id,
            context=interaction,
        )
        await interaction.response.send_message(
            t(interaction, "wz.setup.registration.remove.confirmation"),
            view=view,
            ephemeral=True,
        )
        view.message = await interaction.original_response()
    except Exception:
        _logger.exception(
            "%s WZ setup registration removal prompt failed.",
            log_interaction(interaction),
        )
        await interaction.response.send_message(
            t(interaction, "wz.setup.registration.remove.error"),
            ephemeral=True,
            delete_after=5,
        )
