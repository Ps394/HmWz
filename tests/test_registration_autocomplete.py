from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock
from typing import cast

import discord
import pytest

from hmwz.modules.wz_registration.commands.registration.autocomplete import (
    linked_accounts,
    registered_accounts,
    registration_roles,
)
from hmwz.modules.wz_registration.commands.registration.deregister import deregister
from hmwz.modules.wz_registration.commands.registration.register import register


@pytest.fixture
def autocomplete_interaction() -> discord.Interaction:
    member = Mock(spec=discord.Member)
    member.id = 123
    roles = {
        10: SimpleNamespace(id=10, name="Raid"),
        20: SimpleNamespace(id=20, name="Casual"),
    }
    server_guild = Mock(spec=discord.Guild)
    server_guild.get_role.side_effect = roles.get

    class ModuleManager:
        async def get_module(
            self, _guild: discord.Guild, _module_type: type
        ) -> SimpleNamespace:
            return module

    class Accounts:
        async def get(
            self,
            *,
            guild: discord.Guild,
            member: int,
        ) -> tuple[SimpleNamespace, ...]:
            assert guild is server_guild
            assert member == 123
            return (
                SimpleNamespace(account="Main Account"),
                SimpleNamespace(account="Alt Account"),
            )

    class Registrations:
        async def get(
            self,
            *,
            guild: discord.Guild,
            member: int,
        ) -> tuple[SimpleNamespace, ...]:
            assert guild is server_guild
            assert member == 123
            return (SimpleNamespace(account="Alt Account", role=10),)

    class Roles:
        async def get(self, *, guild: discord.Guild) -> tuple[SimpleNamespace, ...]:
            assert guild is server_guild
            return (
                SimpleNamespace(role=10),
                SimpleNamespace(role=20),
                SimpleNamespace(role=30),
            )

    module = SimpleNamespace(
        game_accounts=Accounts(),
        registrations=Registrations(),
        roles=Roles(),
    )
    interaction = Mock(spec=discord.Interaction)
    interaction.guild = server_guild
    interaction.user = member
    interaction.client = SimpleNamespace(module_manager=ModuleManager())
    return cast(discord.Interaction, interaction)


@pytest.mark.asyncio
async def test_account_autocomplete_is_scoped_to_registration_state(
    autocomplete_interaction: discord.Interaction,
) -> None:
    linked = await linked_accounts(autocomplete_interaction, "")
    registered = await registered_accounts(autocomplete_interaction, "alt")

    assert [choice.value for choice in linked] == ["Main Account", "Alt Account"]
    assert [choice.value for choice in registered] == ["Alt Account"]


@pytest.mark.asyncio
async def test_registration_role_autocomplete_only_offers_configured_roles(
    autocomplete_interaction: discord.Interaction,
) -> None:
    choices = await registration_roles(autocomplete_interaction, "rai")

    assert [(choice.name, choice.value) for choice in choices] == [("Raid", "10")]


def test_register_and_deregister_expose_autocomplete_options() -> None:
    assert register._params["account"].autocomplete is not None
    assert register._params["role"].autocomplete is not None
    assert register._params["role"].type.name == "string"
    assert deregister._params["account"].autocomplete is not None
    assert set(deregister._params) == {"account"}
