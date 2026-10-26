from types import SimpleNamespace
from typing import cast

import pytest

from hmwz.modules.donation.models import DonationType
from hmwz.modules.donation.views import (
    MAX_DONATION_BUTTONS,
    DonationAmountChoiceView,
    DonationOverviewView,
    DonationRecordButton,
)


def donation_type(choice_count: int) -> DonationType:
    return DonationType(
        name="credits",
        kind="simple",
        unit="credits",
        input_mode="choice",
        choices=tuple(str(100 + index) for index in range(choice_count)),
        time_reductions=(),
    )


@pytest.mark.parametrize(
    "choice_count", [MAX_DONATION_BUTTONS, MAX_DONATION_BUTTONS + 1]
)
@pytest.mark.asyncio
async def test_amount_choice_view_respects_component_limit(
    choice_count: int, monkeypatch
) -> None:
    monkeypatch.setattr(
        "hmwz.modules.donation.views.t", lambda *_args, **_kwargs: "Record donation"
    )
    module = SimpleNamespace(guild=SimpleNamespace())

    view = DonationAmountChoiceView(
        cast(object, module), 456, donation_type(choice_count)
    )

    assert len(view.children) <= MAX_DONATION_BUTTONS
    if choice_count > MAX_DONATION_BUTTONS:
        assert len(view.children) == 1
        assert isinstance(view.children[0], DonationRecordButton)
    else:
        assert len(view.children) == MAX_DONATION_BUTTONS


@pytest.mark.asyncio
async def test_overview_falls_back_to_modal_entry_for_oversized_choice_set(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "hmwz.modules.donation.views.t", lambda *_args, **_kwargs: "Record donation"
    )
    module = SimpleNamespace(guild=SimpleNamespace())

    view = DonationOverviewView(
        cast(object, module),
        456,
        donation_type(MAX_DONATION_BUTTONS + 1),
    )

    assert len(view.children) == 1
    assert isinstance(view.children[0], DonationRecordButton)
