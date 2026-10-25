from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock

import discord
import pytest

import hmwz.modules.registration.commands.setup.remove as remove_command
from hmwz.modules.registration.commands.setup.remove import (
    RegistrationRemoveConfirmation,
    remove,
)


@pytest.mark.asyncio
async def test_remove_command_requires_confirmation() -> None:
    guild = cast(discord.Guild, SimpleNamespace(id=10))
    registration = SimpleNamespace(get=AsyncMock(return_value=object()))
    module = SimpleNamespace(registration=registration)
    manager = SimpleNamespace(get_module=AsyncMock(return_value=module))
    confirmation_message = SimpleNamespace(delete=AsyncMock())
    response = SimpleNamespace(send_message=AsyncMock())
    interaction = cast(
        discord.Interaction,
        SimpleNamespace(
            guild=guild,
            channel_id=20,
            user=SimpleNamespace(id=30),
            client=SimpleNamespace(module_manager=manager),
            locale=discord.Locale.german,
            response=response,
            original_response=AsyncMock(return_value=confirmation_message),
        ),
    )

    await remove.callback(interaction)

    response.send_message.assert_awaited_once()
    arguments = response.send_message.await_args
    assert arguments.kwargs["ephemeral"] is True
    assert isinstance(arguments.kwargs["view"], RegistrationRemoveConfirmation)
    assert arguments.kwargs["view"].message is confirmation_message
    assert "Teilnahmen" in arguments.args[0]
    registration.get.assert_awaited_once_with(guild=guild, channel_id=20)


