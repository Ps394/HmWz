from __future__ import annotations

import logging
from typing import Literal

import discord

from hmwz.i18n import t
from hmwz import utils

from ....models import PurgeChannel
from ....module import WzRegistrationModule

logger = logging.getLogger(__name__)
PurgeAction = Literal["add", "remove"]


def can_view_channel(
    channel: discord.TextChannel, bot_member: discord.Member | None
) -> bool:
    """Return whether the bot can view a text channel."""
    can_view = (
        bot_member is not None and channel.permissions_for(bot_member).view_channel
    )
    logger.debug(
        "Bot can view channel %s (%s) in guild %s (%s): %s",
        channel.name,
        channel.id,
        channel.guild.name,
        channel.guild.id,
        can_view,
    )
    return can_view


async def _remove_registration_channel_from_purge_list(
    guild: discord.Guild,
    module: WzRegistrationModule,
    channel_id: int,
) -> None:
    if not await module.purge_channels.remove(guild=guild, channel_id=channel_id):
        raise RuntimeError(
            f"Failed to remove registration channel {channel_id} "
            "from the WZ purge list."
        )


async def get_selectable_channels(
    *,
    guild: discord.Guild,
    module: WzRegistrationModule,
    action: PurgeAction,
    registration_channel_id: int | None,
) -> list[discord.TextChannel]:
    """Return valid channels for the requested purge-list operation."""
    configured: tuple[PurgeChannel, ...] | None = await module.purge_channels.get(
        guild=guild, registration_channel_id=registration_channel_id
    )
    registrations = await module.registration.get_all(guild=guild)
    registration_channel_ids = {
        record.channel for record in registrations or () if record.channel is not None
    }
    for channel_id in registration_channel_ids & {
        record.channel_id for record in configured or ()
    }:
        await _remove_registration_channel_from_purge_list(
            guild=guild,
            module=module,
            channel_id=channel_id,
        )
    configured = await module.purge_channels.get(
        guild=guild, registration_channel_id=registration_channel_id
    )

    if action == "add":
        all_configured = await module.purge_channels.get(guild=guild)
        configured_ids = {record.channel_id for record in all_configured or ()}
        configured_names = []
        for channel_id in configured_ids:
            channel = guild.get_channel(channel_id)
            channel_name = (
                f"{channel.name} ({channel_id})"
                if isinstance(channel, discord.TextChannel)
                else f"unknown channel ({channel_id})"
            )
            configured_names.append(channel_name)
        logger.debug(
            "Configured channels for guild %s (%s): %s",
            guild.name,
            guild.id,
            configured_names,
        )
        channels = [
            channel
            for channel in guild.text_channels
            if (
                can_view_channel(channel, guild.me)
                and channel.id not in configured_ids
                and channel.id not in registration_channel_ids
            )
        ]
        logger.debug(
            "Selectable channels for guild %s (%s): %s",
            guild.name,
            guild.id,
            [f"{channel.name} ({channel.id})" for channel in channels],
        )
    else:
        channels = []
        for record in configured or ():
            channel = guild.get_channel(record.channel_id)
            if (
                isinstance(channel, discord.TextChannel)
                and channel.id not in registration_channel_ids
            ):
                channels.append(channel)

    return sorted(channels, key=lambda channel: channel.name.casefold())


