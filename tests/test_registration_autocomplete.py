from __future__ import annotations

from unittest.mock import AsyncMock
from types import SimpleNamespace
from unittest.mock import Mock
from typing import cast

import discord
import pytest

from hmwz.modules.wz_registration.commands.registration.autocomplete import (
    DISPLAY_NAME_ACCOUNT_VALUE,
    linked_accounts,
    registered_accounts,
    registration_roles,
)
from hmwz.modules.wz_registration.commands.registration.accounts import (
    account_list,
    account_remove,
)
from hmwz.modules.wz_registration.commands.registration.deregister import deregister
from hmwz.modules.wz_registration.commands.registration.register import register


@pytest.fixture
def autocomplete_interaction() -> discord.Interaction:
    member = Mock(spec=discord.Member)
    member.id = 123
    member.display_name = "Player One"
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
            return (
                SimpleNamespace(account="", role=20),
                SimpleNamespace(account="Alt Account", role=10),
            )

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

    assert [choice.value for choice in linked] == [
        DISPLAY_NAME_ACCOUNT_VALUE,
        "Main Account",
        "Alt Account",
    ]
    assert [choice.name for choice in linked] == [
        "Player One",
        "Main Account (Player One)",
        "Alt Account (Player One)",
    ]
    assert [choice.value for choice in registered] == ["Alt Account"]
    assert registered[0].name == "Alt Account (Player One)"
    registered_by_display_name = await registered_accounts(
        autocomplete_interaction, "player"
    )
    assert [choice.value for choice in registered_by_display_name] == [
        DISPLAY_NAME_ACCOUNT_VALUE,
        "Alt Account",
    ]
    linked_by_display_name = await linked_accounts(autocomplete_interaction, "player")
    assert [choice.value for choice in linked_by_display_name] == [
        DISPLAY_NAME_ACCOUNT_VALUE,
        "Main Account",
        "Alt Account",
    ]


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
    assert account_remove._params["account"].autocomplete is not None


@pytest.mark.asyncio
async def test_account_list_embed_includes_display_name_and_linked_accounts() -> None:
    member = Mock(spec=discord.Member)
    member.id = 123
    member.display_name = "Player One"
    member.display_avatar = None
    member.color = discord.Color.blurple()
    guild = Mock(spec=discord.Guild)

    class GameAccounts:
        async def get(
            self, *, guild: discord.Guild, member: int
        ) -> tuple[SimpleNamespace, ...]:
            assert member == 123
            return (
                SimpleNamespace(account="Main Account"),
                SimpleNamespace(account="Alt Account"),
            )

    class ModuleManager:
        async def get_module(
            self, _guild: discord.Guild, _module_type: type
        ) -> SimpleNamespace:
            return SimpleNamespace(game_accounts=GameAccounts())

    interaction = Mock(spec=discord.Interaction)
    interaction.guild = guild
    interaction.user = member
    interaction.client = SimpleNamespace(module_manager=ModuleManager())
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()

    await account_list.callback(interaction)

    embed = interaction.followup.send.await_args.kwargs["embed"]
    assert "Player One" in embed.description
    assert "Discord-Anzeigename" in embed.description
    assert "**1.** Player One" in embed.description
    assert "Main Account" in embed.description
    assert "Alt Account" in embed.description
    assert interaction.followup.send.await_args.kwargs["ephemeral"] is True


@pytest.mark.asyncio
async def test_display_name_registration_uses_button_registration_handler() -> None:
    member = Mock(spec=discord.Member)
    member.id = 123
    member.display_name = "Player One"
    role = Mock(spec=discord.Role)
    role.id = 456
    guild = Mock(spec=discord.Guild)
    guild.get_role.return_value = role
    module = SimpleNamespace(
        roles=SimpleNamespace(get=AsyncMock(return_value=(SimpleNamespace(role=456),))),
        _handle_registration=AsyncMock(),
    )

    class ModuleManager:
        async def get_module(
            self, _guild: discord.Guild, _module_type: type
        ) -> SimpleNamespace:
            return module

    interaction = Mock(spec=discord.Interaction)
    interaction.guild = guild
    interaction.user = member
    interaction.client = SimpleNamespace(module_manager=ModuleManager())
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()

    await register.callback(interaction, DISPLAY_NAME_ACCOUNT_VALUE, "456")

    module._handle_registration.assert_awaited_once_with(
        interaction, role, response_deferred=True
    )
    interaction.response.defer.assert_awaited_once_with(ephemeral=True)
    interaction.followup.send.assert_not_awaited()
