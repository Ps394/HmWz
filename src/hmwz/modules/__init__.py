"""Guild-scoped module management and reusable module services."""

# Import built-in modules so decorators register them.
from . import registration, donation
from .protocols import  ModuleProtocol, Modules, ModuleType
from .manager import Manager

__all__ = [
    "Manager",
    "ModuleProtocol",
    "ModuleType",
    "Modules",
    "registration",
    "donation",
]
