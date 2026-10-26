from __future__ import annotations

import logging

import discord

from hmwz import utils
from hmwz.i18n import t
from hmwz.ui import EphemeralView

from ....module import WzRegistrationModule
from .channels import PurgeAction, get_selectable_channels
from .components import (
    PurgeChannelConfirmation,
    _ChannelPageButton,
    _ChannelReviewButton,
    _ChannelSelect,
)
from .operations import add_channels, remove_channels

logger = logging.getLogger(__name__)


class PurgeChannelSelection(EphemeralView):
    """Ephemere Mehrfachauswahl für Bereinigungskanäle."""

    def __init__(
        self,
        *,
        guild: discord.Guild,
        module: WzRegistrationModule,
        owner_id: int,
        action: PurgeAction,
        channels: list[discord.TextChannel],
        max_values: int,
        registration_channel_id: int | None,
    ) -> None:
        super().__init__(timeout=180)
        self.guild = guild
        self.module = module
        self.owner_id = owner_id
        self.action = action
        self.registration_channel_id = registration_channel_id
        self.max_values = max_values
        self.channels = channels
        self.page = 0
        self.selected_channel_ids: set[int] = set()
        self._update_components(guild)

    def _update_components(self, context: discord.Interaction | discord.Guild) -> None:
        self.clear_items()
        start = self.page * 25
        page_channels = self.channels[start : start + 25]
        page_channel_ids = {channel.id for channel in page_channels}
        selected_on_page = self.selected_channel_ids & page_channel_ids
        remaining = self.max_values - len(self.selected_channel_ids - page_channel_ids)
        select = _ChannelSelect(
            view=self,
            placeholder=t(
                context,
                "wz.setup.channel.select.add"
                if self.action == "add"
                else "wz.setup.channel.select.remove",
            ),
            channels=page_channels,
            max_values=min(len(page_channels), remaining),
            selected_ids=selected_on_page,
        )
        select.disabled = remaining <= 0
        self.add_item(select)
        if self.page > 0:
            self.add_item(
                _ChannelPageButton(
                    view=self,
                    label=t(context, "wz.setup.channel.previous_page"),
                    direction=-1,
                )
            )
        if start + 25 < len(self.channels):
            self.add_item(
                _ChannelPageButton(
                    view=self,
                    label=t(context, "wz.setup.channel.next_page"),
                    direction=1,
                )
            )
        review = _ChannelReviewButton(
            view=self,
            label=t(context, "wz.setup.channel.review"),
        )
        review.disabled = not self.selected_channel_ids
        self.add_item(review)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        await self.send_temporary_response(
            interaction, t(interaction, "wz.setup.channel.selection_owner")
        )
        return False

    async def process(
        self, interaction: discord.Interaction, selected_channel_ids: list[int]
    ) -> None:
        try:
            selectable = await get_selectable_channels(
                guild=self.guild,
                module=self.module,
                action=self.action,
                registration_channel_id=self.registration_channel_id,
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
            confirmation = PurgeChannelConfirmation(
                selection=self,
                owner_id=self.owner_id,
                selected_channel_ids=[channel.id for channel in selected],
                context=interaction,
            )
            confirmation.message = interaction.message
            self.stop()
            await interaction.response.edit_message(
                content=t(
                    interaction,
                    f"wz.setup.channel.confirmation.{self.action}",
                    channel_names="\n".join(channel.mention for channel in selected),
                ),
                view=confirmation,
            )
        except Exception:
            logger.exception(
                "%s Failed to %s WZ purge channels.",
                utils.log_interaction(interaction),
                self.action,
            )
            await self.finish(interaction, t(interaction, "wz.setup.channel.error"))

    async def select_channels(
        self, interaction: discord.Interaction, selected_ids: list[int]
    ) -> None:
        page_channel_ids = {
            channel.id
            for channel in self.channels[self.page * 25 : self.page * 25 + 25]
        }
        self.selected_channel_ids.difference_update(page_channel_ids)
        self.selected_channel_ids.update(selected_ids)
        self._update_components(interaction)
        await interaction.response.edit_message(
            content=t(
                interaction,
                "wz.setup.channel.selection_count",
                selected=len(self.selected_channel_ids),
                maximum=self.max_values,
            ),
            view=self,
        )

    async def change_page(
        self, interaction: discord.Interaction, direction: int
    ) -> None:
        self.page += direction
        self._update_components(interaction)
        await interaction.response.edit_message(
            content=t(
                interaction,
                "wz.setup.channel.select.add"
                if self.action == "add"
                else "wz.setup.channel.select.remove",
            ),
            view=self,
        )

    async def review(self, interaction: discord.Interaction) -> None:
        await self.process(interaction, sorted(self.selected_channel_ids))

    async def commit(
        self, interaction: discord.Interaction, selected_channel_ids: list[int]
    ) -> None:
        await interaction.response.defer()
        try:
            selectable = await get_selectable_channels(
                guild=self.guild,
                module=self.module,
                action=self.action,
                registration_channel_id=self.registration_channel_id,
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
                    registration_channel_id=self.registration_channel_id,
                )
            else:
                messages = await remove_channels(
                    interaction=interaction,
                    guild=self.guild,
                    module=self.module,
                    channels=selected,
                    registration_channel_id=self.registration_channel_id,
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
            logger.exception(
                "%s Failed to %s WZ purge channels.",
                utils.log_interaction(interaction),
                self.action,
            )
            content = t(interaction, "wz.setup.channel.error")
        self.stop()
        await self.finish(interaction, content)
