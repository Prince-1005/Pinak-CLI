"""Welcome/exit banners and greeting helpers for the Pinak REPL."""

# ruff: noqa: W291  # ASCII banner intentionally contains trailing spaces.

from __future__ import annotations

import shutil

from rich.console import Console
from rich.panel import Panel

from ..config import config
from ..utils import CYAN, RESET

console = Console()


def get_greeting_message() -> str:
    username = config.get("username", "").strip()
    greeting = config.get("greeting", "Har Har Mahadev 🔱").strip()
    return f"{greeting}, {username}"


def print_banner() -> None:
    banner = r"""
[cyan]  ____ ___ _   _    _    _  __
 |  _ \_ _| \ | |  / \  | |/ /
 | |_) | ||  \| | / ^ \ | ' / 
 |  __/| || |\  |/ ___ \| . \ 
 |_|  |___|_| \_/_/   \_\_|\_\
[/]
       [yellow bold]([/]
      [yellow bold]/ \ [/]
     [yellow bold]/   )[/]
 [cyan]>>==[/][yellow bold]|[/][cyan]=======>[/]
     [yellow bold]\   )[/]
      [yellow bold]\ /[/]
       [yellow bold])[/]
"""
    from rich import box

    panel = Panel.fit(
        banner,
        title="[bold yellow]PINAK-CLI 🔱[/]",
        subtitle="[bold cyan]Your Content Downloader[/]",
        border_style="cyan",
        box=box.DOUBLE,
    )
    console.print(panel)


def print_exit_screen(interrupted: bool = False) -> None:
    greeting_msg = get_greeting_message()
    from rich import box
    from rich.panel import Panel

    status_text = "Session Interrupted" if interrupted else "Session Ended"
    status_style = "bold red" if interrupted else "bold green"
    icon = "⚠️" if interrupted else "👋"

    exit_text = (
        f"\n  [bold cyan]Thank you for using Pinak-CLI![/bold cyan]\n"
        f"  [bold yellow]{greeting_msg}[/bold yellow]\n\n"
        f"  [dim white]All configuration files and download databases have been saved.[/]\n"
    )

    panel = Panel(
        exit_text,
        title=f"[{status_style}]{icon} {status_text}[/]",
        border_style="cyan",
        box=box.ROUNDED,
        expand=False,
    )
    console.print(panel)


def print_separator() -> None:
    try:
        cols = shutil.get_terminal_size().columns
    except Exception:
        cols = 80
    print(f"{CYAN}{'─' * cols}{RESET}")


def print_welcome_screen() -> None:
    greeting_msg = get_greeting_message()
    output_dir = config.get("output_dir", "downloads")
    quality = config.get("quality", "best")
    audio_quality = config.get("audio_quality", "192")
    embed_subs = "Enabled" if config.get("embed_subs", False) else "Disabled"
    auto_sort = "Enabled" if config.get("auto_sort", False) else "Disabled"

    # Rate limits have been removed as per user request.

    welcome_text = (
        f"[bold green]🔱 {greeting_msg}[/bold green]\n\n"
        f"  📂 [cyan]Output Dir :[/cyan] [magenta]{output_dir}[/magenta]\n"
        f"  🎬 [cyan]Video Qual :[/cyan] [magenta]{quality}[/magenta]  |  🎵 [cyan]Audio Qual :[/cyan] [magenta]{audio_quality} kbps[/magenta]\n"
        f"  💬 [cyan]Subtitles  :[/cyan] [magenta]{embed_subs}[/magenta]  |  🗂️  [cyan]Auto-Sort  :[/cyan] [magenta]{auto_sort}[/magenta]\n\n"
        f"[dim white]Type any media URL directly to download, or type [bold yellow]/help[/] for commands.[/]"
    )
    console.print(
        Panel(
            welcome_text,
            title="[bold yellow]PINAK CONTROL PANEL[/]",
            border_style="cyan",
            expand=False,
        )
    )
    console.print()


def clear_screen() -> None:
    """Clear terminal output and redraw the current session header."""
    console.clear(home=True)
    print_banner()
    print_welcome_screen()
