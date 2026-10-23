"""Shared contracts for exporting snapshots."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class Snapshot:
    """A named data snapshot and its delivery destination."""

    destination_channel_id: int
    filename: str
    payload: Mapping[str, object]


class SnapshotExporter(Protocol):
    """Contract implemented by snapshot delivery backends."""

    async def export(self, snapshot: Snapshot) -> bool:
        """Deliver a snapshot and report whether delivery succeeded."""
        ...


__all__ = ["Snapshot", "SnapshotExporter"]
