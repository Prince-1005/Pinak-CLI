"""High-precision rendering scheduler and event loop."""

from __future__ import annotations

import sys
import time
from collections.abc import Callable

from .input_parser import InputEvent, InputParser


class PrecisionEventLoop:
    """Coordinates high-frame-rate rendering, input dispatching, and atomic frame synchronization."""

    def __init__(
        self,
        target_fps: float = 60.0,
        enable_sync_updates: bool = True,
    ) -> None:
        self.target_fps = max(1.0, min(120.0, target_fps))
        self.frame_interval = 1.0 / self.target_fps
        self.enable_sync_updates = enable_sync_updates
        self.is_running = False
        self.input_parser = InputParser()
        self._last_frame_time = 0.0
        self.last_flush_duration = 0.0

    def stop(self) -> None:
        """Signals the event loop to terminate."""
        self.is_running = False

    def run(
        self,
        on_tick: Callable[[float, list[InputEvent]], str | None],
    ) -> None:
        """
        Executes the main render and input loop.
        on_tick signature: (delta_time, events) -> frame_content_str (or None if no render needed)
        """
        self.is_running = True
        self._last_frame_time = time.perf_counter()

        while self.is_running:
            frame_start = time.perf_counter()
            dt = max(0.0001, frame_start - self._last_frame_time)
            self._last_frame_time = frame_start

            # 1. Non-blocking input interrogation
            events = self.input_parser.poll_events(timeout_seconds=0.0)

            # 2. Frame tick callback
            frame_output = on_tick(dt, events)

            # 3. Synchronized atomic terminal flush
            if frame_output is not None:
                self.flush_frame(frame_output)

            # 4. Sleep remainder of frame budget
            elapsed = time.perf_counter() - frame_start
            sleep_time = self.frame_interval - elapsed
            if sleep_time > 0.001:
                time.sleep(sleep_time)

    def flush_frame(self, content: str) -> None:
        """Emits content to stdout bounded by synchronized update escape codes."""
        out = []
        if self.enable_sync_updates:
            out.append("\x1b[?2026h")  # Begin synchronized update

        out.append("\x1b[H")  # Move cursor to home (top-left)
        out.append(content)
        out.append(
            "\x1b[J"
        )  # Clear from cursor to end of screen (prevents duplicate footer on resize)

        if self.enable_sync_updates:
            out.append("\x1b[?2026l")  # End synchronized update

        started = time.perf_counter()
        try:
            sys.stdout.write("".join(out))
            sys.stdout.flush()
        except (OSError, ValueError):
            self.stop()
        finally:
            self.last_flush_duration = time.perf_counter() - started
