"""Compatibility adapter for donation overview, ranking and history messages."""

from __future__ import annotations

import re

import discord

from hmwz.modules.managed_messages import ManagedMessage, ManagedMessagesModule


class DonationManagedMessagesAdapter:
    """Keep donation content in Donation and Discord publishing shared."""

    def __init__(
        self,
        *,
        guild: discord.Guild,
        managed_messages: ManagedMessagesModule,
    ) -> None:
        self.guild = guild
        self.managed_messages = managed_messages

    @staticmethod
    def main_id(channel_id: int) -> str:
        return f"donation-{channel_id}"

    @staticmethod
    def ranking_id(channel_id: int) -> str:
        return f"donation-{channel_id}-ranking"

    @staticmethod
    def history_id(channel_id: int) -> str:
        return f"donation-{channel_id}-history"

    @staticmethod
    def channel_id(managed_id: str) -> int | None:
        match = re.fullmatch(
            r"donation-(\d+)(?:-(?:ranking|history))?",
            managed_id,
        )
        return int(match.group(1)) if match is not None else None

    def register_owner(self, *, channel_id: int) -> None:
        for managed_id in (
            self.main_id(channel_id),
            self.ranking_id(channel_id),
            self.history_id(channel_id),
        ):
            self.managed_messages.register_managed_owner(
                owner_id="donation",
                managed_id=managed_id,
            )

    async def adopt_legacy_ids(
        self,
        *,
        channel_id: int,
        overview_message_id: int | None,
        ranking_message_id: int | None,
        history_message_id: int | None,
    ) -> bool:
        mappings = (
            (self.main_id(channel_id), overview_message_id),
            (self.ranking_id(channel_id), ranking_message_id),
            (self.history_id(channel_id), history_message_id),
        )
        success = True
        for managed_id, message_id in mappings:
            if message_id is None:
                continue
            success = (
                await self.managed_messages.messages.save(
                    ManagedMessage(
                        guild_id=self.guild.id,
                        managed_id=managed_id,
                        channel_id=channel_id,
                        message_id=message_id,
                        target_kind="channel",
                    )
                )
                and success
            )
        return success

    async def publish(
        self,
        *,
        channel_id: int,
        managed_id: str,
        target_channel_id: int,
        embed: discord.Embed,
        view: discord.ui.View | None = None,
    ) -> bool:
        self.register_owner(channel_id=channel_id)
        return await self.managed_messages.publish(
            managed_id=managed_id,
            channel_id=target_channel_id,
            embeds=(embed,),
            view=view,
        )

    async def delete(
        self,
        *,
        channel_id: int,
    ) -> bool:
        success = True
        for managed_id in (
            self.main_id(channel_id),
            self.ranking_id(channel_id),
            self.history_id(channel_id),
        ):
            success = (
                await self.managed_messages.delete(managed_id=managed_id)
                and success
            )
        return success