@pytest.mark.asyncio
@pytest.mark.parametrize("shared_elsewhere", [True, False])
async def test_confirm_removes_channel_data_messages_and_only_unshared_roles(
    monkeypatch: pytest.MonkeyPatch,
    shared_elsewhere: bool,
) -> None:
    removal_operations: list[str] = []
    guild = cast(
        discord.Guild,
        SimpleNamespace(
            id=10,
            get_role=Mock(return_value=SimpleNamespace(id=99)),
        ),
    )
    registration_record = SimpleNamespace(message=501)
    channel_registration = SimpleNamespace(member=30, role=99, channel_id=20)
    other_registration = SimpleNamespace(member=30, role=99, channel_id=21)
    registrations = SimpleNamespace(
        get=AsyncMock(
            side_effect=[
                (channel_registration,),
                (
                    (channel_registration, other_registration)
                    if shared_elsewhere
                    else (channel_registration,)
                ),
            ]
        ),
        remove=AsyncMock(
            side_effect=lambda **_: removal_operations.append("registrations") or True
        ),
    )
    messages = (
        SimpleNamespace(message=502),
        SimpleNamespace(message=503),
    )
    list_repository = SimpleNamespace(
        get=AsyncMock(return_value=messages),
        remove=AsyncMock(
            side_effect=lambda **_: removal_operations.append("list") or True
        ),
    )
    role_repository = SimpleNamespace(
        remove=AsyncMock(
            side_effect=lambda **_: removal_operations.append("roles") or True
        )
    )
    purge_channels = SimpleNamespace(
        remove=AsyncMock(
            side_effect=lambda **_: removal_operations.append("purge") or True
        )
    )
    settings = SimpleNamespace(
        get=AsyncMock(return_value=registration_record),
        remove=AsyncMock(
            side_effect=lambda **_: removal_operations.append("settings") or True
        ),
    )
    overview = SimpleNamespace(forget_message=Mock())
    module = SimpleNamespace(
        registration=settings,
        registrations=registrations,
        list=list_repository,
        roles=role_repository,
        purge_channels=purge_channels,
        _overview_for=Mock(return_value=overview),
    )
    manager = SimpleNamespace(get_module=AsyncMock(return_value=module))
    response = SimpleNamespace(defer=AsyncMock())
    confirmation_message = SimpleNamespace(delete=AsyncMock())
    interaction = cast(
        discord.Interaction,
        SimpleNamespace(
            guild=guild,
            user=SimpleNamespace(id=30),
            client=SimpleNamespace(
                module_manager=manager,
                user=SimpleNamespace(id=999),
            ),
            locale=discord.Locale.german,
            response=response,
            edit_original_response=AsyncMock(return_value=confirmation_message),
        ),
    )
    deleted_ids: list[int] = []

    class FakeChannel:
        async def fetch_message(self, message_id: int) -> discord.Message:
            return cast(
                discord.Message,
                SimpleNamespace(
                    id=message_id,
                    delete=AsyncMock(
                        side_effect=lambda: (
                            removal_operations.append("message"),
                            deleted_ids.append(message_id),
                        )
                    ),
                ),
            )

        async def history(self, limit: None) -> AsyncIterator[discord.Message]:
            for message_id, author_id in (
                (501, 999),
                (502, 999),
                (503, 999),
                (504, 999),
                (505, 888),
                (506, 30),
            ):
                yield cast(
                    discord.Message,
                    SimpleNamespace(
                        id=message_id,
                        author=SimpleNamespace(id=author_id),
                        delete=AsyncMock(
                            side_effect=lambda message_id=message_id: (
                                removal_operations.append("message"),
                                deleted_ids.append(message_id),
                            )
                        ),
                    ),
                )

    async def fetch_channel(_guild: discord.Guild, _channel_id: int) -> FakeChannel:
        return FakeChannel()

    monkeypatch.setattr(remove_command.utils, "fetch_channel", fetch_channel)
    remove_member_roles = AsyncMock(return_value=False)
    monkeypatch.setattr(
        RegistrationRemoveConfirmation,
        "_remove_member_roles",
        remove_member_roles,
    )
    view = RegistrationRemoveConfirmation(
        owner_id=30,
        guild=guild,
        channel_id=20,
        context=interaction,
    )

    await view.confirm.callback(interaction)

    remove_member_roles.assert_awaited_once_with(
        set() if shared_elsewhere else {(30, 99)}
    )
    assert set(deleted_ids) == {501, 502, 503, 504}
    first_message_removal = removal_operations.index("message")
    assert all(
        removal_operations.index(operation) < first_message_removal
        for operation in ("registrations", "roles", "list", "purge", "settings")
    )
    assert {call.args[0] for call in overview.forget_message.call_args_list} == {
        501,
        502,
        503,
    }
    registrations.remove.assert_awaited_once_with(guild=guild, channel_id=20)
    role_repository.remove.assert_awaited_once_with(guild=guild, channel_id=20)
    list_repository.remove.assert_awaited_once_with(guild=guild, channel=20)
    purge_channels.remove.assert_awaited_once_with(
        guild=guild, registration_channel_id=20
    )
    settings.remove.assert_awaited_once_with(guild=guild, channel_id=20)
    interaction.edit_original_response.assert_awaited_once()
    assert interaction.edit_original_response.await_args.kwargs["view"] is None
    confirmation_message.delete.assert_awaited_once_with(delay=5)


@pytest.mark.asyncio
async def test_cancel_closes_and_deletes_confirmation_dialog() -> None:
    guild = cast(discord.Guild, SimpleNamespace(id=10))
    interaction = cast(
        discord.Interaction,
        SimpleNamespace(
            user=SimpleNamespace(id=30),
            locale=discord.Locale.german,
            response=SimpleNamespace(edit_message=AsyncMock()),
        ),
    )
    view = RegistrationRemoveConfirmation(
        owner_id=30,
        guild=guild,
        channel_id=20,
        context=interaction,
    )
    cancel_button = next(
        item
        for item in view.children
        if item.custom_id == "wz_registration_remove_cancel"
    )

    await cancel_button.callback(interaction)

    interaction.response.edit_message.assert_awaited_once()
    arguments = interaction.response.edit_message.await_args
    assert arguments.kwargs["view"] is None
    assert arguments.kwargs["delete_after"] == 5
