"""Terminal lifecycle and raw mode context manager."""

from __future__ import annotations

import atexit
import logging
import os
import signal
import sys
from types import FrameType, TracebackType
from typing import Any

logger = logging.getLogger("pinak.media.lifecycle")


class TerminalSessionContext:
    """Manages the raw mode lifecycle and alternate screen buffer of the host terminal."""

    def __init__(self, enable_mouse: bool = True) -> None:
        self.enable_mouse = enable_mouse
        self._is_active = False

        self._orig_termios: Any = None
        self._orig_win_in_mode: int | None = None
        self._orig_win_out_mode: int | None = None
        self._orig_sigint_handler: Any = None
        self._orig_sigterm_handler: Any = None

    def __enter__(self) -> TerminalSessionContext:
        self.activate()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.restore()

    def activate(self) -> None:
        """Enters raw mode, switches to alternate buffer, and hides cursor."""
        if self._is_active:
            return

        # 1. Platform-specific raw mode setup
        if os.name == "nt":
            self._activate_windows_console()
        else:
            self._activate_posix_termios()

        # 2. Terminal escape configuration
        # Enter alternate buffer, hide cursor, disable line wrap, enable mouse
        seqs = [
            "\x1b[?1049h",  # Alternate screen buffer
            "\x1b[?25l",  # Hide cursor
            "\x1b[?7l",  # Disable line wrap
        ]
        if self.enable_mouse:
            seqs.append("\x1b[?1000h\x1b[?1006h")  # Normal tracking + SGR 1006 mode

        try:
            sys.stdout.write("".join(seqs))
            sys.stdout.flush()
        except OSError:
            pass

        # 3. Register atexit and signal handlers
        atexit.register(self.restore)
        try:
            self._orig_sigint_handler = signal.signal(signal.SIGINT, self._handle_signal)
            self._orig_sigterm_handler = signal.signal(signal.SIGTERM, self._handle_signal)
        except (ValueError, AttributeError):
            pass

        self._is_active = True

    def restore(self) -> None:
        """Restores main screen buffer, shows cursor, and exits raw mode."""
        if not self._is_active:
            return

        # 1. Reset terminal escape attributes
        seqs = [
            "\x1b[?1006l\x1b[?1000l",  # Disable mouse
            "\x1b[?7h",  # Re-enable line wrap
            "\x1b[?25h",  # Show cursor
            "\x1b[?2026l",  # Disable sync updates
            "\x1b[?1049l",  # Return to main screen buffer
            "\x1b[0m",  # Reset SGR styles
        ]
        try:
            sys.stdout.write("".join(seqs))
            sys.stdout.flush()
        except OSError:
            pass

        # 2. Platform-specific mode restoration
        if os.name == "nt":
            self._restore_windows_console()
        else:
            self._restore_posix_termios()

        # 3. Restore original signals
        try:
            if self._orig_sigint_handler is not None:
                signal.signal(signal.SIGINT, self._orig_sigint_handler)
            if self._orig_sigterm_handler is not None:
                signal.signal(signal.SIGTERM, self._orig_sigterm_handler)
        except (ValueError, AttributeError):
            pass

        self._is_active = False
        atexit.unregister(self.restore)

    def _activate_windows_console(self) -> None:
        """Enables VT processing and raw input on Windows ConPTY."""
        try:
            import ctypes
            from ctypes import wintypes

            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            h_in = kernel32.GetStdHandle(-10)  # STD_INPUT_HANDLE
            h_out = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE

            in_mode = wintypes.DWORD()
            out_mode = wintypes.DWORD()

            if kernel32.GetConsoleMode(h_in, ctypes.byref(in_mode)):
                self._orig_win_in_mode = in_mode.value
                # Disable line input and echo, enable virtual terminal input
                new_in = (in_mode.value & ~0x0002 & ~0x0004 & ~0x0001) | 0x0200
                kernel32.SetConsoleMode(h_in, new_in)

            if kernel32.GetConsoleMode(h_out, ctypes.byref(out_mode)):
                self._orig_win_out_mode = out_mode.value
                # Enable virtual terminal processing
                new_out = out_mode.value | 0x0004 | 0x0001
                kernel32.SetConsoleMode(h_out, new_out)
        except Exception as exc:
            logger.debug("Windows console mode activation failed: %s", exc)

    def _restore_windows_console(self) -> None:
        """Restores original Windows console modes."""
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            if self._orig_win_in_mode is not None:
                h_in = kernel32.GetStdHandle(-10)
                kernel32.SetConsoleMode(h_in, self._orig_win_in_mode)
            if self._orig_win_out_mode is not None:
                h_out = kernel32.GetStdHandle(-11)
                kernel32.SetConsoleMode(h_out, self._orig_win_out_mode)
        except Exception as exc:
            logger.debug("Windows console mode restore failed: %s", exc)

    def _activate_posix_termios(self) -> None:
        """Enables raw mode on POSIX termios."""
        if sys.platform == "win32":
            return
        try:
            import termios
            import tty

            fd = sys.stdin.fileno()
            self._orig_termios = termios.tcgetattr(fd)
            tty.setraw(fd)
        except Exception as exc:
            logger.debug("POSIX termios raw mode activation failed: %s", exc)

    def _restore_posix_termios(self) -> None:
        """Restores original POSIX termios mode."""
        if sys.platform == "win32":
            return
        try:
            import termios

            if self._orig_termios is not None:
                termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self._orig_termios)
        except Exception as exc:
            logger.debug("POSIX termios restore failed: %s", exc)

    def _handle_signal(self, signum: int, frame: FrameType | None) -> None:
        self.restore()
        sys.exit(128 + signum)

    @classmethod
    def reset_terminal(cls) -> None:
        """
        Unconditionally resets host console input/output modes, leaves alternate buffer,
        re-enables cursor, disables mouse tracking, and restores standard terminal styling.
        Safe to call on startup, recovery, or crash recovery commands.
        """
        reset_seqs = (
            "\x1b[?1049l"  # Leave alternate screen buffer
            "\x1b[?25h"  # Re-enable cursor visibility
            "\x1b[?7h"  # Re-enable autowrap
            "\x1b[?1000l"  # Disable standard mouse tracking
            "\x1b[?1006l"  # Disable SGR 1006 mouse mode
            "\x1b[?2026l"  # Disable synchronized update mode
            "\x1b[0m"  # Reset all ANSI color and style attributes
        )
        try:
            sys.stdout.write(reset_seqs)
            sys.stdout.flush()
        except Exception as exc:
            logger.debug("Terminal escape sequences reset failed: %s", exc)

        if os.name == "nt":
            try:
                import ctypes

                kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
                h_in = kernel32.GetStdHandle(-10)
                h_out = kernel32.GetStdHandle(-11)

                std_in = 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0080 | 0x0100
                kernel32.SetConsoleMode(h_in, std_in)

                std_out = 0x0001 | 0x0002 | 0x0004
                kernel32.SetConsoleMode(h_out, std_out)
            except Exception as exc:
                logger.debug("Windows console standard mode reset failed: %s", exc)
        else:
            try:
                import subprocess

                subprocess.run(
                    ["stty", "sane"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=0.5,
                )
            except Exception as exc:
                logger.debug("POSIX stty sane reset failed: %s", exc)
