"""Informational REPL commands: config/stats/platforms/help/history/open."""

from __future__ import annotations

import datetime
import os
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ..config import config
from ..history import get_history, get_stats_data
from ..subtitle_preferences import MAX_SUBTITLE_LANGUAGES
from ..text_safety import safe_rich, safe_text
from ..utils import BOLD, GREEN, RED, RESET, YELLOW

console = Console()


def open_output_folder() -> None:
    output_dir = config.get("output_dir", "downloads")
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.abspath(output_dir)
    try:
        import shutil
        import subprocess
        import webbrowser

        opened = False
        if sys.platform.startswith("win"):
            if hasattr(os, "startfile"):
                try:
                    os.startfile(path)
                    opened = True
                except Exception:
                    pass
            if not opened and shutil.which("explorer"):
                try:
                    subprocess.run(["explorer", path], check=False)  # nosec B603, B607
                    opened = True
                except Exception:
                    pass
        elif sys.platform == "darwin" and shutil.which("open"):
            try:
                subprocess.run(["open", path], check=False)  # nosec B603, B607
                opened = True
            except Exception:
                pass
        elif shutil.which("xdg-open"):
            try:
                subprocess.run(["xdg-open", path], check=False)  # nosec B603, B607
                opened = True
            except Exception:
                pass

        if not opened:
            try:
                opened = bool(webbrowser.open(Path(path).as_uri()))
            except Exception:
                opened = False

        if opened:
            print(f"{GREEN}[+] Opened: {path}{RESET}")
        else:
            print(f"{YELLOW}[!] Could not automatically open folder: {path}{RESET}")
    except Exception as e:
        print(f"{RED}[X] Could not open folder: {e}{RESET}")


def print_help() -> None:
    table = Table(title="Available Commands", style="cyan")
    table.add_column("Command", style="cyan")
    table.add_column("Description", style="white")

    help_items = [
        ("/help", "Show this help menu"),
        ("/doctor", "Check Python, yt-dlp, FFmpeg, internet, and output folder"),
        ("/config", "Show saved preferences"),
        ("/stats", "Show download analytics and insights"),
        ("/setout <dir>", "Change and save the output downloads directory"),
        ("/open", "Open the current output folder"),
        (
            "/history [filter]",
            "View history; filters: failed, audio, media, search <text>",
        ),
        ("/queue <action>", "Manage downloads: add, import, list, run, retry; /queue help"),
        ("/clear", "Clear the screen; keep the Pinak logo and control panel"),
        (
            "/any <url>",
            "Download content from any platform supported by yt-dlp",
        ),
        (
            "/instagram <url>",
            "Download post, reel, igtv from Instagram with description & metadata",
        ),
        ("/video <url>", "Download video from a URL"),
        ("/audio <url>", "Download video/song directly as MP3"),
        (
            "/video_quality [value]",
            "Set video quality (interactive if value is omitted)",
        ),
        (
            "/audio_quality [value]",
            "Set audio quality in kbps (interactive if value is omitted)",
        ),
        (
            "/video_format [value]",
            "Set video format (e.g. mp4, mkv) (interactive if value is omitted)",
        ),
        (
            "/audio_format [value]",
            "Set audio format (e.g. mp3, m4a) (interactive if value is omitted)",
        ),
        ("/platform [search]", "List or search supported platforms"),
        ("/trim <start>-<end>", "Trim video/audio (e.g. /trim 01:15-02:30 <url>)"),
        ("/subs [on|off]", "Enable/disable subtitle downloads (no argument toggles)"),
        (
            "/subs_lang [codes|list]",
            f"Choose and save 1–{MAX_SUBTITLE_LANGUAGES} subtitle languages (e.g. en hi es)",
        ),
        ("/sort", "Toggle auto-sorting into platform directories"),
        ("/username [name]", "Change and save your username"),
        ("/greeting [text]", "Change and save your greeting statement"),
        (
            "/delete_his <target>",
            "Delete history: all, index (e.g. 3), or range (e.g. 2-4)",
        ),
        ("/update", "Update yt-dlp and Pinak itself to the latest versions"),
        ("/ffmpeg", "Download a static FFmpeg build automatically"),
        ("/media [path]", "Launch interactive TUI media player & browser (videos, music, photos)"),
        ("/reset", "Reset terminal console mode, buffer, and cursor if frozen"),
        ("/uninstall", "Completely remove Pinak CLI and its data from your system"),
        ("/exit, exit, quit", "Exit the CLI safely"),
    ]

    for cmd_str, desc in sorted(help_items, key=lambda x: x[0]):
        table.add_row(cmd_str, desc)

    console.print(table)

    output_dir = config.get("output_dir", "downloads")
    tips = f"""[bold]Download Tips:[/]
  - Paste any media URL directly to start downloading.
  - Append [yellow]--force[/] to re-download a URL already in your history.
  - Current output: [yellow]{output_dir}[/]
  - Current quality: [yellow]{config.get("quality", "best")}[/]
  - Legal: only download content you own or are allowed to save (see README).
"""
    console.print(Panel(tips, border_style="cyan"))


