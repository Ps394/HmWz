from __future__ import annotations

import logging

import discord
from discord import app_commands

from hmwz import utils
from hmwz.i18n import CommandLocalizations, t
from hmwz.ui import EphemeralView
from hmwz.modules.hs.qs.module import QsRegistrationModule

_logger = logging.getLogger(__name__)


class QsChannelsResetConfirmation(EphemeralView):
    def __init__(
        self,
        *,
        guild: discord.Guild,
        owner_id: int,
        channel_ids: list[int],
        context: discord.Interaction,
    ) -> None:
        super().__init__(timeout=120)
        self.guild = guild
        self.owner_id = owner_id
        self.channel_ids = channel_ids
        self.ignore_pinned = True
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                if item.custom_id == "qs_reset_channels_confirm":
                    item.label = t(context, "qs.reset_channels.confirm_button")
                elif item.custom_id == "qs_reset_channels_cancel":
                    item.label = t(context, "qs.reset_channels.cancel_button")
                elif item.custom_id == "qs_reset_channels_toggle_pinned":
                    item.label = t(context, "qs.reset_channels.pinned_toggle_include")

    def confirmation_content(self, context: discord.Interaction) -> str:
        return t(
            context,
            "qs.reset_channels.confirmation",
            channel_names="\n".join(
                f"<#{channel_id}>" for channel_id in self.channel_ids
            ),
            pinned_status=t(
                context,
                "qs.reset_channels.pinned_excluded"
                if self.ignore_pinned
                else "qs.reset_channels.pinned_included",
            ),
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        await self.send_temporary_response(
            interaction, t(interaction, "qs.reset_channels.owner")
        )
        return False

    @discord.ui.button(
        label="Pinned messages excluded",
        style=discord.ButtonStyle.secondary,
        custom_id="qs_reset_channels_toggle_pinned",
    )
    async def toggle_pinned(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.ignore_pinned = not self.ignore_pinned
        button.label = t(
            interaction,
            "qs.reset_channels.pinned_toggle_include"
            if self.ignore_pinned
            else "qs.reset_channels.pinned_toggle_exclude",
        )
        await interaction.response.edit_message(
            content=self.confirmation_content(interaction), view=self
        )

    @discord.ui.button(
        label="Confirm cleanup",
        style=discord.ButtonStyle.danger,
        custom_id="qs_reset_channels_confirm",
    )
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.defer()
        self.stop()
        try:
            manager = getattr(interaction.client, "module_manager", None)
            if manager is None:
                content = t(interaction, "qs.reset_channels.error")
            else:
                module: QsRegistrationModule = await manager.get_module(
                    self.guild, QsRegistrationModule
                )
                configured = set(
                    await module.purge_channels.get(guild=self.guild) or ()
                )
                target_ids = [
                    channel_id
                    for channel_id in self.channel_ids
                    if channel_id in configured
                ]
                deleted_count = 0
                failed_channels: list[str] = []
                for channel_id in target_ids:
                    channel = await utils.fetch_channel(self.guild, channel_id)
                    if channel is None:
                        failed_channels.append(f"<#{channel_id}>")
                        _logger.warning(
                            "Configured QS cleanup channel %s is missing or is not a text channel in guild %s.",
                            channel_id,
                            self.guild.id,
                        )
                        continue
                    try:
                        deleted = await channel.purge(
                            limit=None,
                            check=lambda message: (
                                not self.ignore_pinned or not message.pinned
                            ),
                            reason=f"QS reset-channels by {interaction.user}",
                        )
                        deleted_count += len(deleted)
                    except discord.HTTPException:
                        failed_channels.append(channel.mention)
                        _logger.exception(
                            "Failed to clean QS channel %s (%s) in guild %s.",
                            channel.name,
                            channel.id,
                            self.guild.id,
                        )

                content = t(
                    interaction,
                    "qs.reset_channels.partial_failure"
                    if failed_channels
                    else "qs.reset_channels.success",
                    deleted_count=deleted_count,
                    channel_names=", ".join(failed_channels),
                )
        except Exception:
            _logger.exception(
                "%s QS reset-channels failed.", utils.log_interaction(interaction)
            )
            content = t(interaction, "qs.reset_channels.error")
        await self.finish(interaction, content)

    @discord.ui.button(
        label="Cancel",
        style=discord.ButtonStyle.secondary,
        custom_id="qs_reset_channels_cancel",
    )
    async def cancel(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.finish(interaction, t(interaction, "qs.reset_channels.cancelled"))


@app_commands.command(
    name="reset-channels",
    description=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get(
            "command.description.qs.reset_channels",
            "Clean configured QS channels",
        ),
        key="qs.reset_channels.description",
    ),
)
@app_commands.checks.has_any_role("Offiziere", "Moderator")
@app_commands.checks.bot_has_permissions(manage_messages=True)
async def reset_channels(interaction: discord.Interaction) -> None:
    await interaction.response.defer(ephemeral=True)
    try:
        guild = interaction.guild
        manager = getattr(interaction.client, "module_manager", None)
        if guild is None or manager is None:
            await interaction.followup.send(
                t(interaction, "qs.reset_channels.error"), ephemeral=True
            )
            return
        module: QsRegistrationModule = await manager.get_module(
            guild, QsRegistrationModule
        )
        channel_ids = await module.purge_channels.get(guild=guild)
        if not channel_ids:
            await interaction.followup.send(
                t(interaction, "qs.reset_channels.no_channels"), ephemeral=True
            )
            return
        view = QsChannelsResetConfirmation(
            guild=guild,
            owner_id=interaction.user.id,
            channel_ids=list(channel_ids),
            context=interaction,
        )
        view.message = await interaction.followup.send(
            view.confirmation_content(interaction),
            view=view,
            ephemeral=True,
            wait=True,
        )
    except Exception:
        _logger.exception(
            "%s QS reset-channels preparation failed.",
            utils.log_interaction(interaction),
        )
        await interaction.followup.send(
            t(interaction, "qs.reset_channels.error"), ephemeral=True
        )
