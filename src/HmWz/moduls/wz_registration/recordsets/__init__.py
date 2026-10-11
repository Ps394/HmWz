from .configuration import Configuration
from .list import WzList
from .registration import WzRegistration
from .registrations import WzRegistrations
from .roles import WzRoles

# Backward compatible alias used by older code paths.
Server = Configuration

__all__ = [
    "Configuration",
    "Server",
    "WzList",
    "WzRegistration",
    "WzRegistrations",
    "WzRoles",
]
