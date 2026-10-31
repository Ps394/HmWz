from __future__ import annotations

import logging
from typing import Literal

import discord

from hmwz.i18n import t
from hmwz.utils.interactions import log_guild
from hmwz.modules.hs.wz.module import WzModule
from hmwz.modules.hs.wz.models import Role

_logger = logging.getLogger(__name__)
RoleAction = Literal["add", "remove"]


class RoleSetupOperations:
    """Apply selected WZ role changes without touching registrations."""

    def __init__(
        self,
        *,
        guild: discord.Guild,
        module: WzModule,
    ) -> None:
        self.guild = guild
        self.module = module

    async def add(
        self, interaction: discord.Interaction, selected_role_ids: list[int]
    ) -> str:
        configured = await self.module.roles.get(guild=self.guild)
        configured_ids = {record.role for record in configured or ()}
        added: list[str] = []
        failed: list[str] = []
        for role_id in selected_role_ids:
            role = self.guild.get_role(role_id)
            if (
                role is None
                or role.id in configured_ids
                or role.is_default()
                or role.managed
                or (self.guild.me is not None and role >= self.guild.me.top_role)
                or len(configured_ids) >= Role.MAX_PER_GUILD
            ):
                failed.append(f"<@&{role_id}>")
                continue
            if await self.module.roles.add(
                guild=self.guild,
                role=role.id,
            ):
                configured_ids.add(role.id)
                added.append(role.mention)
            else:
                failed.append(role.mention)

        return self._result_message(interaction, "add", added, failed)

    async def remove(
        self, interaction: discord.Interaction, selected_role_ids: list[int]
    ) -> str:
        configured = await self.module.roles.get(guild=self.guild)
        configured_ids = {record.role for record in configured or ()}
        selected = sorted(
            {role_id for role_id in selected_role_ids if role_id in configured_ids}
        )
        if not selected:
            return t(interaction, "wz.setup.role.selection_no_changes")

        roles = [
            role
            for role_id in selected
            if (role := self.guild.get_role(role_id)) is not None
        ]
        failed_members: set[int] = set()
        member_fetch_failed = False
        try:
            async for member in self.guild.fetch_members(limit=None):
                held_roles = [role for role in roles if role in member.roles]
                if not held_roles:
                    continue
                try:
                    await member.remove_roles(
                        *held_roles, reason="WZ Setup Role Removal"
                    )
                except discord.HTTPException:
                    failed_members.add(member.id)
                    _logger.exception(
                        "%s Failed to remove WZ roles %s from member %s.",
                        log_guild(self.guild),
                        [role.id for role in held_roles],
                        member.id,
                    )
        except discord.HTTPException:
            member_fetch_failed = True
            _logger.exception(
                "%s Failed to fetch guild members while removing WZ roles.",
                log_guild(self.guild),
            )
        if member_fetch_failed:
            return t(
                interaction,
                "wz.setup.role.member_fetch_failed",
                count=len(failed_members),
            )
        removed_roles = await self.module.roles.remove(guild=self.guild, roles=selected)
        if not removed_roles:
            return t(interaction, "wz.setup.role.error")
        result = self._result_message(
            interaction,
            "remove",
            [role.mention for role in roles],
            [],
        )
        if failed_members:
            result += "\n" + t(
                interaction,
                "wz.setup.role.member_removal_failed",
                count=len(failed_members),
            )
        return result

    @staticmethod
    def _result_message(
        interaction: discord.Interaction,
        action: RoleAction,
        completed: list[str],
        failed: list[str],
    ) -> str:
        messages = []
        if completed:
            messages.append(
                t(
                    interaction,
                    f"wz.setup.role.{action}.success",
                    role_names=", ".join(completed),
                )
            )
        if failed:
            messages.append(
                t(
                    interaction,
                    "wz.setup.role.operation_failed",
                    role_names=", ".join(failed),
                )
            )
        return "\n".join(messages) or t(
            interaction, "wz.setup.role.selection_no_changes"
        )
