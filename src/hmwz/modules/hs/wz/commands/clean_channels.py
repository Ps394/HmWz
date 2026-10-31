from __future__ import annotations

import logging

import discord
from discord import app_commands

from hmwz.i18n import CommandLocalizations, t
from hmwz.ui.components.entity_selection import EntitySelectionView
from hmwz.ui.embeds import create_embed
from hmwz.ui.messages import (
    edit_interaction_response,
    send_followup,
    send_temporary_followup,
)
from hmwz.utils.interactions import log_guild, log_interaction
from hmwz.utils.loaders import fetch_channel
from hmwz.modules.hs.wz.module import WzModule

_logger = logging.getLogger(__name__)
_MAX_PREVIEW_LENGTH = 700


def _channel_names(channel_ids: list[int], context: discord.Interaction) -> str:
    names = [f"<#{channel_id}>" for channel_id in channel_ids]
    result = "\n".join(names)
    if len(result) <= _MAX_PREVIEW_LENGTH:
        return result
    visible_names: list[str] = []
    for name in names:
        candidate = "\n".join([*visible_names, name])
        if len(candidate) > _MAX_PREVIEW_LENGTH:
            break
        visible_names.append(name)
    hidden_count = len(names) - len(visible_names)
    return "\n".join(
        [
            *visible_names,
            t(context, "wz.clean_channels.more_channels", count=hidden_count),
        ]
    )


