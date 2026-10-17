"""Cross-platform user notifications.

Windows machines with ``win11toast`` get native desktop toasts; every other
platform (and Windows without the optional dependency) falls back to a Rich
panel printed inline, so no notification is ever silently lost.

All helpers are best-effort and never raise.
"""

from __future__ import annotations

import threading

from rich.console import Console
from rich.panel import Panel

from .text_safety import safe_rich

try:  # Windows-only optional dependency.
    from win11toast import toast as _toast
except ImportError:  # pragma: no cover - platform dependent
    _toast = None

console = Console(stderr=True)


def _show_native_notification(title: str, message: str) -> bool:
    """Attempt native desktop notification on Windows, macOS, or Linux.

    Returns True if a native toast/notification was dispatched.
    """
    import shutil
    import subprocess
    import sys

    def fallback() -> None:
        console.print(
            Panel(f"[bold]{safe_rich(title)}[/]\n{safe_rich(message)}", border_style="cyan")
        )

    def deliver(cmd: list[str]) -> None:
        try:
            result = subprocess.run(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10.0, check=False
            )
            if result.returncode != 0:
                fallback()
        except (OSError, subprocess.TimeoutExpired):
            fallback()

    cmd: list[str]
    if _toast is not None and sys.platform.startswith("win"):
        # Third-party stdout and COM lifetime stay isolated from the CLI process.
        code = (
            "import sys; from win11toast import toast; "
            "toast(sys.argv[1],sys.argv[2],duration='short',"
            "on_click=lambda *a,**k:None,on_dismissed=lambda *a,**k:None,"
            "on_failed=lambda *a,**k:None)"
        )
        cmd = [sys.executable, "-c", code, title, message]
    elif sys.platform == "darwin" and shutil.which("osascript"):
        # Text is argv data, never AppleScript source.
        script = (
            "on run argv\n"
            "display notification (item 2 of argv) with title (item 1 of argv)\n"
            "end run"
        )
        cmd = ["osascript", "-e", script, title, message]
    elif (sys.platform.startswith("linux") or "bsd" in sys.platform) and shutil.which(
        "notify-send"
    ):
        cmd = ["notify-send", "--", title, message]
    else:
        return False
    threading.Thread(target=deliver, args=(cmd,), daemon=True).start()
    return True


def notify(title: str, message: str) -> None:
    """Show a desktop toast on Windows/macOS/Linux, falling back to an inline Rich panel."""
    shown = False
    try:
        shown = _show_native_notification(title, message)
    except Exception:
        shown = False

    if not shown:
        console.print(
            Panel(f"[bold]{safe_rich(title)}[/]\n{safe_rich(message)}", border_style="cyan")
        )


def print_offline_notice() -> None:
    """Warn that the device appears to be offline."""
    text = (
        "[bold red]You appear to be offline.[/]\n"
        "Downloads, update checks, and /doctor connectivity tests need internet.\n"
        "[dim]Check your Wi-Fi / VPN / firewall, then retry.[/]"
    )
    console.print(Panel(text, title="📡 Offline", border_style="red"))
    notify("Pinak — offline", "No internet connection detected.")


def print_instagram_notice(detail: str = "") -> None:
    """Explain Instagram failures: usually platform-side blocks, not app bugs."""
    text = (
        "[bold yellow]Instagram blocked or limited this request.[/]\n"
        "This is an Instagram-side restriction (login wall, rate limit, or\n"
        "private/removed content) — not a Pinak bug.\n"
        "[dim]Try again later, use a public post URL, or download via /video.[/]"
    )
    if detail:
        text += f"\n[dim]Detail: {safe_rich(detail)}[/]"
    console.print(Panel(text, title="📸 Instagram notice", border_style="yellow"))
    notify("Pinak — Instagram notice", "Instagram blocked or limited the request.")


def print_update_notice(package: str, version: str, command: str = "/update") -> None:
    """Tell the user a newer downloader engine is available."""
    text = (
        f"[bold yellow]A new version of {package} ({version}) is available![/]\n"
        f"Update the downloading engine any time with [bold]{command}[/]."
    )
    console.print(Panel(text, title="🔄 Update available", border_style="yellow"))
    notify(f"Pinak — {package} update", f"Version {version} is available.")
