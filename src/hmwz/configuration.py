"""
Bot configuration loading and registration defaults.

The ``config`` mapping is loaded from ``configuration.json`` and falls back
to built-in defaults when the file is missing.

Configuration keys include ``bot.prefix``, ``bot.delay_seconds``, and
``bot.token_env``; database ``folder`` and ``filename``; and monitoring
interval and CPU, memory, disk, and temperature thresholds. The ``hs.wz``
settings define minimum and maximum registration roles plus overview defaults.
WZ settings remain compatible with the legacy ``wz_registration`` key.
"""

import json
import logging

_logger = logging.getLogger(__name__)


def _default_config() -> dict:
    """
    Build the default configuration used when no valid file is available.

    Returns:
        The default bot configuration.
    """
    return {
        "bot": {"prefix": "!", "delay_seconds": 0.1, "token_env": "WZ_BOT_TOKEN"},
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
    """Load configuration from a JSON file, creating defaults if it is missing.

    Args:
        path: Path to the configuration file.

    Returns:
        The loaded or default configuration.
    """
    try:
        with open(path) as f:
            return dict(json.load(f))
    except FileNotFoundError:
        _logger.error(f"Configuration file not found: {path}")
        default_conf: dict = _default_config()
        _logger.info(f"Using default configuration: {default_conf}")
        try:
            with open(path, "w") as f:
                json.dump(default_conf, f, indent=4)
            _logger.info(f"Default configuration file generated at: {path}")
            return default_conf
        except Exception as e:
            _logger.error(f"Failed to generate default configuration file: {e}")
            return default_conf
    except json.JSONDecodeError as e:
        _logger.error(f"Error decoding JSON from configuration file: {e}")
        return default_conf


global config

config: dict = _load_configuration()


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
