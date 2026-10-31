"""Load the bot token from the environment or platform-specific storage."""

import logging
import os
import sys

logger = logging.getLogger(__name__)


class Token:
    """Resolve a bot token from supported local sources."""

    @property
    def windowsOS(self) -> str:
        """Return the registry path containing the token."""
        return rf"Software\{self.key}"

    @property
    def linuxOS(self) -> str:
        """Return the configuration-file path containing the token."""
        return os.path.expanduser(f"~/.config/{self.key.lower()}/config")

    def __init__(self, name: str = "WZ_BOT_TOKEN", key: str = "HsBot"):
        """
        Configure the environment variable and storage key used for lookup.

        Args:
            name: Environment variable and value name for the token.
            key: Windows registry and Linux configuration directory key.
        """
        self.name: str = name
        self.key: str = key

    def get_linux_token(self) -> str | None:
        """
        Read the token from the Linux configuration file.

        The file uses one ``NAME=value`` entry per line.

        Returns:
            The configured token, or ``None`` if it is unavailable.
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
        Read the token from the current user's Windows registry.

        Returns:
            The configured token, or ``None`` if it is unavailable.
        """
        try:
            import winreg

            reg_key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, self.windowsOS, 0, winreg.KEY_READ
            )
            token, _ = winreg.QueryValueEx(reg_key, self.name)
            winreg.CloseKey(reg_key)
            logger.info("Bot token loaded from Windows Registry")
            return str(token)
        except (FileNotFoundError, OSError):
            return None

    def get_environment_token(self) -> str | None:
        """
        Read the token from its configured environment variable.

        Returns:
            The environment value, or ``None`` if it is not set.
        """
        return os.getenv(self.name)

    def get(self) -> str | None:
        """
        Resolve the token from the environment or platform-specific storage.

        Returns:
            The first available token, or ``None`` if no source has one.
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
        logger.error(
            f"Please set {self.name} environment variable or run install script to configure token."
        )
        return None
