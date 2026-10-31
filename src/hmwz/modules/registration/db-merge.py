"""Merge legacy Wz tables into Registration/Overview storage, without deleting them."""

from __future__ import annotations

import argparse
import logging
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

_logger = logging.getLogger(__name__)
type SqlValue = int | float | str | bytes | None
type Record = dict[str, SqlValue]
LEGACY_TABLES = ("WzRegistration", "WzRoles", "WzRegistrations", "WzList")
LEGACY_COLUMNS = {
    "WzRegistration": ("Guild", "Channel", "Message", "Title", "Description"),
    "WzRoles": ("Guild", "Role", "Permanent", "Score"),
    "WzRegistrations": ("Guild", "Member", "Account", "Role", "Timestamp"),
    "WzList": ("Guild", "Channel", "Message", "Title", "Text"),
}


def _rows(connection: sqlite3.Connection, table: str) -> list[Record]:
    exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
    ).fetchone()
    if exists is None:
        return []
    columns = {
        row["name"] for row in connection.execute(f'PRAGMA table_info("{table}")')
    }
    missing = set(LEGACY_COLUMNS[table]) - columns
    if missing:
        raise ValueError(f"{table}: missing required columns {sorted(missing)}.")
    return [dict(row) for row in connection.execute(f'SELECT * FROM "{table}"')]


def _create_schema(connection: sqlite3.Connection, path: Path) -> None:
    from hmwz.client.repositories.server import ServerRepository
    from hmwz.modules.overview.repositories.overview import OverviewRepository
    from hmwz.modules.registration.repositories import (
        MemberRegistrationRepository,
        RegistrationRoleRepository,
        RegistrationSettingsRepository,
    )
    from hmwz.sqlite_db import Database

    database = Database(folder=str(path.parent), filename=path.name)
    for repository_type in (
        ServerRepository,
        RegistrationSettingsRepository,
        RegistrationRoleRepository,
        MemberRegistrationRepository,
        OverviewRepository,
    ):
        connection.execute(repository_type(database).table)

    expected_keys = {
        "Servers": ("Guild",),
        "Registration_Settings": ("Guild", "Channel"),
        "Registration_Roles": ("Guild", "Role"),
        "Registration_Members": ("Guild", "Channel", "Member", "Alias"),
        "Module_Overviews": ("Guild", "OverviewId"),
    }
    for table, expected in expected_keys.items():
        columns = connection.execute(f'PRAGMA table_info("{table}")').fetchall()
        actual = tuple(
            row["name"]
            for row in sorted(columns, key=lambda row: row["pk"])
            if row["pk"]
        )
        if actual != expected:
            raise ValueError(
                f"{table} has an outdated primary key {actual}; "
                "migrate the current Registration schema first."
            )


def _merge(
    connection: sqlite3.Connection, table: str, keys: tuple[str, ...], values: Record
) -> None:
    where = " AND ".join(f'"{key}" IS ?' for key in keys)
    key_values = tuple(values[key] for key in keys)
    existing = connection.execute(
        f'SELECT * FROM "{table}" WHERE {where}', key_values
    ).fetchone()
    if existing is None:
        columns = ", ".join(f'"{column}"' for column in values)
        placeholders = ", ".join("?" for _ in values)
        connection.execute(
            f'INSERT INTO "{table}" ({columns}) VALUES ({placeholders})',
            tuple(values.values()),
        )
        return
    updates: Record = {}
    for column, value in values.items():
        if column in keys or value is None:
            continue
        current = existing[column]
        if current is None or current == "" or (column == "Channel" and current == 0):
            if current != value:
                updates[column] = value
        elif value != "" and current != value:
            _logger.warning(
                "%s %s: conflict in %s; keeping current value (source retained).",
                table,
                key_values,
                column,
            )
    if updates:
        assignments = ", ".join(f'"{column}" = ?' for column in updates)
        connection.execute(
            f'UPDATE "{table}" SET {assignments} WHERE {where}',
            (*updates.values(), *key_values),
        )


def _channel(connection: sqlite3.Connection, guild: SqlValue, legacy: Record) -> int:
    channel = legacy.get("Channel")
    if isinstance(channel, int) and channel > 0:
        return channel
    channels = connection.execute(
        "SELECT Channel FROM Registration_Settings WHERE Guild = ? AND Channel > 0",
        (guild,),
    ).fetchall()
    if len(channels) == 1:
        return channels[0]["Channel"]
    _logger.warning(
        "Guild %s: no unambiguous registration channel; retaining data at Channel=0.",
        guild,
    )
    return 0


def _list_order(row: Record) -> tuple[int, int]:
    guild, message = row["Guild"], row["Message"]
    if not isinstance(guild, int) or not isinstance(message, int):
        raise ValueError("WzList requires integer Guild and Message IDs.")
    return guild, message


