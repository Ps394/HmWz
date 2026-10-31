"""Validate credit amounts and configurable fixed choices."""

import re
from decimal import Decimal, InvalidOperation


def parse_choices(raw: str) -> tuple[str, ...]:
    """Split semicolon-separated values and reject duplicates or empty entries."""
    choices = tuple(value.strip() for value in raw.split(";"))
    if (
        not choices
        or len(choices) > 25
        or len(set(choices)) != len(choices)
        or any(not choice for choice in choices)
        or any(len(choice) > 100 for choice in choices)
    ):
        raise ValueError("Enter between 1 and 25 unique, semicolon-separated values.")
    return choices


def parse_amount(raw: str) -> Decimal:
    """Parse a positive amount with optional grouped thousands separators."""
    value = raw.strip()
    if re.fullmatch(r"\d{1,3}(?:([.,])\d{2,3})+", value):
        separators = re.findall(r"[.,]", value)
        groups = re.split(r"[.,]", value)
        if len(set(separators)) == 1 and all(
            2 <= len(group) <= 3 for group in groups[1:]
        ):
            value = "".join(groups)
    try:
        amount = Decimal(value)
    except InvalidOperation as error:
        raise ValueError("Donation amount must be numeric.") from error
    if not amount.is_finite() or amount <= 0 or amount.adjusted() > 50:
        raise ValueError("Donation amount must be greater than zero.")
    return amount


def parse_donation_choices(raw: str) -> tuple[str, ...]:
    """Normalize optional fixed amounts, rejecting numerically equal choices."""
    if not raw.strip():
        return ()
    raw_choices = parse_choices(raw)
    choices = tuple(format(parse_amount(choice), "f") for choice in raw_choices)
    if len(set(choices)) != len(choices):
        raise ValueError("Donation amount choices must be unique.")
    return choices
