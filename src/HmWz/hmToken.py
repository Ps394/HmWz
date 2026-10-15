import logging
import os
import sys

logger = logging.getLogger(__name__)


class Token:
    @property
    def windowsOS(self) -> str:
        return rf"Software\{self.key}"

    @property
    def linuxOS(self) -> str:
        return os.path.expanduser(f"~/.config/{self.key.lower()}/config")

    def __init__(self, name: str = "WZ_BOT_TOKEN", key: str = "HsBot"):
        """
        Initialisiert die Token-Klasse mit dem Namen des Tokens, der gesucht werden soll.

        :param name: Der Name des Tokens (z.B. "WZ_BOT_TOKEN")
        :type name: str
        :param key: Der Schlüssel für die Windows-Registry und den Linux-Konfigurationsordner (z.B. "HsBot")
        :type key: str
        """
        self.name: str = name
        self.key: str = key

    def get_linux_token(self) -> str | None:
        """
        Auslesen des Tokens aus der Konfigurationsdatei unter Linux/Unix

            Config-Datei-Format:

            WZ_BOT_TOKEN=dein_token_hier

        :return: Der Bot-Token oder None, wenn er nicht gefunden wurde
        :rtype: typing.Optional[str]

        """
        if os.path.exists(self.linuxOS):
            try:
                with open(self.linuxOS) as f:
                    for line in f:
                        if line.startswith(f"{self.name}="):
                            token = line.split("=", 1)[1].strip()
                            logger.info("Bot token loaded from config file")
                            return token
            except Exception as e:
                logger.warning(f"Failed to read config file: {e}")
        return None

    def get_windows_token(self) -> str | None:
        """
        Auslesen des Tokens aus der Windows-Registry

        :return: Der Bot-Token oder None, wenn er nicht gefunden wurde
        :rtype: typing.Optional[str]
        """
        try:
            import winreg

            reg_key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.windowsOS, 0, winreg.KEY_READ)
            token, _ = winreg.QueryValueEx(reg_key, self.name)
            winreg.CloseKey(reg_key)
            logger.info("Bot token loaded from Windows Registry")
            return str(token)
        except (FileNotFoundError, OSError):
            return None

    def get_environment_token(self) -> str | None:
        """
        Auslesen des Tokens aus der Umgebung

        :return: Der Bot-Token oder None, wenn er nicht gefunden wurde
        :rtype: typing.Optional[str]
        """
        return os.getenv(self.name)

    def get(self) -> str | None:
        """
        Holt den Bot-Token aus der Umgebung, der Windows-Registry oder der Linux-Konfigurationsdatei.

        :return: Der Bot-Token oder None, wenn er nicht gefunden wurde
        :rtype: typing.Optional[str]
        """
        token = self.get_environment_token()
        if token:
            return token

        if sys.platform == "win32":
            token = self.get_windows_token()
            if token:
                return token

        if sys.platform in ("linux", "darwin"):
            token = self.get_linux_token()
            if token:
                return token

        logger.error("No bot token found!")
        logger.error(f"Please set {self.name} environment variable or run install script to configure token.")
        return None