def show_config() -> None:
    from rich import box

    from ..config import CONFIG_FILE

    console.print(f"[dim]Config file: {safe_rich(os.path.abspath(CONFIG_FILE))}[/dim]")
    console.print("[dim]Tip: run [bold]pinak --config-path[/] anywhere to print this path.[/dim]")

    table = Table(
        title="[bold yellow]🔱 System Configuration 🔱[/bold yellow]",
        style="cyan",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Setting Key", style="bold cyan")
    table.add_column("Current Configured Value", style="bold magenta")

    setting_names = {
        "username": "Username",
        "greeting": "Greeting Text",
        "output_dir": "Output Directory",
        "quality": "Video Quality",
        "audio_quality": "Audio Quality",
        "video_format": "Video Format",
        "audio_format": "Audio Format",
        "embed_subs": "Embed Subtitles",
        "subtitle_languages": f"Subtitle Languages (maximum {MAX_SUBTITLE_LANGUAGES})",
        "auto_sort": "Auto Sort Platform",
        "retry_count": "Retry Count",
        "connect_timeout": "Connect Timeout (s)",
        "read_timeout": "Read Timeout (s)",
    }

    for key in sorted(config):
        label = setting_names.get(key, key.replace("_", " ").title())
        val = safe_rich(config[key])
        if val.lower() == "true":
            val_formatted = "[bold green]Enabled (True)[/bold green]"
        elif val.lower() == "false":
            val_formatted = "[bold red]Disabled (False)[/bold red]"
        else:
            val_formatted = f"[white]{val}[/white]"
        table.add_row(label, val_formatted)

    console.print(table)


def show_history_rendered(filter_text: str = "") -> None:
    downloads = get_history(filter_text)
    if not downloads:
        console.print("[yellow][!] No history matches your filter.[/]")
        return

    # Show newest downloads first
    downloads = downloads[::-1]

    viewport_size = 10
    total = len(downloads)

    # State tracking: selected_idx and scroll_offset
    selected_idx = [0]
    scroll_offset = [0]

    import io

    from prompt_toolkit.application import Application
    from prompt_toolkit.formatted_text import ANSI
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import Layout
    from prompt_toolkit.layout.containers import HSplit, Window
    from prompt_toolkit.layout.controls import FormattedTextControl

    def get_rendered_page(offset_val, selected_val):
        start = offset_val
        end = min(start + viewport_size, total)
        page_items = downloads[start:end]

        # Calculate scrollbar track & thumb position
        visible_count = end - start
        if total <= visible_count:
            scrollbar_chars = ["█"] * visible_count
        else:
            thumb_size = max(1, int(visible_count * (visible_count / total)))
            scroll_ratio = offset_val / (total - visible_count)
            thumb_start = int(scroll_ratio * (visible_count - thumb_size))
            thumb_start = max(0, min(thumb_start, visible_count - thumb_size))

            scrollbar_chars = []
            for i in range(visible_count):
                if thumb_start <= i < thumb_start + thumb_size:
                    scrollbar_chars.append("█")
                else:
                    scrollbar_chars.append("░")

        table = Table(
            title=f"Downloads History (Selected: {selected_val + 1} of {total})",
            style="blue",
            show_header=True,
            header_style="bold cyan",
        )
        table.add_column("S.No.", justify="right", width=6)
        table.add_column("Date", style="cyan", width=20)
        table.add_column("Status", justify="center", width=12)
        table.add_column("Mode", style="magenta", width=10)
        table.add_column("Quality", style="magenta", width=10)
        table.add_column("URL", style="blue")
        table.add_column(" ", justify="center", width=1)  # Scrollbar column!

        for i, d in enumerate(page_items):
            absolute_idx = start + i
            is_selected = absolute_idx == selected_val

            dt = datetime.datetime.fromtimestamp(d["time"]).strftime("%Y-%m-%d %H:%M:%S")
            url = safe_rich(d.get("url", "Unknown URL"))
            status = safe_rich(d.get("status", "unknown"))
            mode = safe_rich(d.get("mode", "media"))
            quality = safe_rich(d.get("quality", "best"))

            status_text = (
                "[green]SUCCESS[/]" if status == "success" else f"[red]{status.upper()}[/]"
            )

            s_no_str = str(absolute_idx + 1)
            row_style = "reverse" if is_selected else None

            table.add_row(
                s_no_str,
                dt,
                status_text,
                mode,
                quality,
                url,
                scrollbar_chars[i],
                style=row_style,
            )

        buf = io.StringIO()
        temp_console = Console(file=buf, color_system="truecolor", force_terminal=True)
        temp_console.print(table)
        temp_console.print()
        temp_console.print("  [yellow]Use [bold]Up/Down[/] arrow keys to scroll log entries.[/]")
        temp_console.print(
            "  [yellow]Use [bold]Left/Right[/] arrow keys to scroll by 10 entries.[/]"
        )
        temp_console.print("  [yellow]Press [bold]ESC[/] or [bold]q[/] to exit history view.[/]")
        return buf.getvalue()

    # If it is interactive, use prompt_toolkit Application to handle arrow keys and escape
    try:
        initial_text = get_rendered_page(0, 0)
        content_control = FormattedTextControl(text=ANSI(initial_text))

        kb = KeyBindings()

        @kb.add("up")
        def _(event):
            if selected_idx[0] > 0:
                selected_idx[0] -= 1
                if selected_idx[0] < scroll_offset[0]:
                    scroll_offset[0] = selected_idx[0]
                content_control.text = ANSI(get_rendered_page(scroll_offset[0], selected_idx[0]))

        @kb.add("down")
        def _(event):
            if selected_idx[0] < total - 1:
                selected_idx[0] += 1
                if selected_idx[0] >= scroll_offset[0] + viewport_size:
                    scroll_offset[0] = selected_idx[0] - viewport_size + 1
                content_control.text = ANSI(get_rendered_page(scroll_offset[0], selected_idx[0]))

        @kb.add("left")
        def _(event):
            if selected_idx[0] > 0:
                selected_idx[0] = max(0, selected_idx[0] - 10)
                if selected_idx[0] < scroll_offset[0]:
                    scroll_offset[0] = selected_idx[0]
                content_control.text = ANSI(get_rendered_page(scroll_offset[0], selected_idx[0]))

        @kb.add("right")
        def _(event):
            if selected_idx[0] < total - 1:
                selected_idx[0] = min(total - 1, selected_idx[0] + 10)
                if selected_idx[0] >= scroll_offset[0] + viewport_size:
                    scroll_offset[0] = selected_idx[0] - viewport_size + 1
                content_control.text = ANSI(get_rendered_page(scroll_offset[0], selected_idx[0]))

        @kb.add("escape")
        @kb.add("q")
        def _(event):
            event.app.exit()

        layout = Layout(HSplit([Window(content=content_control)]))
        app = Application(layout=layout, key_bindings=kb, full_screen=False, mouse_support=False)
        app.run()
    except Exception:
        # Non-interactive fallback: print all rows
        fallback_console = Console()
        fallback_console.print(
            "[yellow][!] Non-interactive fallback: showing all history records.[/]"
        )
        table = Table(title="Downloads History (All Records)", style="blue")
        table.add_column("S.No.", justify="right", width=6)
        table.add_column("Date", style="cyan")
        table.add_column("Status", justify="center")
        table.add_column("Mode", style="magenta")
        table.add_column("Quality", style="magenta")
        table.add_column("URL", style="blue")

        for idx, d in enumerate(downloads):
            dt = datetime.datetime.fromtimestamp(d["time"]).strftime("%Y-%m-%d %H:%M:%S")
            url = safe_rich(d.get("url", "Unknown URL"))
            status = safe_rich(d.get("status", "unknown"))
            mode = safe_rich(d.get("mode", "media"))
            quality = safe_rich(d.get("quality", "best"))

            status_text = (
                "[green]SUCCESS[/]" if status == "success" else f"[red]{status.upper()}[/]"
            )
            table.add_row(str(idx + 1), dt, status_text, mode, quality, url)

        fallback_console.print(table)


def show_platforms(search_term: str = "") -> None:
    try:
        import yt_dlp

        extractors = yt_dlp.extractor.gen_extractors()
        platforms = sorted(
            {ie.IE_NAME.split(":")[0].capitalize() for ie in extractors if ie.IE_NAME != "generic"}
        )
        if search_term:
            platforms = [p for p in platforms if search_term.lower() in p.lower()]
            if not platforms:
                print(f"{YELLOW}[!] No platforms found matching '{safe_text(search_term)}'.{RESET}")
                return
            print(f"\n{BOLD}--- Matching Supported Platforms ({len(platforms)}) ---{RESET}")
        else:
            print(f"\n{BOLD}--- All Supported Platforms ({len(platforms)}) ---{RESET}")

        import shutil

        cols = shutil.get_terminal_size().columns
        col_width = 20
        num_cols = max(1, cols // col_width)
        for i in range(0, len(platforms), num_cols):
            row = platforms[i : i + num_cols]
            print("".join(p.ljust(col_width) for p in row))
        print()

        notice_text = (
            "[yellow][!] Notice:[/yellow] Our system supports downloading content from a wide variety of platforms using your source links. "
            "However, some links may not work yet due to missing integrations (please test them to confirm). "
            "Additional platforms will be added in the future based on user requests. "
            "For more information or feature requests, please contact the developer, [bold cyan]MR. PENGUIN[/bold cyan]."
        )
        console.print(notice_text)
        console.print()
    except Exception as e:
        print(f"{RED}[X] Error fetching platforms: {e}{RESET}")


def show_stats() -> None:
    stats = get_stats_data()
    if not stats:
        console.print("[yellow][!] No stats available yet. Start downloading to see statistics![/]")
        return

    from rich import box

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Stat", style="cyan", justify="right")
    table.add_column("Value", style="magenta")

    rate = stats["success_rate"]
    bar_width = 10
    filled = round((rate / 100.0) * bar_width)
    bar_str = f"[{'█' * filled}{'░' * (bar_width - filled)}]"
    if rate >= 80:
        bar_formatted = f"[bold green]{bar_str}[/bold green]"
    elif rate >= 50:
        bar_formatted = f"[bold yellow]{bar_str}[/bold yellow]"
    else:
        bar_formatted = f"[bold red]{bar_str}[/bold red]"

    table.add_row("📊 Total Attempts:", str(stats["total_attempts"]))
    table.add_row("✅ Successful Runs:", f"[bold green]{stats['successes']}[/bold green]")
    table.add_row("📈 Success Rate:", f"{bar_formatted} [bold white]{rate:.1f}%[/bold white]")
    table.add_row("💾 Total Downloaded:", stats["total_size_str"])
    table.add_row("⏱️ Media Duration:", stats["total_duration_str"])
    table.add_row("⚡ Buffer Saved:", stats["buffer_saved_str"])
    table.add_row("🏆 Top Platform:", stats["top_platform"])

    panel = Panel(
        table,
        title="[bold yellow]🔱 Data Analytics & Insights 📊[/bold yellow]",
        border_style="cyan",
        box=box.ROUNDED,
        expand=False,
    )
    console.print(panel)
    console.print()
