from .configuration import Configuration
from .roles import WzRoles
from .registration import WzRegistration
from .registrations import WzRegistrations
from .list import WzList

# Backward compatible alias used by older code paths.
Server = Configuration

__all__ = [
	"Configuration",
	"WzRoles",
	"WzRegistration",
	"WzRegistrations",
	"WzList",
	"Server",
]