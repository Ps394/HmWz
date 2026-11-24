"""Validation and persistence for registration setup drafts."""

from __future__ import annotations

import logging

import discord

from hmwz.configuration import registration_defaults
from hmwz.i18n import t
from hmwz.ui.messages import send_followup
from hmwz.utils.loaders import fetch_member

from .draft import RegistrationSetupDraft

_logger = logging.getLogger(__name__)


async def save_registration_draft(
    draft: RegistrationSetupDraft,
    interaction: discord.Interaction,
) -> str | None:
    """Validate and persist one registration setup draft."""
    module = draft.module
    guild = module.guild
    min_roles = int(
        registration_defaults(module.module_key).get("min_registration_roles", 1)
    )
    max_roles = int(
        registration_defaults(module.module_key).get("max_registration_roles", 4)
    )
    if not min_roles <= len(draft.roles) <= max_roles:
        await send_followup(
            interaction,
            t(
                interaction,
                "registration.setup.config.role_count_invalid",
                minimum=min_roles,
                maximum=max_roles,
            ),
            ephemeral=True,
        )
        return None

    current_roles = await module.roles.get(guild=guild, channel_id=draft.channel_id)
    current_role_map = {role.role: role.permanent for role in current_roles or ()}
    if current_role_map != draft.original_roles:
        await _send_stale(interaction)
        return None

    current_settings = await module.registration.get(
        guild=guild,
        channel_id=draft.channel_id,
    )
    current_title = (
        current_settings.title if current_settings and current_settings.title else ""
    )
    current_description = (
        current_settings.description
        if current_settings and current_settings.description
        else ""
    )
    current_show_lock_emojis = (
        current_settings.show_lock_emojis if current_settings else True
    )
    if (
        current_title != draft.original_title
        or current_description != draft.original_description
        or current_show_lock_emojis != draft.original_show_lock_emojis
    ):
        await _send_stale(interaction)
        return None

    current_export_channel_id = await module.registration_event_channel.get(guild=guild)
    if current_export_channel_id != draft.original_export_channel_id:
        await _send_stale(interaction)
        return None

    if not await _validate_roles(draft, guild, interaction):
        return None
    if not await _validate_export_channel(draft, guild, interaction):
        return None

    if not await module.registration.upsert(
        guild=guild,
        channel_id=draft.channel_id,
        title=draft.title,
        description=draft.description,
        show_lock_emojis=draft.show_lock_emojis,
    ):
        await send_followup(
            interaction,
            t(interaction, "registration.setup.config.save_error"),
            ephemeral=True,
        )
        return None

    if not await _apply_role_changes(draft, guild, interaction):
        return None
    failed_members = await _apply_removed_roles(draft, guild, interaction)
    if not await _apply_export_channel(draft, guild, interaction):
        return None

    await module.queue_registration_refresh(draft.channel_id)
    if failed_members:
        return t(
            interaction,
            "registration.setup.config.remove_role_member_warning",
            count=len(failed_members),
        )
    return t(interaction, "registration.setup.config.saved")


async def _send_stale(interaction: discord.Interaction) -> None:
    await send_followup(
        interaction,
        t(interaction, "registration.setup.config.stale"),
        ephemeral=True,
    )


async def _validate_roles(
    draft: RegistrationSetupDraft,
    guild: discord.Guild,
    interaction: discord.Interaction,
) -> bool:
    for role_id in draft.roles:
        role = guild.get_role(role_id)
        if (
            role is None
            or role.is_default()
            or role.managed
            or (guild.me is not None and role >= guild.me.top_role)
        ):
            await send_followup(
                interaction,
                t(interaction, "registration.setup.config.role_hierarchy_error"),
                ephemeral=True,
            )
            return False
    return True


async def _validate_export_channel(
    draft: RegistrationSetupDraft,
    guild: discord.Guild,
    interaction: discord.Interaction,
) -> bool:
    if draft.export_channel_id is None:
        return True
    channel = guild.get_channel(draft.export_channel_id)
    if not isinstance(channel, discord.TextChannel):
        await send_followup(
            interaction,
            t(interaction, "registration.setup.config.export_channel_invalid"),
            ephemeral=True,
        )
        return False
    bot_member = guild.me
    if bot_member is None:
        await send_followup(
            interaction,
            t(interaction, "registration.setup.config.export_channel_error"),
            ephemeral=True,
        )
        return False
    permissions = channel.permissions_for(bot_member)
    if not permissions.send_messages or not permissions.attach_files:
        await send_followup(
            interaction,
            t(
                interaction,
                "registration.setup.config.export_channel_missing_permissions",
            ),
            ephemeral=True,
        )
        return False
    return True


async def _apply_role_changes(
    draft: RegistrationSetupDraft,
    guild: discord.Guild,
    interaction: discord.Interaction,
) -> bool:
    module = draft.module
    for role_id, permanent in draft.roles.items():
        if draft.original_roles.get(role_id) == permanent:
            continue
        if not await module.roles.add(
            guild=guild,
            role=role_id,
            permanent=permanent,
            score=1,
            channel_id=draft.channel_id,
        ):
            await send_followup(
                interaction,
                t(interaction, "registration.setup.config.partial_save_error"),
                ephemeral=True,
            )
            return False
    return True


async def _apply_removed_roles(
    draft: RegistrationSetupDraft,
    guild: discord.Guild,
    interaction: discord.Interaction,
) -> set[int]:
    module = draft.module
    removed_role_ids = sorted(draft.original_roles.keys() - draft.roles.keys())
    failed_members: set[int] = set()
    if not removed_role_ids:
        return failed_members

    registrations = await module.registrations.get(
        guild=guild,
        roles=removed_role_ids,
        channel_id=draft.channel_id,
    )
    if not await module.roles.remove(
        guild=guild,
        roles=removed_role_ids,
        channel_id=draft.channel_id,
    ) or not await module.registrations.remove(
        guild=guild,
        roles=removed_role_ids,
        channel_id=draft.channel_id,
    ):
        await send_followup(
            interaction,
            t(interaction, "registration.setup.config.partial_save_error"),
            ephemeral=True,
        )
        return failed_members

    for member_id in {
        record.member for record in registrations or () if record.member is not None
    }:
        member = await fetch_member(guild, member_id)
        if member is None:
            continue
        roles_to_remove = [
            role
            for role_id in removed_role_ids
            if (role := guild.get_role(role_id)) is not None and role in member.roles
        ]
        if not roles_to_remove:
            continue
        try:
            await member.remove_roles(
                *roles_to_remove,
                reason="Registration setup role removal",
            )
        except discord.HTTPException:
            failed_members.add(member.id)
            _logger.exception(
                "Failed to remove registration roles %s from member %s in guild %s.",
                removed_role_ids,
                member.id,
                guild.id,
            )
    return failed_members


async def _apply_export_channel(
    draft: RegistrationSetupDraft,
    guild: discord.Guild,
    interaction: discord.Interaction,
) -> bool:
    del guild
    module = draft.module
    if draft.export_channel_id == draft.original_export_channel_id:
        return True
    if draft.export_channel_id is None:
        changed = await module.registration_event_channel.remove(guild=module.guild)
    else:
        changed = await module.registration_event_channel.set(
            guild=module.guild,
            channel_id=draft.export_channel_id,
        )
    if not changed:
        await send_followup(
            interaction,
            t(interaction, "registration.setup.config.partial_save_error"),
            ephemeral=True,
        )
        return False
    return True
