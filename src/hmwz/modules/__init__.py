# Import built-in modules so decorators register them.
from . import registrations, hs
from .instance import Module, Modules, ModuleType
from .manager import Manager

__all__ = ["Manager", "Module", "ModuleType", "Modules", "hs", "registrations"]
