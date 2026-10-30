import logging

import discord
from discord import app_commands

from hmwz.i18n import CommandLocalizations, t
from hmwz.ui.components.ephemeral_view import EphemeralView
from hmwz.utils.loaders import fetch_channel
from hmwz.utils.interactions import log_interaction
from hmwz.modules.hs.wz.module import WzRegistrationModule

logger = logging.getLogger(__name__)
_MAX_PREVIEW_LENGTH = 1400


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


class CleanChannelsConfirmation(EphemeralView):
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
                if item.custom_id == "wz_clean_channels_confirm":
                    item.label = t(context, "wz.clean_channels.confirm_button")
                elif item.custom_id == "wz_clean_channels_cancel":
                    item.label = t(context, "wz.clean_channels.cancel_button")
                else:
                    item.label = t(
                        context,
                        "wz.clean_channels.pinned_toggle_include"
                        if self.ignore_pinned
                        else "wz.clean_channels.pinned_toggle_exclude",
                    )

    def confirmation_content(self, context: discord.Interaction) -> str:
        return t(
            context,
            "wz.clean_channels.confirmation",
            channel_names=_channel_names(self.channel_ids, context),
            pinned_status=t(
                context,
                "wz.clean_channels.pinned_excluded"
                if self.ignore_pinned
                else "wz.clean_channels.pinned_included",
            ),
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        await self.send_temporary_response(
            interaction, t(interaction, "wz.clean_channels.confirmation_owner")
        )
        return False

    @discord.ui.button(
        label="Pinned messages excluded",
        style=discord.ButtonStyle.secondary,
        custom_id="wz_clean_channels_toggle_pinned",
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
        await interaction.response.edit_message(
            content=self.confirmation_content(interaction), view=self
        )

    @discord.ui.button(
        label="Confirm cleanup",
        style=discord.ButtonStyle.danger,
        custom_id="wz_clean_channels_confirm",
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
                module: WzRegistrationModule = await manager.get_module(
                    self.guild, WzRegistrationModule
                )
                configured_channels = await module.purge_channels.get(guild=self.guild)
                configured_ids = {
                    record.channel_id for record in configured_channels or ()
                }
                selected_ids = [
                    channel_id
                    for channel_id in self.channel_ids
                    if channel_id in configured_ids
                ]
                if not selected_ids:
                    content = t(interaction, "wz.clean_channels.no_channels")
                else:
                    deleted_count = 0
                    failed_channels: list[str] = []
                    for channel_id in selected_ids:
                        channel = await fetch_channel(self.guild, channel_id)
                        if channel is None:
                            logger.warning(
                                "Configured WZ clean channel %s is missing or is not a text channel in guild %s.",
                                channel_id,
                                self.guild.id,
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
                            logger.exception(
                                "Failed to clean WZ channel %s (%s) in guild %s.",
                                channel.name,
                                channel.id,
                                self.guild.id,
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
            logger.exception(
                "%s WZ clean-channels failed.",
                log_interaction(interaction),
            )
            content = t(interaction, "wz.clean_channels.error")
        await self.finish(interaction, content)

    @discord.ui.button(
        label="Cancel",
        style=discord.ButtonStyle.secondary,
        custom_id="wz_clean_channels_cancel",
    )
    async def cancel(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.stop()
        await self.finish(interaction, t(interaction, "wz.clean_channels.cancelled"))


@app_commands.checks.has_any_role("Offiziere", "Moderator")
@app_commands.command(
    name="reset-channels",
    description=app_commands.locale_str(
        CommandLocalizations.get("en", {}).get(
            "command.description.wz.reset_channels", "Reset configured WZ channels"
        ),
        key="wz.reset_channels.description",
    ),
)
@app_commands.checks.bot_has_permissions(manage_messages=True)
async def clean_channels(interaction: discord.Interaction) -> None:
    await interaction.response.defer(ephemeral=True)
    try:
        guild = interaction.guild
        manager = getattr(interaction.client, "module_manager", None)
        if guild is None or manager is None:
            await interaction.followup.send(
                t(interaction, "wz.clean_channels.error"), ephemeral=True
            )
            return

        module: WzRegistrationModule = await manager.get_module(
            guild, WzRegistrationModule
        )
        configured_channels = await module.purge_channels.get(guild=guild)
        if not configured_channels:
            await interaction.followup.send(
                t(interaction, "wz.clean_channels.no_channels"), ephemeral=True
            )
            return

        channel_ids = sorted({record.channel_id for record in configured_channels})
        view = CleanChannelsConfirmation(
            guild=guild,
            owner_id=interaction.user.id,
            channel_ids=channel_ids,
            context=interaction,
        )
        message = await interaction.followup.send(
            view.confirmation_content(interaction),
            view=view,
            ephemeral=True,
            wait=True,
        )
        view.message = message
    except Exception as error:
        logger.exception(
            "%s WZ clean-channels preparation failed: %s",
            log_interaction(interaction),
            error,
        )
        await interaction.followup.send(
            t(interaction, "wz.clean_channels.error"), ephemeral=True
        )
