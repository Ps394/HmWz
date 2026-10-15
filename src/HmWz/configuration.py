"""
Configurationsmodul für den Bot.

:param config: Ein Dictionary, das die Konfigurationen des Bots enthält, geladen aus der Datei "configuration.json".
"""

import json
import logging

_logger = logging.getLogger(__name__)


def _default_config() -> dict:
    """
    Gibt die Standardkonfigurationen zurück, die verwendet werden, wenn die Konfigurationsdatei nicht gefunden oder ungültig ist.

    :return: Ein Dictionary mit den Standardkonfigurationen.
    :rtype: dict
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
        "wz_registration": {
            "max_registration_roles": 4,
            "min_registration_roles": 1,
            "default_title": "Anmeldung",
            "default_description": "Klicke zum An-/Abmelden eine der Schaltflächen unten!",
        },
    }


def _load_configuration(path: str = "configuration.json") -> dict:
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
"""
Konfigurationen des Bots, geladen aus der Datei "configuration.json". Zugriff auf die Konfigurationen erfolgt über dieses Dictionary.

# Gruppe "bot":
- "prefix": Das Präfix, das der Bot für Befehle verwendet (z.B. "!").
- "delay_seconds": Die Verzögerung in Sekunden, die der Bot zwischen Befehlen einhält, um Ratenbegrenzungen zu vermeiden.
- "token_env": Der Name der Umgebungsvariable, die den Bot-Token enthält (z.B. "WZ_BOT_TOKEN").
# Gruppe "monitoring":
- "interval_seconds": Das Intervall in Sekunden, in dem die Systemressourcen überwacht werden.
- "cpu_threshold": Die CPU-Auslastungsgrenze in Prozent, bei der eine Warnung ausgegeben wird.
- "memory_threshold": Die Speicherauslastungsgrenze in Prozent, bei der eine Warnung ausgegeben wird.
- "disk_threshold": Die Festplattenauslastungsgrenze in Prozent, bei der eine Warnung ausgegeben wird.
- "temperature_threshold": Die Temperaturgrenze in Grad Celsius, bei der eine Warnung ausgegeben wird.
# Gruppe "wz_registration":
- "max_registration_roles": Die maximale Anzahl von Rollen, die für die Anmeldung verwendet werden können.
- "min_registration_roles": Die minimale Anzahl von Rollen, die für die Anmeldung verwendet werden müssen
- "default_title": Der Standardtitel für die Anmeldungsübersicht.
- "default_description": Die Standardbeschreibung für die Anmeldungsübersicht.
"""
