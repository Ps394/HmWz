# Import built-in modules so decorators register them.
from . import donation, registration, hs, queue, overview
from .protocols import Module, Modules, ModuleType
from .manager import Manager

__all__ = [
    "Manager",
    "Module",
    "ModuleType",
    "Modules",
    "donation",
    "hs",
    "queue",
    "registration",
    "overview",
]
