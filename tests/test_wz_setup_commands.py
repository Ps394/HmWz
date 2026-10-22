import discord

from hmwz.modules.hs.wz.commands import WzGroup
from hmwz.modules.hs.wz.commands.clean_channels import clean_channels
from hmwz.modules.hs.wz.commands.reset_roles import reset_roles


def test_wz_setup_commands_are_valid_single_level_subcommands() -> None:
    wz = WzGroup(None)
    setup = next(command for command in wz.commands if command.name == "setup")
    assert isinstance(setup, discord.app_commands.Group)
    assert {command.name for command in setup.commands} == {
        "channel-add",
        "channel-remove",
        "role-add",
        "role-remove",
    }

    client = discord.Client(intents=discord.Intents.none())
    tree = discord.app_commands.CommandTree(client)
    tree.add_command(wz)
    payload = wz.to_dict(tree)
    setup_payload = next(
        option for option in payload["options"] if option["name"] == "setup"
    )

    assert setup_payload["type"] == 2
    assert {option["type"] for option in setup_payload["options"]} == {1}


def test_wz_maintenance_commands_and_defaults() -> None:
    wz = WzGroup(None)
    command_names = {command.name for command in wz.commands}
    parameters = {parameter.name: parameter for parameter in clean_channels.parameters}

    assert "clean-channels" in command_names
    assert "reset-roles" in command_names
    assert parameters["ignore_pinned"].default is True
    assert reset_roles.name == "reset-roles"
