from .instance import Module, ModuleType, Modules
from .manager import Manager

# Import built-in modules so decorators register them.
from . import wz_registration

__all__ = ["Manager", "Module", "ModuleType", "Modules", "wz_registration"]
