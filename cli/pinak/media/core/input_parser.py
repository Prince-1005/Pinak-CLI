"""Non-blocking ANSI keyboard and SGR mouse input parser."""

from __future__ import annotations

import os
import re
import sys
import time
from dataclasses import dataclass


@dataclass
class KeyEvent:
    """Represents a keyboard stroke."""

    key: str  # e.g., 'a', 'space', 'enter', 'up', 'down', 'left', 'right', 'esc', 'q'
    ctrl: bool = False
    alt: bool = False
    shift: bool = False


@dataclass
class MouseEvent:
    """Represents a mouse event under SGR 1006 protocol."""

    button: int  # 0: Left, 1: Middle, 2: Right, 64: WheelUp, 65: WheelDown
    col: int
    row: int
    is_pressed: bool
    is_move: bool = False


InputEvent = KeyEvent | MouseEvent


class InputParser:
    """Tokenizes raw terminal standard input into structured keyboard and mouse events."""

    _SGR_MOUSE_REGEX = re.compile(rb"\x1b\[<(\d+);(\d+);(\d+)([Mm])")

    MOUSE_MOVE_INTERVAL: float = 0.016  # Max 60Hz mouse drag rate to prevent buffer flooding

    def __init__(self) -> None:
        self._buffer = bytearray()
        self._last_mouse_move_time: float = 0.0
        self._pending_since: float = 0.0

    def poll_events(self, timeout_seconds: float = 0.0) -> list[InputEvent]:
        """Reads non-blocking input from stdin and returns all parsed events."""
        events: list[InputEvent] = []
        raw_bytes = self._read_nonblocking(timeout_seconds)
        if raw_bytes:
            if not self._buffer:
                self._pending_since = time.perf_counter()
            self._buffer.extend(raw_bytes)
            if len(self._buffer) > 65536:
                self._buffer.clear()
                return events

        while self._buffer:
            if self._buffer == b"\x1b" and time.perf_counter() - self._pending_since < 0.03:
                break
            event, consumed = self._parse_next_event(bytes(self._buffer))
            if consumed > 0:
                del self._buffer[:consumed]
                if event is not None:
                    if isinstance(event, MouseEvent) and event.is_move:
                        now = time.perf_counter()
                        if now - self._last_mouse_move_time < self.MOUSE_MOVE_INTERVAL:
                            continue
                        self._last_mouse_move_time = now
                    events.append(event)
            else:
                if time.perf_counter() - self._pending_since > 0.1:
                    del self._buffer[:1]
                    self._pending_since = time.perf_counter()
                    continue
                break

        return events

    def _read_nonblocking(self, timeout_sec: float) -> bytes:
        """Platform-specific non-blocking read."""
        if os.name == "nt":
            import msvcrt

            collected = bytearray()
            deadline = time.perf_counter() + timeout_sec
            try:
                import ctypes

                has_user32 = hasattr(ctypes, "windll") and hasattr(ctypes.windll, "user32")
            except Exception:
                has_user32 = False

            while True:
                if msvcrt.kbhit():  # type: ignore[attr-defined]
                    ch = msvcrt.getwch()  # type: ignore[attr-defined]
                    if ch in ("\x00", "\xe0"):
                        special = msvcrt.getwch()
                        sequence = {
                            "H": b"\x1b[A",
                            "P": b"\x1b[B",
                            "K": b"\x1b[D",
                            "M": b"\x1b[C",
                            "I": b"\x1b[5~",
                            "Q": b"\x1b[6~",
                            "G": b"\x1b[H",
                            "O": b"\x1b[F",
                        }.get(special)
                        if sequence:
                            collected.extend(sequence)
                        continue
                    if "\ud800" <= ch <= "\udbff":
                        ch = (
                            (ch + msvcrt.getwch())
                            .encode("utf-16", errors="surrogatepass")
                            .decode("utf-16", errors="replace")
                        )
                    if (
                        ch in ("\r", "\n", "\x0d", "\x0a")
                        and has_user32
                        and ctypes.windll.user32.GetAsyncKeyState(0x11) & 0x8000
                    ):
                        collected.extend(b"\x1b[109;5u")
                        continue
                    collected.extend(ch.encode("utf-8", errors="replace"))
                    if len(collected) >= 4096:
                        break
                elif time.perf_counter() >= deadline:
                    break
                else:
                    time.sleep(0.002)
            return bytes(collected)
        else:
            import select

            r, _, _ = select.select([sys.stdin.fileno()], [], [], max(0.0, timeout_sec))
            if r:
                try:
                    return os.read(sys.stdin.fileno(), 1024)
                except OSError:
                    return b""
            return b""

    def _parse_next_event(self, data: bytes) -> tuple[InputEvent | None, int]:
        """Parses a single event from the start of data. Returns (event, consumed_bytes)."""
        if not data:
            return None, 0

        # 1. SGR Mouse event: \x1b[<{btn};{col};{row}M or m
        mouse_match = self._SGR_MOUSE_REGEX.match(data)
        if mouse_match:
            btn = int(mouse_match.group(1))
            col = int(mouse_match.group(2))
            row = int(mouse_match.group(3))
            is_press = mouse_match.group(4) == b"M"
            consumed = mouse_match.end()
            return (
                MouseEvent(
                    button=btn,
                    col=col,
                    row=row,
                    is_pressed=is_press,
                    is_move=(btn & 32 != 0),
                ),
                consumed,
            )

        # 2. Escape sequence handling
        if data[0] == 0x1B:
            if len(data) == 1:
                return KeyEvent(key="esc"), 1

            # Arrow keys & function keys: \x1b[A, \x1b[B, \x1b[C, \x1b[D
            if data.startswith(b"\x1b[A"):
                return KeyEvent(key="up"), 3
            if data.startswith(b"\x1b[B"):
                return KeyEvent(key="down"), 3
            if data.startswith(b"\x1b[C"):
                return KeyEvent(key="right"), 3
            if data.startswith(b"\x1b[D"):
                return KeyEvent(key="left"), 3
            if data.startswith(b"\x1b[H"):
                return KeyEvent(key="home"), 3
            if data.startswith(b"\x1b[F"):
                return KeyEvent(key="end"), 3
            if data.startswith(b"\x1b[5~"):
                return KeyEvent(key="pageup"), 4
            if data.startswith(b"\x1b[6~"):
                return KeyEvent(key="pagedown"), 4
            if (
                data.startswith(b"\x1b[109;5u")
                or data.startswith(b"\x1b[77;5u")
                or data.startswith(b"\x1b[109;6u")
                or data.startswith(b"\x1b[77;6u")
            ):
                return KeyEvent(key="m", ctrl=True), 8
            if data.startswith(b"\x1b[13;5u") or data.startswith(b"\x1b[13;6u"):
                return KeyEvent(key="m", ctrl=True), 7

            if data.startswith(b"\x1b[200~"):
                return None, 6
            if data.startswith(b"\x1b[201~"):
                return None, 6

            # Partial sequence waiting for more bytes
            if len(data) < 3 and data.startswith(b"\x1b["):
                return None, 0
            if data.startswith(b"\x1b[") and len(data) < 64 and data[-1:] in b"0123456789;<":
                return None, 0

            # Standalone Esc
            return KeyEvent(key="esc"), 1

        # 3. Standard ASCII / Unicode characters
        b = data[0]
        if b == 0x20:
            return KeyEvent(key="space"), 1
        if b in (0x0D, 0x0A):
            if os.name == "nt":
                try:
                    import ctypes

                    if (
                        hasattr(ctypes, "windll")
                        and hasattr(ctypes.windll, "user32")
                        and ctypes.windll.user32.GetAsyncKeyState(0x11) & 0x8000
                    ):
                        return KeyEvent(key="m", ctrl=True), 1
                except Exception:
                    pass
            return KeyEvent(key="enter"), 1
        if b in (0x08, 0x7F):
            return KeyEvent(key="backspace"), 1
        if b == 0x09:
            return KeyEvent(key="tab"), 1
        if b == 0x03:
            return KeyEvent(key="c", ctrl=True), 1
        if b == 0x11:
            return KeyEvent(key="q", ctrl=True), 1
        if b == 0x0F:
            return KeyEvent(key="o", ctrl=True), 1

        # Single or multi-byte UTF-8 character
        expected = (
            2 if 0xC2 <= b <= 0xDF else 3 if 0xE0 <= b <= 0xEF else 4 if 0xF0 <= b <= 0xF4 else 1
        )
        if len(data) < expected:
            return None, 0
        for length in (1, 2, 3, 4):
            if len(data) >= length:
                try:
                    char_str = data[:length].decode("utf-8")
                    return KeyEvent(key=char_str), length
                except UnicodeDecodeError:
                    continue
        return None, 1
