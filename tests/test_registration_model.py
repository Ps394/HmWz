from types import SimpleNamespace
from typing import cast

import discord

from hmwz.modules.wz_registration.models.registration import Registration
from hmwz.modules.wz_registration.models.registration_member import (
    RegistrationMember,
)
from hmwz.modules.wz_registration.models.registration_role import RegistrationRole


def test_registration_counts_and_score_follow_role_properties() -> None:
    guild = cast(discord.Guild, SimpleNamespace(id=123, name="test guild"))
    permanent = RegistrationMember(
        member_id=10,
        role=RegistrationRole(role_id=1, score=5, permanent=True),
        timestamp="2026-01-01T00:00:00",
    )
    temporary = RegistrationMember(
        member_id=20,
        role=RegistrationRole(role_id=2, score=3),
        timestamp="2026-01-01T00:00:00",
    )
    registration = Registration(guild=guild)

    registration.add_registration(permanent)
    registration.add_registration(temporary)

    assert registration.count_total_registrations == 2
    assert registration.permanent_registrations == (permanent,)
    assert registration.temporary_registrations == (temporary,)
    assert registration.count_permanent_registrations == 1
    assert registration.count_temporary_registrations == 1
    assert registration.total_score == 8


def test_change_registration_replaces_the_old_registration() -> None:
    guild = cast(discord.Guild, SimpleNamespace(id=123, name="test guild"))
    old = RegistrationMember(
        member_id=10,
        role=RegistrationRole(role_id=1),
        timestamp="2026-01-01T00:00:00",
    )
    new = RegistrationMember(
        member_id=10,
        role=RegistrationRole(role_id=2, score=4),
        timestamp="2026-01-02T00:00:00",
    )
    registration = Registration(guild=guild, registrations=[old])

    registration.change_registration(old, new)

    assert registration.registrations == [new]
    assert registration.total_score == 4
