from __future__ import annotations

import logging

import discord
from discord import app_commands

from hmwz import utils
from hmwz.i18n import CommandLocalizations, t

from hmwz.modules.hs.qs.module import QsRegistrationModule

_logger = logging.getLogger(__name__)


class QsResetConfirmation(discord.ui.View):
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
            if not isinstance(item, discord.ui.Button):
                continue
            key = (
                "qs.reset.confirm_button"
                if item.custom_id == "qs_registration_reset_confirm"
                else "qs.reset.cancel_button"
            )
            item.label = t(context, key)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        await interaction.response.send_message(
            t(interaction, "qs.reset.confirmation_owner"), ephemeral=True
        )
        return False

    @discord.ui.button(
        label="Reset",
        style=discord.ButtonStyle.danger,
        custom_id="qs_registration_reset_confirm",
    )
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.defer()
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        try:
            manager = getattr(interaction.client, "module_manager", None)
            if manager is None:
                await interaction.edit_original_response(
                    content=t(interaction, "qs.reset.error"), view=None
                )
                return
            module: QsRegistrationModule = await manager.get_module(
                self.guild, QsRegistrationModule
            )
            records = await module.registrations.get(
                guild=self.guild, channel_id=self.channel_id
            )
            role_removal_failed = False
            for record in records or ():
                if record.member is None or record.role is None:
                    continue
                member = await utils.fetch_member(self.guild, record.member)
                role = self.guild.get_role(record.role)
                if member is None or role is None:
                    continue
                try:
                    await member.remove_roles(role, reason="QS Registration Reset")
                except discord.HTTPException:
                    role_removal_failed = True
                    _logger.exception(
                        "Failed to remove QS role %s from member %s in guild %s.",
                        record.role,
                        record.member,
                        self.guild.id,
                    )

            if not await module.registrations.remove(
                guild=self.guild, channel_id=self.channel_id
            ):
                await interaction.edit_original_response(
                    content=t(interaction, "qs.reset.error"), view=None
                )
                return
            overview_updated = await module.compose_registration_overview(
                force=True, channel_id=self.channel_id
            )
            if not overview_updated:
                await interaction.edit_original_response(
                    content=t(interaction, "qs.reset.overview_failed"), view=None
                )
                return
            await interaction.edit_original_response(
                content=t(
                    interaction,
                    "qs.reset.partial_failure"
                    if role_removal_failed
                    else "qs.reset.success",
                ),
                view=None,
            )
        except Exception:
            _logger.exception(
                "%s QS registration reset failed.",
                utils.log_interaction(interaction),
            )
            await interaction.edit_original_response(
                content=t(interaction, "qs.reset.error"), view=None
            )

    @discord.ui.button(
        label="Cancel",
        style=discord.ButtonStyle.secondary,
        custom_id="qs_registration_reset_cancel",
    )
    async def cancel(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        await interaction.response.edit_message(
            content=t(interaction, "qs.reset.cancelled"), view=None
        )


@app_commands.command(
    name="reset",
    description=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get(
            "command.description.qs.registration.reset",
            "Reset QS registrations after confirmation",
        ),
        key="qs.registration.reset.description",
    ),
)
@app_commands.checks.has_any_role("Offiziere", "Moderator")
async def reset(interaction: discord.Interaction) -> None:
    guild = interaction.guild
    channel_id = interaction.channel_id
    manager = getattr(interaction.client, "module_manager", None)
    if guild is None or channel_id is None or manager is None:
        await interaction.response.send_message(
            t(interaction, "qs.reset.error"), ephemeral=True
        )
        return
    try:
        module: QsRegistrationModule = await manager.get_module(
            guild, QsRegistrationModule
        )
        registration = await module.registration.get(guild=guild, channel_id=channel_id)
        if registration is None:
            await interaction.response.send_message(
                t(interaction, "qs.registration.error.not_configured"),
                ephemeral=True,
            )
            return
        records = await module.registrations.get(guild=guild, channel_id=channel_id)
        if not records:
            await interaction.response.send_message(
                t(interaction, "qs.reset.no_registrations"), ephemeral=True
            )
            return
        await interaction.response.send_message(
            t(interaction, "qs.reset.confirmation"),
            view=QsResetConfirmation(
                owner_id=interaction.user.id,
                guild=guild,
                channel_id=channel_id,
                context=interaction,
            ),
            ephemeral=True,
        )
    except Exception:
        _logger.exception(
            "%s QS reset prompt failed.", utils.log_interaction(interaction)
        )
        await interaction.response.send_message(
            t(interaction, "qs.reset.error"), ephemeral=True
        )
