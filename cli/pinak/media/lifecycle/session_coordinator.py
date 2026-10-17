"""Process-level media session coordinator and CLI mutual exclusion lock."""

from __future__ import annotations

import logging
import threading
from typing import Any

logger = logging.getLogger("pinak.media.session")


class MediaSessionCoordinator:
    """Coordinates lifecycle locks between the Pinak CLI REPL and active TUI media sessions."""

    _active_session: Any | None = None
    _lock: threading.RLock = threading.RLock()

    @classmethod
    def is_media_active(cls) -> bool:
        """Returns True if a TUI media session is currently occupying the terminal."""
        with cls._lock:
            if cls._active_session is None:
                return False
            return getattr(cls._active_session, "is_running", True)

    @classmethod
    def acquire_session(cls, session: Any) -> None:
        """Registers a new active media session, terminating any prior session."""
        with cls._lock:
            if cls.is_media_active():
                cls.request_close_active_session(reason="superseded_by_new_session")
            cls._active_session = session
            logger.info("Media session acquired by TUI engine")

    @classmethod
    def release_session(cls) -> None:
        """Releases the active session lock."""
        with cls._lock:
            cls._active_session = None
            logger.info("Media session released; CLI prompt receptive")

    @classmethod
    def request_close_active_session(cls, reason: str = "user_exit") -> None:
        """Triggers graceful teardown of the active media player."""
        with cls._lock:
            if cls._active_session is not None:
                logger.info(f"Requesting media session close: {reason}")
                if hasattr(cls._active_session, "stop"):
                    cls._active_session.stop()
                elif hasattr(cls._active_session, "close"):
                    cls._active_session.close()
                cls._active_session = None

    @classmethod
    def format_suspended_cli_banner(cls) -> str:
        """Generates the notification banner displayed when media starts playing in TUI."""
        return (
            "\n[bold yellow]╔══════════════════════════════════════════════════════════════════════════════╗[/bold yellow]\n"
            "[bold yellow]║  🔱 PINAK TUI MEDIA PLAYER ACTIVE | Media is Playing in TUI                  ║[/bold yellow]\n"
            "[bold yellow]║  TUI Media Player is working. Pinak-CLI command input is locked.             ║[/bold yellow]\n"
            "[bold yellow]║  Close the TUI Media Player window or press \\[x] in TUI to resume Pinak-CLI.  ║[/bold yellow]\n"
            "[bold yellow]╚══════════════════════════════════════════════════════════════════════════════╝[/bold yellow]\n"
        )

    @classmethod
    def format_return_cli_banner(cls) -> str:
        """Generates the welcome return message displayed after closing media player."""
        return "\n[bold green]✓ TUI Media Player closed.[/bold green] Pinak-CLI command input restored.\n"
