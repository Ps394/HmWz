"""Compatibility exports for registration setup components."""

from .main import RegistrationConfigView
from .roles import (
    RegistrationRoleRemovalSelect,
    RegistrationRoleRemovalView,
    RegistrationRoleSelect,
    RegistrationRoleView,
)
from .content import RegistrationTextModal, RegistrationTitleModal
from .export_channel import (
    RegistrationExportChannelSelect as RegistrationExportChannelSelect,
    RegistrationExportChannelView as RegistrationExportChannelView,
)
from .draft import RegistrationSetupDraft
from .service import save_registration_draft


async def _save_registration_draft(draft, interaction):
    """Compatibility wrapper for existing setup imports."""
    return await save_registration_draft(draft, interaction)


__all__ = [
    "RegistrationConfigView",
    "RegistrationRoleRemovalSelect",
    "RegistrationRoleRemovalView",
    "RegistrationRoleSelect",
    "RegistrationRoleView",
    "RegistrationTextModal",
    "RegistrationTitleModal",
    "RegistrationExportChannelSelect",
    "RegistrationExportChannelView",
    "RegistrationSetupDraft",
]
