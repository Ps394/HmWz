from __future__ import annotations

import logging
import runpy
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Callable, cast

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "hmwz"
    / "modules"
    / "registration"
    / "db-merge.py"
)
merge_database = cast(
    Callable[..., Path | None], runpy.run_path(str(SCRIPT))["merge_database"]
)


@pytest.fixture
def legacy_database(tmp_path: Path) -> Path:
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE WzRegistration (
                Guild INTEGER PRIMARY KEY, Channel INTEGER, Message INTEGER,
                Title TEXT, Description TEXT, GuildName TEXT, ChannelName TEXT,
                FOREIGN KEY (Guild) REFERENCES Servers(Guild)
            ) WITHOUT ROWID;
            CREATE TABLE WzRoles (
                Guild INTEGER, Role INTEGER, Permanent BOOLEAN, Score INTEGER DEFAULT 1,
                GuildName TEXT, RoleName TEXT, PRIMARY KEY (Guild, Role)
            ) WITHOUT ROWID;
            CREATE TABLE WzRegistrations (
                Guild INTEGER, Member INTEGER, Account TEXT NOT NULL DEFAULT '',
                Role INTEGER, Timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                GuildName TEXT, MemberUsername TEXT, MemberDisplayName TEXT,
                RoleName TEXT, PRIMARY KEY (Guild, Member, Account)
            ) WITHOUT ROWID;
            CREATE TABLE WzList (
                Guild INTEGER, Channel INTEGER, Message INTEGER, Title TEXT, Text TEXT,
                PRIMARY KEY (Guild, Message),
                FOREIGN KEY (Guild) REFERENCES Servers(Guild)
            ) WITHOUT ROWID;
            INSERT INTO WzRegistration VALUES
                (1, 10, 100, 'Title', 'Description', 'Guild', 'Channel');
            INSERT INTO WzRoles VALUES (1, 20, 1, 3, 'Guild', 'Role');
            INSERT INTO WzRegistrations VALUES
                (1, 30, '', 20, '2026-10-30 20:00:00', 'Guild', 'user', 'User', 'Role'),
                (1, 30, 'Alt', 20, '2026-10-30 20:01:00', 'Guild', 'user', 'User', 'Role');
            INSERT INTO WzList VALUES
                (1, 11, 102, 'Page 2', 'Second'),
                (1, 11, 101, 'Page 1', 'First');
            CREATE TABLE Unrelated (Value TEXT);
            INSERT INTO Unrelated VALUES ('keep');
            """
        )
    return path


def test_merge_preserves_data_and_adopts_overview_messages(
    legacy_database: Path,
) -> None:
    backup = merge_database(legacy_database)
    assert backup is not None and backup.is_file()
    with sqlite3.connect(backup) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM WzRegistrations"
        ).fetchone() == (2,)
        assert not connection.execute(
            "SELECT 1 FROM sqlite_master WHERE name = 'Registration_Members'"
        ).fetchall()
    with sqlite3.connect(legacy_database) as connection:
        assert connection.execute("SELECT * FROM Servers").fetchall() == [(1, "Guild")]
        assert connection.execute("SELECT * FROM Registration_Roles").fetchall() == [
            (1, 10, 20, 1, 3)
        ]
        assert connection.execute(
            "SELECT Channel, Alias, Timestamp, MemberUsername, MemberDisplayName, RoleName "
            "FROM Registration_Members ORDER BY Alias"
        ).fetchall() == [
            (10, "", "2026-10-30 20:00:00", "user", "User", "Role"),
            (10, "Alt", "2026-10-30 20:01:00", "user", "User", "Role"),
        ]
        assert connection.execute(
            "SELECT OverviewId, Channel, Message, Title, Description, Buttons "
            "FROM Module_Overviews ORDER BY OverviewId"
        ).fetchall() == [
            ("registration-10", 10, 100, "Title", "Description", "[]"),
            ("registration-10-list-1", 11, 101, "Page 1", "First", "[]"),
            ("registration-10-list-2", 11, 102, "Page 2", "Second", "[]"),
        ]
        assert connection.execute("SELECT * FROM Unrelated").fetchall() == [("keep",)]
        assert connection.execute(
            "SELECT COUNT(*) FROM WzRegistrations"
        ).fetchone() == (2,)
        assert not connection.execute("PRAGMA foreign_key_check").fetchall()


def test_repeated_merge_keeps_current_values_and_fills_missing_fields(
    legacy_database: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    merge_database(legacy_database)
    with sqlite3.connect(legacy_database) as connection:
        connection.execute(
            "UPDATE Registration_Settings SET Title = 'New', Description = NULL"
        )
        connection.execute("UPDATE Registration_Members SET RoleName = NULL")
        connection.execute("UPDATE Module_Overviews SET Message = 999")
    with caplog.at_level(logging.WARNING):
        merge_database(legacy_database)
    assert "conflict" in caplog.text
    with sqlite3.connect(legacy_database) as connection:
        assert connection.execute(
            "SELECT Title, Description FROM Registration_Settings"
        ).fetchall() == [("New", "Description")]
        assert connection.execute(
            "SELECT RoleName FROM Registration_Members"
        ).fetchall() == [("Role",), ("Role",)]
        assert connection.execute(
            "SELECT Message FROM Module_Overviews"
        ).fetchall() == [(999,), (999,), (999,)]
        assert connection.execute(
            "SELECT COUNT(*) FROM Registration_Members"
        ).fetchone() == (2,)


def test_dry_run_leaves_database_unchanged(legacy_database: Path) -> None:
    assert merge_database(legacy_database, dry_run=True) is None
    with sqlite3.connect(legacy_database) as connection:
        assert not connection.execute(
            "SELECT 1 FROM sqlite_master WHERE name = 'Registration_Settings'"
        ).fetchall()
    assert not list(legacy_database.parent.glob("*.bak"))


def test_failure_rolls_back_every_write(legacy_database: Path) -> None:
    with sqlite3.connect(legacy_database) as connection:
        connection.execute(
            "CREATE TABLE Registration_Members ("
            "Guild INTEGER, Channel INTEGER, Member INTEGER, Alias TEXT, "
            "PRIMARY KEY (Guild, Channel, Member, Alias))"
        )
    with pytest.raises(sqlite3.OperationalError, match="Role"):
        merge_database(legacy_database)
    with sqlite3.connect(legacy_database) as connection:
        assert not connection.execute(
            "SELECT 1 FROM sqlite_master WHERE name = 'Registration_Settings'"
        ).fetchall()
        assert connection.execute("SELECT COUNT(*) FROM WzRoles").fetchone() == (1,)


def test_malformed_source_is_reported_without_writes(legacy_database: Path) -> None:
    with sqlite3.connect(legacy_database) as connection:
        connection.execute(
            "ALTER TABLE WzRegistrations RENAME COLUMN Account TO Invalid"
        )
    with pytest.raises(ValueError, match="Account"):
        merge_database(legacy_database)
    assert not list(legacy_database.parent.glob("*.bak"))


def test_unassigned_records_are_kept_and_reported(
    legacy_database: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with sqlite3.connect(legacy_database) as connection:
        connection.execute("UPDATE WzRegistration SET Channel = NULL")
    with caplog.at_level(logging.WARNING):
        merge_database(legacy_database)
    assert "Channel=0" in caplog.text
    assert "cannot be assigned" in caplog.text
    with sqlite3.connect(legacy_database) as connection:
        assert connection.execute(
            "SELECT Channel FROM Registration_Members"
        ).fetchall() == [(0,), (0,)]
        assert connection.execute("SELECT COUNT(*) FROM WzList").fetchone() == (2,)
        assert connection.execute(
            "SELECT COUNT(*) FROM Module_Overviews"
        ).fetchone() == (0,)


def test_missing_file_is_not_created(tmp_path: Path) -> None:
    path = tmp_path / "missing.db"
    with pytest.raises(FileNotFoundError):
        merge_database(path)
    assert not path.exists()


def test_outdated_target_schema_is_rejected(legacy_database: Path) -> None:
    with sqlite3.connect(legacy_database) as connection:
        connection.execute(
            "CREATE TABLE Registration_Settings (Guild INTEGER PRIMARY KEY, Channel INTEGER)"
        )
    with pytest.raises(ValueError, match="outdated primary key"):
        merge_database(legacy_database, dry_run=True)
    with sqlite3.connect(legacy_database) as connection:
        assert (
            connection.execute("SELECT * FROM Registration_Settings").fetchall() == []
        )


def test_current_settings_and_role_scope_take_precedence(legacy_database: Path) -> None:
    merge_database(legacy_database)
    with sqlite3.connect(legacy_database) as connection:
        connection.execute("DELETE FROM Module_Overviews")
        connection.execute("DELETE FROM Registration_Members")
        connection.execute(
            "UPDATE Registration_Settings SET Message = 555, Title = 'Current'"
        )
        connection.execute("UPDATE Registration_Roles SET Channel = 12")
    merge_database(legacy_database)
    with sqlite3.connect(legacy_database) as connection:
        assert connection.execute(
            "SELECT Message, Title FROM Module_Overviews WHERE OverviewId = 'registration-10'"
        ).fetchone() == (555, "Current")
        assert connection.execute(
            "SELECT Channel FROM Registration_Members"
        ).fetchall() == [(12,), (12,)]


def test_missing_channel_with_multiple_targets_is_not_guessed(
    legacy_database: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    merge_database(legacy_database)
    with sqlite3.connect(legacy_database) as connection:
        connection.execute("DELETE FROM WzRegistration")
        connection.execute("DELETE FROM Registration_Roles")
        connection.execute("DELETE FROM Registration_Members")
        connection.execute(
            "INSERT INTO Registration_Settings (Guild, Channel) VALUES (1, 12)"
        )
    with caplog.at_level(logging.WARNING):
        merge_database(legacy_database)
    assert "no unambiguous registration channel" in caplog.text
    with sqlite3.connect(legacy_database) as connection:
        assert connection.execute(
            "SELECT Channel FROM Registration_Roles"
        ).fetchall() == [(0,)]


def test_backup_includes_uncheckpointed_wal_data(legacy_database: Path) -> None:
    writer = sqlite3.connect(legacy_database)
    try:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.execute("INSERT INTO Unrelated VALUES ('wal')")
        writer.commit()
        backup = merge_database(legacy_database)
        assert backup is not None
        with sqlite3.connect(backup) as connection:
            assert connection.execute("SELECT * FROM Unrelated").fetchall() == [
                ("keep",),
                ("wal",),
            ]
    finally:
        writer.close()


def test_standalone_cli_from_another_directory(
    legacy_database: Path,
    tmp_path: Path,
) -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(legacy_database), "--dry-run"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "preview rolled back" in result.stderr
    assert not list(tmp_path.glob("*.bak"))
