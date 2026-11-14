"""Validate and import Discord-to-game-account mappings."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TypedDict

import discord

from .repositories import MemberGameAccountRepository


class AccountEntry(TypedDict):
    discord_username: str
    players: list[str]


@dataclass
class ImportResult:
    imported: int = 0
    existing: int = 0
    skipped: int = 0
    issues: list[str] = field(default_factory=list)


def parse_entries(content: str | bytes) -> list[AccountEntry]:
    """Validate all entries before importing any accounts."""
    data = json.loads(content)
    if not isinstance(data, list):
        raise ValueError("The JSON must contain a list of account entries")
    entries: list[AccountEntry] = []
    for entry in data:
        if not isinstance(entry, dict):
            raise ValueError("Every account entry must be an object")
        username = entry.get("discord_username")
        players = entry.get("players")
        if (
            not isinstance(username, str)
            or not username.strip()
            or not isinstance(players, list)
            or not players
            or not all(
                isinstance(player, str) and 2 <= len(player.strip()) <= 100
                for player in players
            )
        ):
            raise ValueError("Invalid account entry")
        entries.append(
            {
                "discord_username": username.strip(),
                "players": [player.strip() for player in players],
            }
        )
    return entries


async def import_entries(
    guild: discord.Guild,
    repository: MemberGameAccountRepository,
    entries: list[AccountEntry],
) -> ImportResult:
    """Import uniquely resolved accounts without replacing existing owners."""
    members: dict[str, list[discord.Member]] = {}
    async for member in guild.fetch_members(limit=None):
        members.setdefault(member.name.casefold(), []).append(member)
        if member.discriminator != "0":
            members.setdefault(str(member).casefold(), []).append(member)

    result = ImportResult()
    for entry in entries:
        username = entry["discord_username"]
        matches = members.get(username.casefold(), [])
        if len(matches) != 1:
            result.skipped += len(entry["players"])
            result.issues.append(
                f"Discord username {username!r}: {len(matches)} matches"
            )
            continue
        member = matches[0]
        for player in entry["players"]:
            existing = await repository.get(guild=guild, account=player)
            if existing:
                if existing[0].member == member.id:
                    result.existing += 1
                else:
                    result.skipped += 1
                    result.issues.append(
                        f"Account {player!r}: already owned by another member"
                    )
                continue
            if await repository.add(guild=guild, member=member.id, account=player):
                result.imported += 1
            else:
                result.skipped += 1
                result.issues.append(f"Account {player!r}: database insert failed")
    return result
