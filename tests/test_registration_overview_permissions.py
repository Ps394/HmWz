from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import discord

from hmwz.modules.registration.overview import RegistrationHandler, RegistrationOverview
from hmwz.modules.overview import OverviewModule
from hmwz.modules.registration.repositories import (
    MemberRegistrationRepository,
    RegistrationRoleRepository,
    RegistrationSettingsRepository,
)


def test_overview_reports_missing_channel_permissions() -> None:
    bot_member = object()
    guild = cast(
        discord.Guild,
        SimpleNamespace(me=bot_member),
    )
    channel = cast(
        discord.TextChannel,
        SimpleNamespace(
            permissions_for=lambda member: discord.Permissions(
                view_channel=True,
                send_messages=True,
                embed_links=False,
            )
        ),
    )
    overview = RegistrationOverview(
        guild=guild,
        client=cast(discord.Client, SimpleNamespace()),
        registration=cast(RegistrationSettingsRepository, SimpleNamespace()),
        roles=cast(RegistrationRoleRepository, SimpleNamespace()),
        registrations=cast(MemberRegistrationRepository, SimpleNamespace()),
        registration_handler=cast(RegistrationHandler, lambda *_args: None),
        overview_module=cast(OverviewModule, SimpleNamespace()),
        channel_id=123,
    )

    assert overview._missing_send_permissions(channel) == ("embed_links",)
