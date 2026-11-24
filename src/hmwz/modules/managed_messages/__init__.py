"""Reusable infrastructure for bot-managed Discord messages."""

from .models import ManagedMessage, ManagedTargetKind, ManagedThread
from .module import ManagedMessagesModule
from .protocols import (
    ManagedBatchRefreshHandler,
    ManagedChannelDeleteHandler,
    ManagedMessageRefreshHandler,
    ManagedThreadDeleteHandler,
    ManagedViewFactory,
)
from .repositories import ManagedMessageRepository, ManagedThreadRepository
from .migrate import migrate_overviews

__all__ = [
    "ManagedMessage",
    "ManagedThread",
    "ManagedTargetKind",
    "ManagedBatchRefreshHandler",
    "ManagedChannelDeleteHandler",
    "ManagedThreadDeleteHandler",
    "ManagedMessageRefreshHandler",
    "ManagedMessagesModule",
    "ManagedMessageRepository",
    "ManagedThreadRepository",
    "migrate_overviews",
    "ManagedViewFactory",
]
