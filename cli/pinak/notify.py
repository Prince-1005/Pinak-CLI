"""Cross-platform user notifications.

Windows machines with ``win11toast`` get native desktop toasts; every other
platform (and Windows without the optional dependency) falls back to a Rich
panel printed inline, so no notification is ever silently lost.

All helpers are best-effort and never raise.
"""

from __future__ import annotations

import contextlib
import io
import threading

from rich.console import Console
from rich.panel import Panel

try:  # Windows-only optional dependency.
    from win11toast import toast as _toast
except ImportError:  # pragma: no cover - platform dependent
    _toast = None

console = Console()


def _show_native_notification(title: str, message: str) -> bool:
    """Attempt native desktop notification on Windows, macOS, or Linux.

    Returns True if a native toast/notification was dispatched.
    """
    import shutil
    import subprocess
    import sys

    # Tier 1: Windows win11toast
    if sys.platform.startswith("win") and _toast is not None:

        def _show_win() -> None:
            with (
                contextlib.suppress(BaseException),
                contextlib.redirect_stdout(io.StringIO()),
                contextlib.redirect_stderr(io.StringIO()),
            ):
                _toast(
                    title,
                    message,
                    duration="short",
                    on_click=lambda *a, **k: None,
                    on_dismissed=lambda *a, **k: None,
                    on_failed=lambda *a, **k: None,
                )

        threading.Thread(target=_show_win, daemon=True).start()
        return True

    # Tier 2: macOS osascript
    if sys.platform == "darwin" and shutil.which("osascript"):

        def _show_mac() -> None:
            with contextlib.suppress(Exception):
                safe_title = title.replace('"', '\\"')
                safe_msg = message.replace('"', '\\"')
                cmd = [
                    "osascript",
                    "-e",
                    f'display notification "{safe_msg}" with title "{safe_title}"',
                ]
                subprocess.run(cmd, capture_output=True, timeout=5.0)  # nosec B603

        threading.Thread(target=_show_mac, daemon=True).start()
        return True

    # Tier 3: Linux notify-send
    if (sys.platform.startswith("linux") or "bsd" in sys.platform) and shutil.which("notify-send"):

        def _show_linux() -> None:
            with contextlib.suppress(Exception):
                subprocess.run(
                    ["notify-send", title, message], capture_output=True, timeout=5.0
                )  # nosec B603, B607

        threading.Thread(target=_show_linux, daemon=True).start()
        return True

    return False


def notify(title: str, message: str) -> None:
    """Show a desktop toast on Windows/macOS/Linux, falling back to an inline Rich panel."""
    shown = False
    try:
        shown = _show_native_notification(title, message)
    except Exception:
        shown = False

    if not shown:
        console.print(Panel(f"[bold]{title}[/]\n{message}", border_style="cyan"))


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
        text += f"\n[dim]Detail: {detail}[/]"
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
