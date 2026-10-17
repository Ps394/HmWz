import asyncio
import logging
import os

from hmwz.configuration import config

_logger = logging.getLogger(__name__)

try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    _logger.warning("psutil not available - resource monitoring disabled")


async def resource_monitor_loop(
    interval: int = config["monitoring"]["interval_seconds"],
):
    """
    Periodische Überwachung der Ressourcen (CPU, Speicher, Festplatte).

    :param interval: Zeitintervall in Sekunden zwischen den Überprüfungen (Standard: 60 Sekunden)
    :type interval: int
    """
    if not PSUTIL_AVAILABLE:
        _logger.info("Resource monitoring disabled (psutil not installed)")
        return

    await asyncio.sleep(1)  # Give time for the event loop to start
    process = psutil.Process(os.getpid())

    while True:
        try:
            mem_info = psutil.virtual_memory()
            temp_info = (
                psutil.sensors_temperatures()
                if hasattr(psutil, "sensors_temperatures")
                else None
            )
            storage_info = psutil.disk_usage("/")
            cpu_info = psutil.cpu_times_percent(interval=None)
            process.memory_full_info()
            cpu_percent = process.cpu_percent(interval=1)

            if temp_info:
                for name, entries in temp_info.items():
                    for entry in entries:
                        if (
                            entry.current
                            >= config["monitoring"]["temperature_threshold"]
                        ):
                            _logger.warning(
                                f"High temperature detected: {entry.label or name} at {entry.current:.1f}°C"
                            )

            if (
                cpu_info.user > config["monitoring"]["cpu_threshold"]
                or cpu_info.system > config["monitoring"]["cpu_threshold"]
            ):
                _logger.warning(f"High CPU usage detected: {cpu_percent:.1f}%")

            if mem_info.percent > config["monitoring"]["memory_threshold"]:
                _logger.warning(
                    f"High RAM usage detected: {mem_info.percent:.1f}% ({mem_info.used / 1024 / 1024:.1f} MB used of {mem_info.total / 1024 / 1024:.1f} MB)"
                )

            if storage_info.percent > config["monitoring"]["disk_threshold"]:
                _logger.warning(
                    f"High disk usage detected: {storage_info.percent:.1f}% ({storage_info.used / 1024 / 1024 / 1024:.1f} GB used of {storage_info.total / 1024 / 1024 / 1024:.1f} GB)"
                )

        except Exception as e:
            _logger.exception(f"Error monitoring resources: {e}")

        await asyncio.sleep(interval)
