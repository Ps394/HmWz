from dataclasses import FrozenInstanceError

import pytest

from hmwz.modules.donation.models import DonationType
from hmwz.modules.queue.models import QueueConfiguration


def test_donation_type_is_a_standalone_immutable_value() -> None:
    donation_type = DonationType(
        name="Credits",
        kind="simple",
        unit="credits",
        input_mode="free",
        choices=(),
        time_reductions=(),
    )

    assert donation_type.unit == "credits"
    with pytest.raises(FrozenInstanceError):
        setattr(donation_type, "unit", "crystals")


def test_queue_configuration_is_a_standalone_immutable_value() -> None:
    configuration = QueueConfiguration(
        guild_id=1,
        channel_id=2,
        title="Evening queue",
        description="",
        role_id=9,
        modal_prompt="Confirm",
        message_id=None,
        destruction_message_id=None,
        mode="qs_phases",
        timezone="Europe/Berlin",
        next_start_at=None,
        phase_hours=(),
        remove_role_on_reset=False,
        eruption_start_reminder_enabled=False,
        eruption_start_reminder_minutes=60,
        eruption_end_reminder_enabled=False,
        eruption_end_reminder_minutes=60,
        phase_start_reminder_enabled=False,
        phase_start_reminder_minutes=15,
    )

    assert configuration.mode == "qs_phases"
    with pytest.raises(FrozenInstanceError):
        setattr(configuration, "title", "Changed")
