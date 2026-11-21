"""
Bot configuration loading and registration defaults.

The ``config`` mapping is loaded from ``configuration.json`` and falls back
to built-in defaults when the file is missing or invalid.

Configuration keys include ``bot.prefix``, ``bot.delay_seconds``, and
``bot.token_env``; database ``folder`` and ``filename``; and monitoring
interval and CPU, memory, disk, and temperature thresholds. The ``hs.wz``
settings define minimum and maximum registration roles plus overview defaults.
Moderator role names are configured in ``moderator_roles``. WZ settings remain
compatible with the legacy ``wz_registration`` key.
"""

import json
import logging

_logger = logging.getLogger(__name__)
_DEFAULT_MODERATOR_ROLES = (
    "Offiziere",
    "offiziere",
    "Moderator",
    "moderator",
    "officier",
    "Officier",
)


def _default_config() -> dict:
    """
    Build the default configuration used when no valid file is available.

    Returns:
        The default bot configuration.
    """
    return {
        "bot": {"prefix": "!", "delay_seconds": 0.1, "token_env": "WZ_BOT_TOKEN"},
        "moderator_roles": list(_DEFAULT_MODERATOR_ROLES),
        "database": {"folder": "data", "filename": "data.db"},
        "monitoring": {
            "interval_seconds": 60,
            "cpu_threshold": 90.0,
            "memory_threshold": 80.0,
            "disk_threshold": 90.0,
            "temperature_threshold": 80.0,
        },
        "hs": {
            "wz": {
                "max_registration_roles": 4,
                "min_registration_roles": 1,
                "default_title": "Anmeldung",
                "default_description": "Klicke zum An-/Abmelden eine der Schaltflächen unten!",
            },
            "qs": {
                "max_registration_roles": 4,
                "default_title": "QS-Anmeldung",
                "default_description": "Melde dich über eine der Schaltflächen an. "
                "Die Übersicht dient der Planung.",
            },
        },
    }


def _load_configuration(path: str = "configuration.json") -> dict:
    """Load configuration, using defaults for a missing or invalid file.

    Args:
        path: Path to the configuration file.

    Returns:
        The loaded or default configuration.
    """
    default_conf = _default_config()
    try:
        with open(path, encoding="utf-8") as f:
            loaded = json.load(f)
        if not isinstance(loaded, dict):
            raise TypeError("Configuration file must contain a JSON object.")
        return loaded
    except FileNotFoundError:
        _logger.error("Configuration file not found: %s", path)
        _logger.info("Using default configuration: %s", default_conf)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(default_conf, f, indent=4)
            _logger.info("Default configuration file generated at: %s", path)
            return default_conf
        except OSError as e:
            _logger.error(
                "Failed to generate default configuration file: %s", e, exc_info=True
            )
            return default_conf
    except (json.JSONDecodeError, TypeError) as e:
        _logger.error(
            "Invalid configuration file %s; using built-in defaults: %s",
            path,
            e,
        )
        return default_conf


global config

config: dict = _load_configuration()

_configured_moderator_roles = config.get("moderator_roles", _DEFAULT_MODERATOR_ROLES)
if (
    not isinstance(_configured_moderator_roles, (list, tuple))
    or not _configured_moderator_roles
    or not all(
        isinstance(role, str) and role.strip() for role in _configured_moderator_roles
    )
):
    raise ValueError(
        "Configuration key 'moderator_roles' must be a non-empty list of role names."
    )
MODERATOR_ROLES: tuple[str, ...] = tuple(_configured_moderator_roles)


def wz_registration_config() -> dict:
    """Return WZ settings from the new namespace or the legacy config key.

    Returns:
        The WZ registration settings, or an empty mapping when unavailable.
    """
    return registration_defaults("wz")


def registration_defaults(module_key: str) -> dict:
    """Return defaults for a registration module.

    Args:
        module_key: Registration configuration key to retrieve.

    Returns:
        The matching settings, or an empty mapping when unavailable.
    """
    hs_config = config.get("hs")
    if isinstance(hs_config, dict):
        registration_config = hs_config.get(module_key)
        if isinstance(registration_config, dict):
            return registration_config
    if module_key != "wz":
        return {}
    legacy_config = config.get("wz_registration")
    return legacy_config if isinstance(legacy_config, dict) else {}