class PurgeChannelSelection(discord.ui.View):
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
        await interaction.response.send_message(
            t(interaction, "wz.setup.channel.selection_owner"), ephemeral=True
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
                await interaction.response.edit_message(
                    content=t(interaction, "wz.setup.channel.selection_no_changes"),
                    view=None,
                )
                self.stop()
                return
            await interaction.response.edit_message(
                content=t(
                    interaction,
                    f"wz.setup.channel.confirmation.{self.action}",
                    channel_names="\n".join(channel.mention for channel in selected),
                ),
                view=PurgeChannelConfirmation(
                    selection=self,
                    owner_id=self.owner_id,
                    selected_channel_ids=[channel.id for channel in selected],
                    context=interaction,
                ),
            )
        except Exception:
            logger.exception(
                "%s Failed to %s WZ purge channels.",
                utils.log_interaction(interaction),
                self.action,
            )
            message = t(interaction, "wz.setup.channel.error")
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)

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
                messages = await self._add_channels(interaction, selected)
            else:
                messages = await self._remove_channels(interaction, selected)
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
        await interaction.edit_original_response(content=content, view=None)

    async def _add_channels(
        self,
        interaction: discord.Interaction,
        channels: list[discord.TextChannel],
    ) -> list[str]:
        configured = await self.module.purge_channels.get(
            guild=self.guild,
            registration_channel_id=self.registration_channel_id,
        )
        configured_ids = {record.channel_id for record in configured or ()}
        added: list[str] = []
        failed: list[str] = []

        for channel in channels:
            if len(configured_ids) >= PurgeChannel.MAX_PER_REGISTRATION:
                failed.append(channel.mention)
                continue
            if await self.module.purge_channels.add(
                guild=self.guild,
                channel_id=channel.id,
                registration_channel_id=self.registration_channel_id or 0,
            ):
                configured_ids.add(channel.id)
                added.append(channel.mention)
            else:
                failed.append(channel.mention)

        messages: list[str] = []
        if added:
            messages.append(
                t(
                    interaction,
                    "wz.setup.channel.add.success",
                    channel_names=", ".join(added),
                )
            )
        if failed:
            messages.append(
                t(
                    interaction,
                    "wz.setup.channel.operation_failed",
                    channel_names=", ".join(failed),
                )
            )
        return messages

    async def _remove_channels(
        self,
        interaction: discord.Interaction,
        channels: list[discord.TextChannel],
    ) -> list[str]:
        removed: list[str] = []
        failed: list[str] = []

        for channel in channels:
            if await self.module.purge_channels.remove(
                guild=self.guild,
                channel_id=channel.id,
                registration_channel_id=self.registration_channel_id,
            ):
                removed.append(channel.mention)
            else:
                failed.append(channel.mention)

        messages: list[str] = []
        if removed:
            messages.append(
                t(
                    interaction,
                    "wz.setup.channel.remove.success",
                    channel_names=", ".join(removed),
                )
            )
        if failed:
            messages.append(
                t(
                    interaction,
                    "wz.setup.channel.operation_failed",
                    channel_names=", ".join(failed),
                )
            )
        return messages


class PurgeChannelConfirmation(discord.ui.View):
    def __init__(
        self,
        *,
        selection: PurgeChannelSelection,
        owner_id: int,
        selected_channel_ids: list[int],
        context: discord.Interaction,
    ) -> None:
        super().__init__(timeout=180)
        self.selection = selection
        self.owner_id = owner_id
        self.selected_channel_ids = selected_channel_ids
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.label = t(
                    context,
                    "wz.setup.channel.confirm_button"
                    if item.custom_id == "wz_channel_confirm"
                    else "wz.setup.channel.cancel_button",
                )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        await interaction.response.send_message(
            t(interaction, "wz.setup.channel.selection_owner"), ephemeral=True
        )
        return False

    @discord.ui.button(
        label="Confirm",
        style=discord.ButtonStyle.primary,
        custom_id="wz_channel_confirm",
    )
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.stop()
        await self.selection.commit(interaction, self.selected_channel_ids)

    @discord.ui.button(
        label="Cancel",
        style=discord.ButtonStyle.secondary,
        custom_id="wz_channel_cancel",
    )
    async def cancel(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.stop()
        self.selection.stop()
        await interaction.response.edit_message(
            content=t(interaction, "wz.setup.channel.cancelled"),
            view=None,
        )


class _ChannelSelect(discord.ui.Select):
    def __init__(
        self,
        *,
        view: PurgeChannelSelection,
        placeholder: str,
        channels: list[discord.TextChannel],
        max_values: int,
        selected_ids: set[int],
    ) -> None:
        super().__init__(
            placeholder=placeholder,
            min_values=0,
            max_values=max(1, max_values),
            options=[
                discord.SelectOption(
                    label=channel.name[:100],
                    value=str(channel.id),
                    default=channel.id in selected_ids,
                )
                for channel in channels
            ],
        )
        self.purge_view = view

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.purge_view.select_channels(
            interaction,
            [int(channel_id) for channel_id in self.values],
        )


class _ChannelPageButton(discord.ui.Button):
    def __init__(
        self,
        *,
        view: PurgeChannelSelection,
        label: str,
        direction: int,
    ) -> None:
        super().__init__(label=label, style=discord.ButtonStyle.secondary)
        self.selection = view
        self.direction = direction

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.selection.change_page(interaction, self.direction)


class _ChannelReviewButton(discord.ui.Button):
    def __init__(self, *, view: PurgeChannelSelection, label: str) -> None:
        super().__init__(label=label, style=discord.ButtonStyle.primary)
        self.selection = view

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.selection.review(interaction)
