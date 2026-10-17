# Import built-in modules so decorators register them.
from . import wz_registration
from .instance import Module, Modules, ModuleType
from .manager import Manager

__all__ = ["Manager", "Module", "ModuleType", "Modules", "wz_registration"]