def _transfer(connection: sqlite3.Connection, source: dict[str, list[Record]]) -> None:
    configurations = {row["Guild"]: row for row in source["WzRegistration"]}
    for rows in source.values():
        for row in rows:
            _merge(
                connection,
                "Servers",
                ("Guild",),
                {"Guild": row["Guild"], "Name": row.get("GuildName")},
            )

    for row in source["WzRegistration"]:
        values = {
            column: row[column]
            for column in ("Guild", "Channel", "Message", "Title", "Description")
        }
        _merge(connection, "Registration_Settings", ("Guild", "Channel"), values)

    for row in source["WzRoles"]:
        guild = row["Guild"]
        channel = _channel(connection, guild, configurations.get(guild, {}))
        _merge(
            connection,
            "Registration_Roles",
            ("Guild", "Role"),
            {
                "Guild": guild,
                "Channel": channel,
                "Role": row["Role"],
                "Permanent": row["Permanent"],
                "Score": row["Score"],
            },
        )

    for row in source["WzRegistrations"]:
        guild = row["Guild"]
        role = connection.execute(
            "SELECT Channel FROM Registration_Roles WHERE Guild = ? AND Role = ?",
            (guild, row["Role"]),
        ).fetchone()
        if role is not None and role["Channel"] > 0:
            channel = role["Channel"]
        else:
            channel = _channel(connection, guild, configurations.get(guild, {}))
        _merge(
            connection,
            "Registration_Members",
            ("Guild", "Channel", "Member", "Alias"),
            {
                "Guild": guild,
                "Channel": channel,
                "Member": row["Member"],
                "Alias": row["Account"],
                "Role": row["Role"],
                "Timestamp": row["Timestamp"],
                "MemberUsername": row.get("MemberUsername"),
                "MemberDisplayName": row.get("MemberDisplayName"),
                "RoleName": row.get("RoleName"),
            },
        )

    for row in source["WzRegistration"]:
        channel = _channel(connection, row["Guild"], row)
        if channel == 0:
            continue
        settings = connection.execute(
            "SELECT Message, Title, Description FROM Registration_Settings "
            "WHERE Guild = ? AND Channel = ?",
            (row["Guild"], channel),
        ).fetchone()
        content = settings if settings is not None else row
        _merge(
            connection,
            "Module_Overviews",
            ("Guild", "OverviewId"),
            {
                "Guild": row["Guild"],
                "OverviewId": f"registration-{channel}",
                "Channel": channel,
                "Message": content["Message"],
                "Title": content["Title"] or "",
                "Description": content["Description"] or "",
            },
        )

    pages: dict[tuple[SqlValue, int], int] = defaultdict(int)
    for row in sorted(source["WzList"], key=_list_order):
        guild = row["Guild"]
        channel = _channel(connection, guild, configurations.get(guild, {}))
        message_channel = row["Channel"]
        if channel == 0 or not isinstance(message_channel, int) or message_channel <= 0:
            _logger.warning(
                "WzList message %s cannot be assigned; source retained.", row["Message"]
            )
            continue
        pages[guild, channel] += 1
        _merge(
            connection,
            "Module_Overviews",
            ("Guild", "OverviewId"),
            {
                "Guild": guild,
                "OverviewId": f"registration-{channel}-list-{pages[guild, channel]}",
                "Channel": row["Channel"],
                "Message": row["Message"],
                "Title": row["Title"] or "",
                "Description": row["Text"] or "",
            },
        )


def merge_database(path: Path, *, dry_run: bool = False) -> Path | None:
    """Merge in-place atomically and return the backup path.

    The bot must be stopped. Current non-empty values win conflicts. Legacy
    tables remain intact. Dry runs roll back all changes and create no backup.
    Raises OSError, ValueError or sqlite3.Error on failure; writes are rolled back.
    """
    path = path.resolve(strict=True)
    backup_path: Path | None = None
    connection = sqlite3.connect(path.as_uri() + "?mode=rw", uri=True, timeout=5)
    connection.row_factory = sqlite3.Row
    try:
        source = {table: _rows(connection, table) for table in LEGACY_TABLES}
        if not any(source.values()):
            raise ValueError("No legacy Wz records found; nothing to merge.")
        if not dry_run:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            backup_path = path.with_name(
                f"{path.name}.pre-registration-merge-{stamp}.bak"
            )
            backup = sqlite3.connect(backup_path)
            try:
                connection.backup(backup)
            finally:
                backup.close()
            _logger.info("Backup created: %s", backup_path)
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("BEGIN IMMEDIATE")
        _create_schema(connection, path)
        _transfer(connection, source)
        violations = connection.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise ValueError(f"Foreign key check failed: {len(violations)} violations.")
        if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ValueError("Database integrity check failed.")
        if dry_run:
            connection.rollback()
        else:
            connection.commit()
        for table, rows in source.items():
            _logger.info("%s: processed %s source records.", table, len(rows))
        _logger.info(
            "Merge %s; legacy tables retained.",
            "preview rolled back" if dry_run else "committed",
        )
        return backup_path
    finally:
        connection.close()


def main() -> None:
    """Run the merge CLI, logging failures with a non-zero exit status."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    if __package__ is None:
        sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    try:
        merge_database(args.database, dry_run=args.dry_run)
    except (OSError, ValueError, sqlite3.Error):
        _logger.exception("Merge failed; transaction rolled back.")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
