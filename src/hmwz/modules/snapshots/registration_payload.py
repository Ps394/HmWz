from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Literal

import discord

from hmwz import sqlite_db

from . import Snapshot

if TYPE_CHECKING:
    from hmwz.modules.registration.repositories import (
        MemberRegistrationRepository,
        RegistrationSettingsRepository,
    )

RegistrationEventType = Literal[
    "registration", "registration_change", "deregistration", "sync"
]

_logger = logging.getLogger(__name__)


class RegistrationSnapshotBuilder:
    """Build registration snapshot data from the registration repositories."""

    def __init__(
        self,
        *,
        guild: discord.Guild,
        module_key: str,
        registration: RegistrationSettingsRepository,
        registrations: MemberRegistrationRepository,
    ) -> None:
        self.guild = guild
        self.module_key = module_key
        self.registration = registration
        self.registrations = registrations

    async def build(
        self,
        *,
        channel_id: int,
        destination_channel_id: int,
        event_type: RegistrationEventType,
    ) -> Snapshot:
        """Build an immutable snapshot for one configured registration channel."""
        configuration = await self.registration.get(
            guild=self.guild, channel_id=channel_id
        )
        records = await self.registrations.get(guild=self.guild, channel_id=channel_id)
        registrations = await self._build_registrations(records or (), channel_id)
        source_channel = self.guild.get_channel_or_thread(channel_id)
        channel_name = str(channel_id)
        if source_channel is not None:
            channel_name = source_channel.name
        if configuration is not None and configuration.title:
            channel_name = configuration.title

        return Snapshot(
            destination_channel_id=destination_channel_id,
            filename=f"{self.module_key}-{channel_id}-{event_type}.json",
            payload={
                "type": event_type,
                "name": channel_name,
                "channel-id": channel_id,
                "registrations": registrations,
            },
        )

    async def _build_registrations(
        self,
        records: tuple["MemberRegistrationRepository._Data", ...],
        channel_id: int,
    ) -> list[dict[str, int | str]]:
        registrations: list[dict[str, int | str]] = []
        for record in records:
            member_id = record.member
            if member_id is None:
                _logger.warning(
                    "%s Skipping registration without a member ID in channel %s.",
                    sqlite_db.Base.log_prefix(self.guild),
                    channel_id,
                )
                continue
            registrations.append(
                await self._build_member_registration(record, member_id)
            )
        return registrations

    async def _build_member_registration(
        self,
        record: "MemberRegistrationRepository._Data",
        member_id: int,
    ) -> dict[str, int | str]:
        if not record.member_username or not record.member_display_name:
            member_names = await self.registrations.member_names(self.guild, member_id)
        else:
            member_names = None

        member_name = record.member_username
        if not member_name:
            member_name = (
                member_names[0] if member_names is not None else str(member_id)
            )
        display_name = record.member_display_name
        if not display_name:
            display_name = member_names[1] if member_names is not None else member_name
        return {
            "member_id": member_id,
            "member_name": member_name,
            "registration_alias": record.account or display_name,
        }


__all__ = ["RegistrationEventType", "RegistrationSnapshotBuilder"]
