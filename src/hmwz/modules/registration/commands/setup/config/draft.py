"""Mutable registration settings collected before setup is saved."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hmwz.modules.registration.module import RegistrationModule


@dataclass(slots=True)
class RegistrationSetupDraft:
    """Keep registration changes in memory until the moderator saves them."""

    module: RegistrationModule
    channel_id: int
    owner_id: int
    title: str
    original_title: str
    description: str
    original_description: str
    show_lock_emojis: bool
    original_show_lock_emojis: bool
    roles: dict[int, bool]
    original_roles: dict[int, bool]
    export_channel_id: int | None
    original_export_channel_id: int | None

    @classmethod
    async def load(
        cls, module: RegistrationModule, channel_id: int, owner_id: int
    ) -> RegistrationSetupDraft:
        settings = await module.registration.get(
            guild=module.guild, channel_id=channel_id
        )
        roles = await module.roles.get(guild=module.guild, channel_id=channel_id)
        export_channel_id = await module.registration_event_channel.get(
            guild=module.guild
        )
        title = settings.title if settings and settings.title else ""
        description = settings.description if settings and settings.description else ""
        show_lock_emojis = settings.show_lock_emojis if settings else True
        configured_roles = {role.role: role.permanent for role in roles or ()}
        return cls(
            module=module,
            channel_id=channel_id,
            owner_id=owner_id,
            title=title,
            original_title=title,
            description=description,
            original_description=description,
            show_lock_emojis=show_lock_emojis,
            original_show_lock_emojis=show_lock_emojis,
            roles=configured_roles.copy(),
            original_roles=configured_roles.copy(),
            export_channel_id=export_channel_id,
            original_export_channel_id=export_channel_id,
        )
