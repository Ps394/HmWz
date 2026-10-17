from __future__ import annotations

import logging
from typing import Literal

import discord

from hmwz.i18n import t

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
    logger.debug("Bot can view channel %s(%s): %s", channel.name, channel.id, can_view)
    return can_view


async def _remove_registration_channel_from_purge_list(
    guild: discord.Guild,
    module: WzRegistrationModule,
    registration_channel_id: int,
) -> None:
    if not await module.purge_channels.remove(
        guild=guild, channel_id=registration_channel_id
    ):
        raise RuntimeError(
            f"Failed to remove registration channel {registration_channel_id} "
            "from the WZ purge list."
        )


async def get_selectable_channels(
    *,
    guild: discord.Guild,
    module: WzRegistrationModule,
    action: PurgeAction,
) -> list[discord.TextChannel]:
    """Return valid channels for the requested purge-list operation."""
    configured: tuple[PurgeChannel, ...] | None = await module.purge_channels.get(
        guild=guild
    )
    registration = await module.registration.get(guild=guild)
    registration_channel_id = registration.channel if registration else None

    if registration_channel_id is not None and any(
        record.channel_id == registration_channel_id for record in configured or ()
    ):
        await _remove_registration_channel_from_purge_list(
            guild=guild,
            module=module,
            registration_channel_id=registration_channel_id,
        )

    if action == "add":
        configured_ids = {record.channel_id for record in configured or ()}
        logger.debug(
            "Configured channel IDs for guild %s: %s", guild.id, configured_ids
        )
        channels = [
            channel
            for channel in guild.text_channels
            if (
                can_view_channel(channel, guild.me)
                and channel.id not in configured_ids
                and channel.id != registration_channel_id
            )
        ]
        logger.debug(
            "Selectable channels for guild %s: %s",
            guild.id,
            [channel.id for channel in channels],
        )
    else:
        channels = []
        for record in configured or ():
            channel = guild.get_channel(record.channel_id)
            if (
                isinstance(channel, discord.TextChannel)
                and channel.id != registration_channel_id
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
    ) -> None:
        super().__init__(timeout=180)
        self.guild = guild
        self.module = module
        self.owner_id = owner_id
        self.action = action

        if action == "add":
            self.add_item(
                _ChannelSelect(
                    view=self,
                    placeholder=t(guild, "wz.setup.purge_channel.select.add"),
                    channels=channels,
                )
            )
        else:
            self.add_item(
                _ChannelSelect(
                    view=self,
                    placeholder=t(guild, "wz.setup.purge_channel.select.remove"),
                    channels=channels,
                )
            )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        await interaction.response.send_message(
            t(interaction, "wz.setup.purge_channel.selection_owner"), ephemeral=True
        )
        return False

    async def process(
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
                messages = await self._add_channels(interaction, selected)
            else:
                messages = await self._remove_channels(interaction, selected)

            if rejected_ids:
                messages.append(
                    t(
                        interaction,
                        "wz.setup.purge_channel.selection_skipped",
                        channel_names=", ".join(
                            f"<#{channel_id}>" for channel_id in sorted(rejected_ids)
                        ),
                    )
                )
            content = "\n".join(messages) or t(
                interaction, "wz.setup.purge_channel.selection_no_changes"
            )
        except Exception:
            logger.exception(
                "Failed to %s WZ purge channels in guild %s.",
                self.action,
                self.guild.id,
            )
            content = t(interaction, "wz.setup.purge_channel.error")

        self.stop()
        await interaction.edit_original_response(content=content, view=None)

    async def _add_channels(
        self,
        interaction: discord.Interaction,
        channels: list[discord.TextChannel],
    ) -> list[str]:
        configured = await self.module.purge_channels.get(guild=self.guild)
        configured_ids = {record.channel_id for record in configured or ()}
        added: list[str] = []
        failed: list[str] = []

        for channel in channels:
            if len(configured_ids) >= PurgeChannel.MAX_PER_GUILD:
                failed.append(channel.mention)
                continue
            if await self.module.purge_channels.add(
                guild=self.guild, channel_id=channel.id
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
                    "wz.setup.purge_channel.add.success",
                    channel_names=", ".join(added),
                )
            )
        if failed:
            messages.append(
                t(
                    interaction,
                    "wz.setup.purge_channel.operation_failed",
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
                guild=self.guild, channel_id=channel.id
            ):
                removed.append(channel.mention)
            else:
                failed.append(channel.mention)

        messages: list[str] = []
        if removed:
            messages.append(
                t(
                    interaction,
                    "wz.setup.purge_channel.remove.success",
                    channel_names=", ".join(removed),
                )
            )
        if failed:
            messages.append(
                t(
                    interaction,
                    "wz.setup.purge_channel.operation_failed",
                    channel_names=", ".join(failed),
                )
            )
        return messages


class _ChannelSelect(discord.ui.Select):
    def __init__(
        self,
        *,
        view: PurgeChannelSelection,
        placeholder: str,
        channels: list[discord.TextChannel],
    ) -> None:
        super().__init__(
            placeholder=placeholder,
            min_values=1,
            max_values=min(len(channels), PurgeChannel.MAX_PER_GUILD),
            options=[
                discord.SelectOption(label=channel.name[:100], value=str(channel.id))
                for channel in channels
            ],
        )
        self.purge_view = view

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.purge_view.process(
            interaction,
            [int(channel_id) for channel_id in self.values],
        )
