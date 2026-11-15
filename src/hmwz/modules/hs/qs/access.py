"""Role and moderator checks shared by all Qs interactions."""

from __future__ import annotations

from typing import TYPE_CHECKING

import aiosqlite
import discord

from hmwz.configuration import MODERATOR_ROLES
from hmwz.i18n import t
from hmwz.ui.messages import send_interaction_message

from .models import Configuration, Phase

if TYPE_CHECKING:
    from .module import QsModule


def can_manage(member: discord.Member | discord.User) -> bool:
    """Match the project's moderator/officer role convention."""
    return isinstance(member, discord.Member) and any(
        role.name in MODERATOR_ROLES for role in member.roles
    )


class QsAccess:
    """Validate who may act on an active Qs event and which accounts they own."""

    def __init__(self, module: QsModule) -> None:
        self.module = module

    async def game_accounts_for(self, member_id: int) -> tuple[str, ...]:
        """Return linked accounts, treating an uninitialized account table as empty."""
        try:
            return await self.module.game_accounts.accounts_for_member(
                guild_id=self.module.guild.id, member_id=member_id
            )
        except aiosqlite.OperationalError as error:
            if "no such table: gameaccounts" in str(error).casefold():
                return ()
            raise

    async def authorize(
        self, interaction: discord.Interaction, channel_id: int
    ) -> Configuration | None:
        """Require the event's role on a member from this guild."""
        configuration = await self.module.qs.get(self.module.guild.id, channel_id)
        if (
            configuration is None
            or configuration.state != "active"
            or interaction.guild_id != self.module.guild.id
            or not isinstance(interaction.user, discord.Member)
            or not any(
                role.id == configuration.role_id for role in interaction.user.roles
            )
        ):
            await send_interaction_message(
                interaction, t(interaction, "qs.event.role_required")
            )
            return None
        return configuration

    async def authorize_moderation(
        self, interaction: discord.Interaction, channel_id: int
    ) -> bool:
        """Recheck moderator privileges and active event ownership."""
        configuration = await self.module.qs.get(self.module.guild.id, channel_id)
        if (
            interaction.guild_id == self.module.guild.id
            and can_manage(interaction.user)
            and configuration is not None
            and configuration.state == "active"
        ):
            return True
        await send_interaction_message(
            interaction, t(interaction, "qs.event.withdraw_denied")
        )
        return False

    async def authorize_withdrawal(
        self, interaction: discord.Interaction, channel_id: int, member_id: int
    ) -> Configuration | None:
        """Allow role holders to retract their own report and moderators any report."""
        configuration = await self.module.qs.get(self.module.guild.id, channel_id)
        member = interaction.user
        if (
            configuration is not None
            and configuration.state == "active"
            and interaction.guild_id == self.module.guild.id
            and isinstance(member, discord.Member)
            and (
                can_manage(member)
                or (
                    member.id == member_id
                    and any(role.id == configuration.role_id for role in member.roles)
                )
            )
        ):
            return configuration
        await send_interaction_message(
            interaction, t(interaction, "qs.event.withdraw_denied")
        )
        return None

    async def phase(
        self, interaction: discord.Interaction, channel_id: int, phase_index: int
    ) -> Phase | None:
        """Return a configured phase or tell the member the event is not configured."""
        phase = next(
            (
                phase
                for phase in await self.module.qs.phases(
                    self.module.guild.id, channel_id
                )
                if phase.index == phase_index
            ),
            None,
        )
        if phase is None:
            await send_interaction_message(
                interaction, t(interaction, "qs.event.not_configured")
            )
        return phase
