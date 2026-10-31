from __future__ import annotations

import logging

import discord

from hmwz.i18n import t
from hmwz.ui.components.entity_selection import EntitySelectionView
from hmwz.ui.embeds import create_embed
from hmwz.ui.messages import edit_interaction_response
from hmwz.utils.interactions import log_interaction

from ....module import WzModule
from .channels import ChannelAction, get_selectable_channels
from .components import ChannelConfirmation
from .operations import add_channels, remove_channels

_logger = logging.getLogger(__name__)


class ChannelSelection(EntitySelectionView):
    """Text-channel selection with a preview before confirmation."""

    def __init__(
        self,
        *,
        guild: discord.Guild,
        module: WzModule,
        owner_id: int,
        action: ChannelAction,
        channels: list[discord.TextChannel],
        max_values: int,
        context: discord.Interaction,
    ) -> None:
        super().__init__(
            owner_id=owner_id,
            kind="channel",
            allowed_ids=(channel.id for channel in channels),
            max_selected=max_values,
            placeholder=t(context, f"wz.setup.channel.select.{action}"),
            owner_message=t(context, "wz.setup.channel.selection_owner"),
            invalid_message=t(context, "wz.setup.channel.invalid_selection"),
            options=[
                discord.SelectOption(label=channel.name[:100], value=str(channel.id))
                for channel in channels
            ]
            if action == "remove"
            else None,
        )
        self.guild = guild
        self.module = module
        self.owner_id = owner_id
        self.action = action
        self.max_values = max_values
        self.channels = channels
        self.review_button.label = t(context, "wz.setup.channel.review")
        self.review_button.disabled = True
        self.cancel_button.label = t(context, "wz.setup.channel.cancel_button")

    def selection_embed(self, context: discord.Interaction) -> discord.Embed:
        """Show selected channels and the available selection limit."""
        embed = create_embed(
            title=t(context, f"wz.setup.channel.title.{self.action}"),
            description=t(
                context,
                "wz.setup.channel.selection_count",
                selected=len(self.selected_ids),
                maximum=self.max_selected,
            )
            + "\n"
            + t(context, f"wz.setup.channel.selection_rules.{self.action}"),
        )
        embed.add_field(
            name=t(context, "wz.setup.selection.preview"),
            value="\n".join(
                f"<#{channel_id}>" for channel_id in sorted(self.selected_ids)
            )
            or t(context, "wz.setup.selection.empty"),
            inline=False,
        )
        return embed

    async def on_selection_changed(self, interaction: discord.Interaction) -> None:
        """Refresh the preview and enable review only for nonempty selections."""
        self.review_button.disabled = not self.selected_ids
        await edit_interaction_response(
            interaction,
            content=None,
            embed=self.selection_embed(interaction),
            view=self,
        )

    @discord.ui.button(
        label="Review",
        style=discord.ButtonStyle.primary,
        custom_id="wz_channel_select_review",
        row=1,
    )
    async def review_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.review(interaction)

    @discord.ui.button(
        label="Cancel",
        style=discord.ButtonStyle.secondary,
        custom_id="wz_channel_select_cancel",
        row=1,
    )
    async def cancel_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.finish(interaction, t(interaction, "wz.setup.channel.cancelled"))

    async def process(
        self, interaction: discord.Interaction, selected_channel_ids: list[int]
    ) -> None:
        try:
            selectable = await get_selectable_channels(
                guild=self.guild,
                module=self.module,
                action=self.action,
            )
            selectable_by_id = {channel.id: channel for channel in selectable}
            selected = [
                selectable_by_id[channel_id]
                for channel_id in selected_channel_ids
                if channel_id in selectable_by_id
            ]
            if not selected:
                await self.finish(
                    interaction, t(interaction, "wz.setup.channel.selection_no_changes")
                )
                return
            confirmation = ChannelConfirmation(
                selection=self,
                owner_id=self.owner_id,
                selected_channel_ids=[channel.id for channel in selected],
                context=interaction,
            )
            confirmation.message = interaction.message
            self.stop()
            await edit_interaction_response(
                interaction,
                content=t(
                    interaction,
                    f"wz.setup.channel.confirmation.{self.action}",
                    channel_names="\n".join(channel.mention for channel in selected),
                ),
                embed=None,
                view=confirmation,
            )
        except Exception:
            _logger.exception(
                "%s Failed to %s WZ cleanup channels.",
                log_interaction(interaction),
                self.action,
            )
            await self.finish(interaction, t(interaction, "wz.setup.channel.error"))

    async def review(self, interaction: discord.Interaction) -> None:
        await self.process(interaction, sorted(self.selected_ids))

    async def commit(
        self, interaction: discord.Interaction, selected_channel_ids: list[int]
    ) -> None:
        await interaction.response.defer()
        try:
            selectable = await get_selectable_channels(
                guild=self.guild,
                module=self.module,
                action=self.action,
            )
            selectable_by_id = {channel.id: channel for channel in selectable}
            selected = [
                selectable_by_id[channel_id]
                for channel_id in selected_channel_ids
                if channel_id in selectable_by_id
            ]
            rejected_ids = set(selected_channel_ids) - selectable_by_id.keys()
            if self.action == "add":
                messages = await add_channels(
                    interaction=interaction,
                    guild=self.guild,
                    module=self.module,
                    channels=selected,
                )
            else:
                messages = await remove_channels(
                    interaction=interaction,
                    guild=self.guild,
                    module=self.module,
                    channels=selected,
                )
            if rejected_ids:
                messages.append(
                    t(
                        interaction,
                        "wz.setup.channel.selection_skipped",
                        channel_names=", ".join(
                            f"<#{channel_id}>" for channel_id in sorted(rejected_ids)
                        ),
                    )
                )
            content = "\n".join(messages) or t(
                interaction, "wz.setup.channel.selection_no_changes"
            )
        except Exception:
            _logger.exception(
                "%s Failed to %s WZ cleanup channels.",
                log_interaction(interaction),
                self.action,
            )
            content = t(interaction, "wz.setup.channel.error")
        self.stop()
        await self.finish(interaction, content)
