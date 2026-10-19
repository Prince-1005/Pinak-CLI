"""CLI command handlers for /play, /view, and /media."""

from __future__ import annotations

import sys
from pathlib import Path

from rich.console import Console

from ..media.lifecycle.session_coordinator import MediaSessionCoordinator
from ..media.picker.scanner import SUPPORTED_EXTENSIONS
from ..media.picker.sibling_seeder import SiblingPlaylistSeeder
from ..media.picker.tui_picker import TUIMediaPicker
from ..media.player.coordinator import MediaSession
from ..text_safety import safe_rich

console = Console()


def handle_media_command(args: list[str], standalone: bool = False) -> None:
    """Handles the unified /media command to play video/audio, view photos, or browse media."""
    _play_or_browse(args, default_title="Pinak Media Player", standalone=standalone)


def handle_play_command(args: list[str], standalone: bool = False) -> None:
    """Legacy alias: /play is unified into /media."""
    handle_media_command(args, standalone=standalone)


def handle_view_command(args: list[str], standalone: bool = False) -> None:
    """Legacy alias: /view is unified into /media."""
    handle_media_command(args, standalone=standalone)


def launch_standalone_media_window(args: list[str], wait: bool = True) -> bool:
    """Spawns the TUI Media application in a separate independent OS console window."""
    import subprocess
    import tempfile

    from ..utils import trusted_which

    cmd = [sys.executable, "-m", "pinak.commands.media_app", *args]
    proc: subprocess.Popen | None = None
    status_dir = (
        tempfile.TemporaryDirectory(prefix="pinak-launch-")
        if wait and sys.platform == "darwin"
        else None
    )
    status_file = Path(status_dir.name) / "status" if status_dir else None
    try:
        if sys.platform.startswith("win"):
            creation_flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0x00000010)
            proc = subprocess.Popen(cmd, creationflags=creation_flags)
        elif sys.platform == "darwin":
            import shlex

            shell_cmd = " ".join(shlex.quote(part) for part in cmd)
            if status_file:
                shell_cmd += '; result=$?; printf "%s" "$result" > ' + shlex.quote(str(status_file))
            # In AppleScript double-quoted strings, backslashes and double quotes must be escaped
            escaped_script_cmd = shell_cmd.replace("\\", "\\\\").replace('"', '\\"')
            script = f'tell application "Terminal" to do script "{escaped_script_cmd}"'
            if wait:
                script = (
                    f'tell application "Terminal"\nset mediaTab to do script "{escaped_script_cmd}"\n'
                    "delay 1\nrepeat while busy of mediaTab\ndelay 0.2\nend repeat\nend tell"
                )
            proc = subprocess.Popen(["osascript", "-e", script])
        else:
            term = (
                trusted_which("x-terminal-emulator")
                or trusted_which("xterm")
                or trusted_which("gnome-terminal")
            )
            if term:
                terminal_args = (
                    ["--wait", "--", *cmd] if Path(term).name == "gnome-terminal" else ["-e", *cmd]
                )
                proc = subprocess.Popen([term, *terminal_args])

        if proc is not None:
            if wait:
                successful = proc.wait() == 0
                if status_file:
                    successful = (
                        successful
                        and status_file.is_file()
                        and status_file.read_text().strip() == "0"
                    )
                return successful
            return True
    except Exception:
        pass
    finally:
        if status_dir:
            status_dir.cleanup()
    return False


def _play_or_browse(
    args: list[str], default_title: str = "Media", standalone: bool = False
) -> None:
    # If standalone mode requested and not forced inline, launch in separate OS window
    if (standalone or "--standalone" in args) and "--inline" not in args and "-i" not in args:
        clean_launch_args = [a for a in args if a != "--standalone"]
        console.print(MediaSessionCoordinator.format_suspended_cli_banner())
        launched = launch_standalone_media_window(clean_launch_args, wait=True)
        console.print(MediaSessionCoordinator.format_return_cli_banner())
        if launched:
            return
        console.print("[yellow]Standalone launch failed; opening the player here.[/yellow]")
        args = [*clean_launch_args, "--inline"]

    enable_window = any(w in args for w in ("--window", "--gui", "-w"))
    clean_args = [a for a in args if a not in ("--inline", "-i", "--window", "--gui", "-w")]
    target_path_str = " ".join(clean_args).strip().strip("\"'") if clean_args else ""
    target_path = Path(target_path_str).resolve() if target_path_str else Path(".").resolve()

    if not target_path.exists():
        console.print(f"[red][!] Path not found:[/red] {safe_rich(target_path_str)}")
        return

    curr_dir = target_path if target_path.is_dir() else target_path.parent
    selected_file: Path | None = target_path if target_path.is_file() else None
    picker: TUIMediaPicker | None = None

    # Print CLI suspension message before entering TUI
    console.print(MediaSessionCoordinator.format_suspended_cli_banner())

    while True:
        if selected_file is None:
            if picker is None:
                picker = TUIMediaPicker(start_dir=curr_dir)
            selected_file = _run_picker_loop(picker)
            if not selected_file:
                # User pressed 'q' or 'esc' in folder browser -> exit TUI
                break

        curr_dir = selected_file.parent
        if selected_file.suffix.lower() not in SUPPORTED_EXTENSIONS:
            console.print(
                f"[yellow]Cannot open this file type:[/yellow] {safe_rich(selected_file.name)}"
            )
            if not sys.stdin.isatty():
                break
            selected_file = None
            continue
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

        # Closing media file returns to showing the folder browser in the TUI
        if picker is None:
            picker = TUIMediaPicker(start_dir=curr_dir)
        picker.focus_path(selected_file)
        selected_file = None

    # Output return message after session teardown
    console.print(MediaSessionCoordinator.format_return_cli_banner())


def _run_picker_loop(picker: TUIMediaPicker) -> Path | None:
    """Runs the interactive TUI picker loop until selection or exit."""
    import shutil
    import time
    from contextlib import closing

    if not sys.stdin.isatty():
        return None

    from ..media.core.input_parser import InputParser
    from ..media.core.lifecycle import TerminalSessionContext

    parser = InputParser()
    with closing(picker), TerminalSessionContext(enable_mouse=True):
        while True:
            cols, rows = shutil.get_terminal_size(fallback=(80, 24))
            frame_str = picker.render_tui(cols, rows)
            sys.stdout.write(f"\x1b[H{frame_str}")
            sys.stdout.flush()

            events = parser.poll_events(timeout_seconds=0.05)
            for ev in events:
                editing = (
                    picker.is_searching or picker.is_inputting_path or bool(picker.search_query)
                )
                _, confirmed = picker.handle_input(ev)
                if confirmed is not None:
                    return confirmed

                if not editing and hasattr(ev, "key") and ev.key.lower() in ("q", "esc"):
                    return None
                if hasattr(ev, "key") and ev.key == "c" and getattr(ev, "ctrl", False):
                    return None
            time.sleep(0.01)
