"""Standalone TUI Media Application entrypoint running in its own console window."""

from __future__ import annotations

import contextlib
import os
import sys
from pathlib import Path

from ..media.picker.sibling_seeder import SiblingPlaylistSeeder
from ..media.picker.tui_picker import TUIMediaPicker
from ..media.player.coordinator import MediaSession


def run_media_app(args: list[str] | None = None) -> None:
    """Runs the interactive Media Picker & Player in a dedicated terminal window."""
    if hasattr(sys.stdout, "reconfigure"):
        with contextlib.suppress(Exception):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        with contextlib.suppress(Exception):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    # Maximize console window on Windows for highest available resolution
    if os.name == "nt" and sys.stdin.isatty():
        try:
            import ctypes

            hwnd = ctypes.windll.kernel32.GetConsoleWindow()
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, 3)  # SW_MAXIMIZE
            else:
                os.system("mode con: cols=160 lines=50")
        except Exception:
            pass
    with contextlib.suppress(Exception):
        sys.stdout.write("\x1b[9;1t")
        sys.stdout.flush()

    raw_args = sys.argv[1:] if args is None else args
    enable_window = any(w in raw_args for w in ("--window", "--gui", "-w"))
    filtered_args = [a for a in raw_args if a not in ("--inline", "-i", "--window", "--gui", "-w")]
    target_path_str = " ".join(filtered_args).strip() if filtered_args else ""
    target_path = Path(target_path_str).resolve() if target_path_str else Path(".").resolve()

    from .media import _run_picker_loop

    curr_dir = (
        target_path
        if target_path.is_dir()
        else (target_path.parent if target_path.is_file() else Path(".").resolve())
    )
    selected_file: Path | None = target_path if target_path.is_file() else None

    while True:
        if selected_file is None:
            picker = TUIMediaPicker(start_dir=curr_dir)
            selected_file = _run_picker_loop(picker)
            if not selected_file:
                break

        curr_dir = selected_file.parent
        playlist, start_idx = SiblingPlaylistSeeder.seed_from_file(selected_file)
        session = MediaSession(
            playlist=playlist,
            initial_index=start_idx,
            enable_consent_prompt=True,
            enable_native_window=enable_window,
        )
        exit_action = session.start()

        if not sys.stdin.isatty() or exit_action == "quit_app":
            break

        # Closing media returns to showing folder in TUI
        selected_file = None


if __name__ == "__main__":
    run_media_app()
