from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class Local:
    local = {"EN", "DE"}

    app_cmd_err_MissingPermissions = {"D"}