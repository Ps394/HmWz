"""Focused application services for registration mutations."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import discord

from hmwz.i18n import t
from hmwz.ui.messages import send_temporary_followup
from hmwz.utils.loaders import fetch_role

if TYPE_CHECKING:
    from .module import RegistrationModule


class RegistrationMutationService:
    """Coordinate registration add/remove operations and Discord roles."""

    def __init__(self, module: RegistrationModule) -> None:
        self.module = module
        self._channel_locks: dict[int, asyncio.Lock] = {}

    async def handle(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
        *,
        response_deferred: bool = False,
    ) -> None:
        guild = interaction.guild
        member = interaction.user
        channel_id = interaction.channel_id
        if (
            guild is None
            or not isinstance(member, discord.Member)
            or channel_id is None
        ):
            return
        if not response_deferred:
            await interaction.response.defer(ephemeral=True)

        lock = self._channel_locks.setdefault(channel_id, asyncio.Lock())
        async with lock:
            records = await self.module.registrations.get(
                guild=guild,
                member=member.id,
                account="",
                channel_id=channel_id,
            )
            current = records[0] if records else None
            if current is not None and current.role == role.id:
                await self.remove(
                    interaction,
                    guild,
                    member,
                    role,
                    channel_id,
                )
                return
            await self.add(
                interaction,
                guild,
                member,
                role,
                channel_id,
                current,
            )

    async def remove(
        self,
        interaction: discord.Interaction,
        guild: discord.Guild,
        member: discord.Member,
        role: discord.Role,
        channel_id: int,
    ) -> None:
        if not await self.module.registrations.remove(
            guild=guild,
            member=member.id,
            account="",
            channel_id=channel_id,
        ):
            await self.module._send_registration_error(interaction)
            return

        remaining = await self.module.registrations.get(
            guild=guild,
            member=member.id,
            channel_id=channel_id,
        )
        if role.id not in {
            item.role for item in remaining or () if item.role is not None
        }:
            await member.remove_roles(
                role,
                reason=f"{self.module.module_key.upper()} deregistration",
            )
        await send_temporary_followup(
            interaction,
            t(
                interaction,
                f"{self.module.module_key}.overview.registration.remove_registration",
                role_name=role.name,
            ),
            ephemeral=True,
        )
        await self.module.queue_registration_refresh(channel_id)

    async def add(
        self,
        interaction: discord.Interaction,
        guild: discord.Guild,
        member: discord.Member,
        role: discord.Role,
        channel_id: int,
        current,
    ) -> None:
        if current is None and self.module.max_players is not None:
            count = await self.module.registrations.count(
                guild=guild,
                channel_id=channel_id,
            )
            if count >= self.module.max_players:
                await send_temporary_followup(
                    interaction,
                    t(
                        interaction,
                        f"{self.module.module_key}.overview.registration.full",
                        max_players=self.module.max_players,
                    ),
                    ephemeral=True,
                )
                return

        if not await self.module.registrations.add(
            guild=guild,
            member=member.id,
            role=role.id,
            account="",
            channel_id=channel_id,
            member_username=member.name,
            member_display_name=member.display_name,
            role_name=role.name,
        ):
            await self.module._send_registration_error(interaction)
            return

        is_update = current is not None and current.role != role.id
        if current is not None and current.role is not None and current.role != role.id:
            await self._remove_previous_role(
                guild,
                member,
                current.role,
                channel_id,
            )
        await member.add_roles(
            role,
            reason=f"{self.module.module_key.upper()} registration",
        )
        await send_temporary_followup(
            interaction,
            t(
                interaction,
                f"{self.module.module_key}.overview.registration."
                f"{'update_registration' if is_update else 'new_registration'}",
                role_name=role.name,
            ),
            ephemeral=True,
        )
        await self.module.queue_registration_refresh(channel_id)

    async def _remove_previous_role(
        self,
        guild: discord.Guild,
        member: discord.Member,
        role_id: int,
        channel_id: int,
    ) -> None:
        remaining = await self.module.registrations.get(
            guild=guild,
            member=member.id,
            channel_id=channel_id,
        )
        if any(item.role == role_id for item in remaining or ()):
            return
        old_role = await fetch_role(guild, role_id)
        if old_role is not None:
            await member.remove_roles(
                old_role,
                reason=f"{self.module.module_key.upper()} registration update",
            )
