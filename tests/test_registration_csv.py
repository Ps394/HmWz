import csv
import io

from hmwz.modules.registration.commands.csv import _serialize_csv


def test_registration_csv_escapes_quotes_and_newlines() -> None:
    content = _serialize_csv(
        (
            ("NR", "Account", "Comment"),
            (1, 'player; "one"', "first line\nsecond line"),
        )
    )

    rows = list(csv.reader(io.StringIO(content, newline=""), delimiter=";"))

    assert rows == [
        ["NR", "Account", "Comment"],
        ["1", 'player; "one"', "first line\nsecond line"],
    ]
    assert content.endswith("\n")
