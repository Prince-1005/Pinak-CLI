"""Terminal capability detection and interrogation engine."""

from __future__ import annotations

import os
import re
import select
import shutil
import sys
import time
from dataclasses import dataclass


@dataclass
class TerminalCapabilities:
    """Represents the discovered graphics and layout capabilities of the host terminal."""

    has_kitty: bool = False
    has_sixel: bool = False
    has_iterm2: bool = False
    has_truecolor: bool = False
    has_sync_updates: bool = False
    cell_width_px: int = 10
    cell_height_px: int = 20
    cols: int = 80
    rows: int = 24

    @property
    def cell_aspect_ratio(self) -> float:
        """Ratio of cell height to cell width (typically ~2.0 for character terminals)."""
        if self.cell_width_px <= 0:
            return 2.0
        return self.cell_height_px / self.cell_width_px

    @property
    def primary_graphics_mode(self) -> str:
        """Determines the best available rendering mode for the host terminal."""
        if self.has_kitty:
            return "kitty"
        if self.has_sixel:
            return "sixel"
        if self.has_iterm2:
            return "iterm2"
        if self.has_truecolor:
            return "halfblock"
        return "ascii"


class TerminalProber:
    """Probes the host terminal for graphics protocols and dimensions with timeout protection."""

    PROBE_TIMEOUT_SECONDS: float = 0.040

    @classmethod
    def probe(cls, skip_active_interrogation: bool = False) -> TerminalCapabilities:
        """Inspects environment and optionally interrogates the TTY via escape sequences."""
        cols, rows = shutil.get_terminal_size(fallback=(80, 24))
        caps = TerminalCapabilities(cols=cols, rows=rows)

        # 1. Environment variable inspection (fast path)
        env_term = os.environ.get("TERM", "").lower()
        env_term_program = os.environ.get("TERM_PROGRAM", "")
        env_colorterm = os.environ.get("COLORTERM", "").lower()

        # Modern operating systems (Windows 10/11) and modern terminals natively support 24-bit TrueColor.
        if (
            os.name == "nt"
            or env_colorterm in ("truecolor", "24bit")
            or "kitty" in env_term
            or "alacritty" in env_term
            or "xterm" in env_term
            or env_term not in ("dumb", "")
        ):
            caps.has_truecolor = True

        # Kitty Protocol Auto-Elevation:
        # Check TERM, KITTY_WINDOW_ID, KITTY_PID, or modern emulators supporting Kitty APC graphics
        if (
            "kitty" in env_term
            or "ghostty" in env_term
            or bool(os.environ.get("KITTY_WINDOW_ID"))
            or bool(os.environ.get("KITTY_PID"))
            or bool(os.environ.get("GHOSTTY_RESOURCES_DIR"))
            or env_term_program in ("kitty", "ghostty", "WezTerm")
            or bool(os.environ.get("WEZTERM_PANE"))
        ):
            caps.has_kitty = True
            caps.has_sync_updates = True

        # Sixel Protocol Auto-Elevation:
        # Check TERM with sixel, foot terminal, mintty, mlterm
        if (
            "sixel" in env_term
            or env_term in ("foot", "foot-extra")
            or env_term_program == "mintty"
            or bool(os.environ.get("MINTTY_SHORTCUT"))
            or bool(os.environ.get("MLTERM"))
        ):
            caps.has_sixel = True

        if env_term_program == "iTerm.app" or bool(os.environ.get("ITERM_SESSION_ID")):
            caps.has_iterm2 = True
            caps.has_sync_updates = True

        # 1b. Query actual font cell dimensions via native OS APIs
        cls._query_cell_dimensions_native(caps)

        if skip_active_interrogation or not sys.stdin.isatty():
            return caps

        # 2. Synchronous interrogation if interactive TTY is available
        try:
            raw_response = cls._query_raw_terminal()
            cls._parse_probe_responses(raw_response, caps)
        except Exception:
            # Silently tolerate any I/O probe failures and fall back to heuristics
            pass

        return caps

    @classmethod
    def _query_cell_dimensions_native(cls, caps: TerminalCapabilities) -> None:
        """Queries precise font cell width and height in pixels via OS APIs."""
        if sys.platform == "win32":
            try:
                import ctypes
                from ctypes import wintypes

                class COORD(ctypes.Structure):
                    _fields_ = [("X", wintypes.SHORT), ("Y", wintypes.SHORT)]

                class CONSOLE_FONT_INFOEX(ctypes.Structure):
                    _fields_ = [
                        ("cbSize", wintypes.ULONG),
                        ("nFont", wintypes.DWORD),
                        ("dwFontSize", COORD),
                        ("FontFamily", wintypes.UINT),
                        ("FontWeight", wintypes.UINT),
                        ("FaceName", wintypes.WCHAR * 32),
                    ]

                handle = ctypes.windll.kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
                info = CONSOLE_FONT_INFOEX()
                info.cbSize = ctypes.sizeof(CONSOLE_FONT_INFOEX)
                if ctypes.windll.kernel32.GetCurrentConsoleFontEx(
                    handle, False, ctypes.byref(info)
                ):
                    w = int(info.dwFontSize.X)
                    h = int(info.dwFontSize.Y)
                    if w > 0 and h > 0:
                        caps.cell_width_px = w
                        caps.cell_height_px = h
            except Exception:
                pass
        else:
            try:
                import fcntl
                import struct
                import termios

                res = fcntl.ioctl(sys.stdout.fileno(), termios.TIOCGWINSZ, b"\x00" * 8)
                r_rows, r_cols, xpixels, ypixels = struct.unpack("HHHH", res)
                if xpixels > 0 and ypixels > 0 and r_cols > 0 and r_rows > 0:
                    caps.cell_width_px = max(1, xpixels // r_cols)
                    caps.cell_height_px = max(1, ypixels // r_rows)
            except Exception:
                pass

    @classmethod
    def _query_raw_terminal(cls) -> bytes:
        """Transmits interrogation tokens and reads back response tokens within timeout."""
        if sys.platform == "win32":
            # On Windows ConPTY, avoid blocking stdin read if unsupported
            return b""

        # Primary DA (Sixel), Kitty query, Cell size query
        query_payload = b"\x1b[c\x1b_Gi=1,s=1,v=1,a=q,t=d,f=24;AAAA\x1b\\\x1b[16t"
        try:
            sys.stdout.buffer.write(query_payload)
            sys.stdout.buffer.flush()
        except (AttributeError, OSError):
            return b""

        collected = bytearray()
        deadline = time.perf_counter() + cls.PROBE_TIMEOUT_SECONDS

        while time.perf_counter() < deadline:
            remaining = max(0.001, deadline - time.perf_counter())
            r, _, _ = select.select([sys.stdin.fileno()], [], [], remaining)
            if not r:
                break
            try:
                chunk = os.read(sys.stdin.fileno(), 1024)
                if not chunk:
                    break
                collected.extend(chunk)
            except OSError:
                break

        return bytes(collected)

    @classmethod
    def _parse_probe_responses(cls, raw: bytes, caps: TerminalCapabilities) -> None:
        """Parses collected raw escape tokens into capability flags."""
        if not raw:
            return

        if b"i=1;OK" in raw or b"i=1;ok" in raw:
            caps.has_kitty = True

        # Sixel check in DA response: e.g. \x1b[?62;4;...c
        if b";4;" in raw or raw.endswith(b";4c") or b"?4;" in raw:
            caps.has_sixel = True

        # Cell size response: \x1b[6;{height};{width}t
        cell_match = re.search(rb"\x1b\[6;(\d+);(\d+)t", raw)
        if cell_match:
            try:
                h = int(cell_match.group(1))
                w = int(cell_match.group(2))
                if h > 0 and w > 0:
                    caps.cell_height_px = h
                    caps.cell_width_px = w
            except ValueError:
                pass