class CleanChannelsConfirmation(EntitySelectionView):
    def __init__(
        self,
        *,
        guild: discord.Guild,
        owner_id: int,
        channel_ids: list[int],
        context: discord.Interaction,
    ) -> None:
        options = []
        for channel_id in channel_ids:
            channel = guild.get_channel(channel_id)
            options.append(
                discord.SelectOption(
                    label=channel.name[:100]
                    if isinstance(channel, discord.TextChannel)
                    else str(channel_id),
                    value=str(channel_id),
                )
            )
        super().__init__(
            owner_id=owner_id,
            kind="channel",
            allowed_ids=channel_ids,
            max_selected=len(channel_ids),
            options=options,
            placeholder=t(context, "wz.clean_channels.select_exceptions"),
            owner_message=t(context, "wz.clean_channels.confirmation_owner"),
            invalid_message=t(context, "wz.reset.invalid_exceptions"),
            timeout=120,
        )
        self.guild = guild
        self.owner_id = owner_id
        self.channel_ids = channel_ids
        self.ignore_pinned = True
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                if item.custom_id == "wz_clean_channels_confirm":
                    item.label = t(context, "wz.clean_channels.confirm_button")
                elif item.custom_id == "wz_clean_channels_cancel":
                    item.label = t(context, "wz.clean_channels.cancel_button")
                elif item.custom_id == "wz_clean_channels_toggle_pinned":
                    item.label = t(
                        context,
                        "wz.clean_channels.pinned_toggle_include"
                        if self.ignore_pinned
                        else "wz.clean_channels.pinned_toggle_exclude",
                    )

    def confirmation_embed(self, context: discord.Interaction) -> discord.Embed:
        """Preview cleanup targets, ignored channels and pinned-message behavior."""
        reset_ids = [
            channel_id
            for channel_id in self.channel_ids
            if channel_id not in self.selected_ids
        ]
        embed = create_embed(
            title=t(context, "wz.clean_channels.preview_title"),
            description=t(context, "wz.reset.preview_instructions")
            + "\n\n"
            + t(context, "wz.clean_channels.warning"),
        )
        embed.add_field(
            name=t(context, "wz.clean_channels.affected", count=len(reset_ids)),
            value=_channel_names(reset_ids, context) or t(context, "wz.reset.none"),
            inline=False,
        )
        embed.add_field(
            name=t(context, "wz.reset.ignored", count=len(self.selected_ids)),
            value=_channel_names(sorted(self.selected_ids), context)
            or t(context, "wz.reset.none"),
            inline=False,
        )
        embed.add_field(
            name=t(context, "wz.clean_channels.pinned_label"),
            value=t(
                context,
                "wz.clean_channels.pinned_excluded"
                if self.ignore_pinned
                else "wz.clean_channels.pinned_included",
            ),
            inline=False,
        )
        return embed

    async def on_selection_changed(self, interaction: discord.Interaction) -> None:
        """Refresh the preview and prevent confirming an empty cleanup."""
        self.confirm.disabled = not (self.allowed_ids - self.selected_ids)
        await edit_interaction_response(
            interaction,
            content=None,
            embed=self.confirmation_embed(interaction),
            view=self,
        )

    @discord.ui.button(
        label="Pinned messages excluded",
        style=discord.ButtonStyle.secondary,
        custom_id="wz_clean_channels_toggle_pinned",
        row=1,
    )
    async def toggle_pinned(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.ignore_pinned = not self.ignore_pinned
        button.label = t(
            interaction,
            "wz.clean_channels.pinned_toggle_include"
            if self.ignore_pinned
            else "wz.clean_channels.pinned_toggle_exclude",
        )
        await edit_interaction_response(
            interaction,
            content=None,
            embed=self.confirmation_embed(interaction),
            view=self,
        )

    @discord.ui.button(
        label="Confirm cleanup",
        style=discord.ButtonStyle.danger,
        custom_id="wz_clean_channels_confirm",
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
                content = t(interaction, "wz.clean_channels.error")
            else:
                module: WzModule = await manager.get_module(self.guild, WzModule)
                configured_channels = await module.channels.get(guild=self.guild)
                configured_ids = {
                    record.channel_id for record in configured_channels or ()
                }
                selected_ids = [
                    channel_id
                    for channel_id in self.channel_ids
                    if channel_id in configured_ids
                    and channel_id not in self.selected_ids
                ]
                if not selected_ids:
                    content = t(interaction, "wz.clean_channels.no_channels")
                else:
                    deleted_count = 0
                    failed_channels: list[str] = []
                    for channel_id in selected_ids:
                        channel = await fetch_channel(self.guild, channel_id)
                        if channel is None:
                            _logger.warning(
                                "%s Configured WZ clean channel %s is missing or is not a text channel.",
                                log_guild(self.guild),
                                channel_id,
                            )
                            failed_channels.append(f"<#{channel_id}>")
                            continue
                        try:
                            deleted = await channel.purge(
                                limit=None,
                                check=lambda message: (
                                    not self.ignore_pinned or not message.pinned
                                ),
                                reason=f"WZ clean-channels by {interaction.user}",
                            )
                            deleted_count += len(deleted)
                        except discord.HTTPException:
                            failed_channels.append(channel.mention)
                            _logger.exception(
                                "%s Failed to clean WZ channel %s (%s).",
                                log_guild(self.guild),
                                channel.name,
                                channel.id,
                            )

                    content = t(
                        interaction,
                        "wz.clean_channels.partial_failure"
                        if failed_channels
                        else "wz.clean_channels.success",
                        deleted_count=deleted_count,
                        channel_names=", ".join(failed_channels),
                    )
        except Exception:
            _logger.exception(
                "%s WZ clean-channels failed.",
                log_interaction(interaction),
            )
            content = t(interaction, "wz.clean_channels.error")
        await self.finish(interaction, content)

    @discord.ui.button(
        label="Cancel",
        style=discord.ButtonStyle.secondary,
        custom_id="wz_clean_channels_cancel",
        row=1,
    )
    async def cancel(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.stop()
        await self.finish(interaction, t(interaction, "wz.clean_channels.cancelled"))



@app_commands.command(
    name="reset-channels",
    description=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get(
            "command.description.wz.reset_channels", "Reset configured WZ channels"
        ),
        key="wz.reset_channels.description",
    ),
)
@app_commands.checks.has_any_role("Offiziere", "offiziere", "Moderator", "moderator", "officier", "Officier")
@app_commands.checks.bot_has_permissions(manage_messages=True)
async def clean_channels(interaction: discord.Interaction) -> None:
    await interaction.response.defer(ephemeral=True)
    try:
        guild = interaction.guild
        manager = getattr(interaction.client, "module_manager", None)
        if guild is None or manager is None:
            await send_temporary_followup(
                interaction, t(interaction, "wz.clean_channels.error")
            )
            return

        module: WzModule = await manager.get_module(guild, WzModule)
        configured_channels = await module.channels.get(guild=guild)
        if not configured_channels:
            await send_temporary_followup(
                interaction, t(interaction, "wz.clean_channels.no_channels")
            )
            return

        channel_ids = sorted({record.channel_id for record in configured_channels})
        view = CleanChannelsConfirmation(
            guild=guild,
            owner_id=interaction.user.id,
            channel_ids=channel_ids,
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
            "%s WZ clean-channels preparation failed: %s",
            log_interaction(interaction),
            error,
        )
        await send_temporary_followup(
            interaction, t(interaction, "wz.clean_channels.error")
        )
