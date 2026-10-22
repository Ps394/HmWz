from hmwz.modules.registrations.commands.wz.setup.configure import configure


def test_configure_command_uses_invocation_channel_and_role_parameters() -> None:
    parameters = {parameter.name: parameter for parameter in configure.parameters}

    assert set(parameters) == {"role", "permanent"}
    assert parameters["role"].required is True
    assert parameters["permanent"].required is False
    assert parameters["permanent"].default is False
