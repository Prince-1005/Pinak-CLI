"""Uninstallation workflows: detect installer, purge local configs, and remove package."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm

from .config import config_dir
from .history import LEGACY_DB_FILE, data_dir
from .logging_setup import get_logger

log = get_logger("pinak.uninstall")
console = Console()
legacy_db_file = LEGACY_DB_FILE
command_history_file = os.path.expanduser("~/.pinak_cli_history")


def _purge_targets(include_cache: bool = True) -> list[str]:
    targets = [config_dir, data_dir, legacy_db_file, command_history_file]
    if include_cache:
        import platformdirs

        targets.append(platformdirs.user_cache_dir("pinak-cli", "pinak"))
    safe = []
    for target in targets:
        if not target:
            continue
        path = Path(target).absolute()
        resolved = path.resolve()
        if resolved in (Path(resolved.anchor), Path.home().resolve(), Path.cwd().resolve()):
            log.warning("Refusing unsafe purge target: %s", target)
            continue
        if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
            log.warning("Retaining linked data directory: %s", target)
            continue
        safe.append(str(resolved))
    return list(dict.fromkeys(safe))


def detect_uninstall_cmd() -> list[str]:
    """Detect how pinak-cli was installed and return the corresponding uninstallation command."""
    # 1. Check if uv is installed and pinak-cli is registered in uv tools
    if shutil.which("uv"):
        try:
            res = subprocess.run(  # nosec B603, B607
                ["uv", "tool", "list"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
            )
            if res.returncode == 0 and "pinak-cli" in res.stdout:
                return ["uv", "tool", "uninstall", "pinak-cli"]
        except Exception as exc:
            log.debug("uv detection failed: %r", exc)

    # 2. Check if pipx is installed and manages pinak-cli
    if shutil.which("pipx"):
        try:
            res = subprocess.run(  # nosec B603, B607
                ["pipx", "list", "--short"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
            )
            if res.returncode == 0 and "pinak-cli" in res.stdout:
                return ["pipx", "uninstall", "pinak-cli"]
        except Exception as exc:
            log.debug("pipx detection failed: %r", exc)

    # 3. Fallback to standard pip uninstallation
    return [sys.executable, "-m", "pip", "uninstall", "-y", "pinak-cli"]


def purge_user_data(include_cache: bool = True) -> list[str]:
    """Remove user configuration, history database, and local cache directories.

    Returns the list of paths that were removed.
    """
    removed: list[str] = []
    # Collect standard config and data directories
    targets = _purge_targets(include_cache)

    for target in targets:
        if target and os.path.exists(target):
            try:
                if os.path.isdir(target):
                    shutil.rmtree(target)
                else:
                    os.remove(target)
                if not os.path.exists(target):
                    removed.append(target)
            except Exception as exc:
                log.warning("Failed to purge %s: %r", target, exc)

    return removed


def _format_powershell_cmd(cmd: list[str]) -> str:
    """Safely formats a command list for PowerShell invocation, handling spaces in paths."""
    if not cmd:
        return ""
    quoted = ["'" + arg.replace("'", "''") + "'" for arg in cmd]
    return f"& {quoted[0]} " + " ".join(quoted[1:])


def execute_uninstallation(
    cmd: list[str], detached: bool = True, *, purge_after: bool = False
) -> bool:
    """Execute the package uninstallation command.

    On Windows, uses a detached process with a delay to avoid file lock conflicts.
    """
    cmd_str = " ".join(cmd)
    log.info("Executing uninstallation command: %s", cmd_str)

    if sys.platform.startswith("win") and detached:
        # On Windows, running binaries/DLLs are locked while in use.
        # Launch a detached PowerShell process that pauses briefly to let pinak exit, then uninstalls.
        # Using the PowerShell call operator (&) with quoted executable path prevents failures when
        # Python paths contain spaces (e.g. 'C:\Program Files\Python311\python.exe').
        ps_cmd = _format_powershell_cmd(cmd)
        powershell_script = f"Start-Sleep -Seconds 1; {ps_cmd}"
        if purge_after:
            cleanup = []
            for target in _purge_targets():
                literal = "'" + target.replace("'", "''") + "'"
                cleanup.append(
                    f"if (Test-Path -LiteralPath {literal}) {{ Remove-Item -LiteralPath {literal} -Recurse -Force -ErrorAction Stop }}"
                )
            powershell_script += "; if ($LASTEXITCODE -eq 0) { " + "; ".join(cleanup) + " }"
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(
            subprocess, "DETACHED_PROCESS", 0
        )
        try:
            subprocess.Popen(  # nosec B603, B607
                ["powershell", "-NoProfile", "-Command", powershell_script],
                creationflags=flags,
                close_fds=True,
            )
            return True
        except Exception as exc:
            log.warning("Detached process launch failed (%r); falling back to direct run", exc)

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )  # nosec B603
        if proc.returncode != 0:
            return False
        if purge_after:
            purge_user_data()
        return True
    except Exception as exc:
        log.error("Failed to run uninstall command %r: %r", cmd, exc)
        return False


def run_uninstall(yes: bool = False, purge_data: bool = True) -> int:
    """Interactive uninstallation workflow with confirmation, emojis, and cleanup."""
    panel_content = (
        "[bold red]⚠️  UNINSTALL PINAK CLI ⚠️[/bold red]\n\n"
        "Are you sure you want to completely uninstall [bold cyan]Pinak CLI[/bold cyan] from your system? 🥺💔\n\n"
        "This will completely remove:\n"
        "  🗑️  The [bold]pinak[/bold] executable and all package files\n"
        "  📁  Saved configurations and preferences\n"
        "  📜  Download history database\n\n"
        "[bold green]🛡️  Note: Your downloaded media files (videos, audios, images) will NOT be deleted.[/bold green]"
    )
    console.print(Panel(panel_content, border_style="red", expand=False))

    if not yes:
        try:
            confirmed = Confirm.ask(
                "[bold yellow]❓ Do you really want to completely uninstall Pinak CLI?[/bold yellow]",
                default=False,
            )
        except (KeyboardInterrupt, EOFError):
            confirmed = False

        if not confirmed:
            console.print(
                "\n[bold green]✨ Uninstallation canceled! Pinak is glad to stay with you! 🚀🎉[/bold green]\n"
            )
            return 0

    cmd = detect_uninstall_cmd()
    console.print(
        f"[yellow]📦 Triggering package removal ([bold]{' '.join(cmd)}[/bold])...[/yellow]"
    )

    success = execute_uninstallation(cmd, detached=True, purge_after=purge_data)
    if success:
        if purge_data:
            console.print(
                "[dim]Configuration/history cleanup runs only after successful package removal. Downloaded media is retained.[/dim]"
            )
        from .config import config

        if config.get("log_file"):
            console.print(
                "[dim]External log files are retained; remove them explicitly if desired.[/dim]"
            )
        console.print(
            "\n[bold cyan]👋 Pinak has been scheduled for removal. Thank you for using Pinak! See you again! 🌸✨[/bold cyan]\n"
        )
        return 0

    console.print(
        f"\n[bold red]❌ Automated removal could not start. You can uninstall manually by running:[/bold red]\n"
        f"   [bold yellow]{' '.join(cmd)}[/bold yellow]\n"
    )
    return 1
