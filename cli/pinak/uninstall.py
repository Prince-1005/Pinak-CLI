"""Uninstallation workflows: detect installer, purge local configs, and remove package."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm

from .config import config_dir
from .history import LEGACY_DB_FILE, data_dir
from .logging_setup import get_logger

log = get_logger("pinak.uninstall")
console = Console()
legacy_db_file = LEGACY_DB_FILE


def detect_uninstall_cmd() -> list[str]:
    """Detect how pinak-cli was installed and return the corresponding uninstallation command."""
    # 1. Check if uv is installed and pinak-cli is registered in uv tools
    if shutil.which("uv"):
        try:
            res = subprocess.run(  # nosec B603, B607
                ["uv", "tool", "list"],
                capture_output=True,
                text=True,
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
    targets = [config_dir, data_dir]

    if include_cache:
        import platformdirs

        cache_dir = platformdirs.user_cache_dir("pinak-cli", "pinak")
        targets.append(cache_dir)

    for target in targets:
        if target and os.path.exists(target):
            try:
                shutil.rmtree(target, ignore_errors=True)
                removed.append(target)
            except Exception as exc:
                log.debug("Failed to purge %s: %r", target, exc)

    # Also clean legacy ~/.pinak_history.db if present
    if legacy_db_file and os.path.exists(legacy_db_file):
        try:
            os.remove(legacy_db_file)
            removed.append(legacy_db_file)
        except Exception as exc:
            log.debug("Failed to remove legacy db: %r", exc)

    return removed


def execute_uninstallation(cmd: list[str], detached: bool = True) -> bool:
    """Execute the package uninstallation command.

    On Windows, uses a detached process with a delay to avoid file lock conflicts.
    """
    cmd_str = " ".join(cmd)
    log.info("Executing uninstallation command: %s", cmd_str)

    if sys.platform.startswith("win") and detached:
        # On Windows, running binaries/DLLs are locked while in use.
        # Launch a detached PowerShell process that pauses briefly to let pinak exit, then uninstalls.
        powershell_script = f"Start-Sleep -Seconds 1; {cmd_str}"
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
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)  # nosec B603
        return proc.returncode == 0
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

    if purge_data:
        console.print("[yellow]🧹 Cleaning configuration settings and history database...[/yellow]")
        purged = purge_user_data(include_cache=True)
        if purged:
            console.print("[green]✅ Configuration and history database removed![/green]")
        else:
            console.print("[dim]No configuration files needed removal.[/dim]")

    cmd = detect_uninstall_cmd()
    console.print(
        f"[yellow]📦 Triggering package removal ([bold]{' '.join(cmd)}[/bold])...[/yellow]"
    )

    success = execute_uninstallation(cmd, detached=True)
    if success:
        console.print(
            "\n[bold cyan]👋 Pinak has been scheduled for removal. Thank you for using Pinak! See you again! 🌸✨[/bold cyan]\n"
        )
        return 0

    console.print(
        f"\n[bold red]❌ Automated removal could not start. You can uninstall manually by running:[/bold red]\n"
        f"   [bold yellow]{' '.join(cmd)}[/bold yellow]\n"
    )
    return 1
