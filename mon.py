import subprocess
import psutil


def get_service_pid(service_name: str = "discordbot.service") -> int:
    """Return the MainPID of a systemd service, with pidof as fallback."""
    try:
        output = subprocess.check_output(
            ["systemctl", "show", "-p", "MainPID", "--value", service_name],
            text=True,
        ).strip()
        pid = int(output)
        if pid > 0:
            return pid
    except (subprocess.CalledProcessError, ValueError):
        pass

    output = subprocess.check_output(["pidof", "-s", "discordbot"], text=True).strip()
    pid = int(output)
    if pid <= 0:
        raise RuntimeError(f"No valid PID found for {service_name}")
    return pid


def main() -> None:
    pid = get_service_pid("discordbot.service")
    discordbot = psutil.Process(pid)
    memory = psutil.virtual_memory()

    print(f"Discord service PID: {pid}")
    print(f"Total memory: {memory.total / (1024 ** 3):.2f} GB")
    print(f"Available memory: {memory.available / (1024 ** 3):.2f} GB")
    print(f"Used memory: {memory.used / (1024 ** 3):.2f} GB")
    print(f"Memory usage: {memory.percent}%")

    cpu = psutil.cpu_percent(interval=1)
    print(f"CPU usage: {cpu}%")

    print(f"Discord bot memory usage: {discordbot.memory_info().rss / (1024 ** 2):.2f} MB")


if __name__ == "__main__":
    main()