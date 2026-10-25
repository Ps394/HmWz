from __future__ import annotations

import logging
from typing import Literal

import discord

from hmwz.configuration import wz_registration_config
from hmwz.i18n import t
from hmwz.modules.hs.wz.module import WzRegistrationModule

logger = logging.getLogger(__name__)
RoleAction = Literal["add", "remove"]


class RoleSetupOperations:
    """Apply selected WZ registration role changes."""

    def __init__(
        self,
        *,
        guild: discord.Guild,
        module: WzRegistrationModule,
        channel_id: int,
        permanent: bool,
    ) -> None:
        self.guild = guild
        self.module = module
        self.channel_id = channel_id
        self.permanent = permanent

    async def add(
        self, interaction: discord.Interaction, selected_role_ids: list[int]
    ) -> str:
        configured = await self.module.roles.get(
            guild=self.guild, channel_id=self.channel_id
        )
        configured_ids = {record.role for record in configured or ()}
        configured_anywhere = await self.module.roles.get(guild=self.guild)
        configured_global_ids = {record.role for record in configured_anywhere or ()}
        max_roles = int(wz_registration_config().get("max_registration_roles", 4))
        added: list[str] = []
        failed: list[str] = []
        for role_id in selected_role_ids:
            role = self.guild.get_role(role_id)
            if (
                role is None
                or role.id in configured_global_ids
                or role.is_default()
                or role.managed
                or (self.guild.me is not None and role >= self.guild.me.top_role)
                or len(configured_ids) >= max_roles
            ):
                failed.append(f"<@&{role_id}>")
                continue
            if await self.module.roles.add(
                guild=self.guild,
                role=role.id,
                permanent=self.permanent,
                score=1,
                channel_id=self.channel_id,
            ):
                configured_ids.add(role.id)
                added.append(role.mention)
            else:
                failed.append(role.mention)

        if added and not await self.module.compose_registration_overview(
            force=True, channel_id=self.channel_id
        ):
            return t(
                interaction,
                "wz.setup.role.add.overview_failed",
                role_names=", ".join(added),
            )
        return self._result_message(interaction, "add", added, failed)

    async def remove(
        self, interaction: discord.Interaction, selected_role_ids: list[int]
    ) -> str:
        configured = await self.module.roles.get(
            guild=self.guild, channel_id=self.channel_id
        )
        configured_ids = {record.role for record in configured or ()}
        min_roles = int(wz_registration_config().get("min_registration_roles", 1))
        selected = [
            role_id for role_id in selected_role_ids if role_id in configured_ids
        ]
        if len(configured_ids) - len(selected) < min_roles:
            return t(interaction, "wz.setup.role.min_roles")
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
                    logger.exception(
                        "Failed to remove WZ roles %s from member %s in guild %s.",
                        [role.id for role in held_roles],
                        member.id,
                        self.guild.id,
                    )
        except discord.HTTPException:
            member_fetch_failed = True
            logger.exception(
                "Failed to fetch guild members while removing WZ roles in guild %s.",
                self.guild.id,
            )
        if member_fetch_failed:
            return t(
                interaction,
                "wz.setup.role.member_fetch_failed",
                count=len(failed_members),
            )
        removed_roles = await self.module.roles.remove(
            guild=self.guild, roles=selected, channel_id=self.channel_id
        )
        removed_registrations = await self.module.registrations.remove(
            guild=self.guild, roles=selected, channel_id=self.channel_id
        )
        if not removed_roles or not removed_registrations:
            return t(interaction, "wz.setup.role.error")
        if not await self.module.compose_registration_overview(
            force=True, channel_id=self.channel_id
        ):
            return t(
                interaction,
                "wz.setup.role.remove.overview_failed",
                role_names=", ".join(f"<@&{role_id}>" for role_id in selected),
            )
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
