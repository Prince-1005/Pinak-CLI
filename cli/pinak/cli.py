import os
import re
import sys

# Configure UTF-8 encoding for stdout/stderr to prevent emoji rendering errors on Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except:
        pass

import shutil
import typer
from typing import Optional
import datetime
import questionary
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import FileHistory
from prompt_toolkit.styles import Style
from prompt_toolkit.key_binding import KeyBindings

from .config import config, init_config, save_config, CONFIG_FILE
from .history import (
    init_db, get_history, get_stats_data, check_rate_limit,
    clear_all_history, delete_history_by_ids, get_history_ids_desc,
    initialize_session, push_session_start, push_command_event
)
from .doctor import run_doctor
from .downloader import handle_download, parse_download_text, is_downloading
from . import updater
from .utils import (
    script_dir, get_clipboard_text, normalize_quality,
    get_platform, human_duration, human_size,
    CYAN, GREEN, YELLOW, RED, RESET, BOLD
)

console = Console()

from prompt_toolkit.keys import Keys

def ask_with_esc(q):
    """Wrapper to allow Esc key to cancel questionary prompts."""
    try:
        @q.application.key_bindings.add(Keys.Escape, eager=True)
        def _(event):
            event.app.exit(result=None)
    except AttributeError:
        from prompt_toolkit.key_binding import merge_key_bindings, KeyBindings
        kb = KeyBindings()
        @kb.add(Keys.Escape, eager=True)
        def _(event):
            event.app.exit(result=None)
        q.application.key_bindings = merge_key_bindings([q.application.key_bindings, kb])
    
    # Catch internal KeyboardInterrupt from Ctrl+C to avoid redundant messages
    try:
        return q.ask(kbi_msg="")
    except TypeError:
        # Fallback if kbi_msg is not supported in the user's questionary version
        return q.ask()

def print_separator():
    try:
        cols = shutil.get_terminal_size().columns
    except Exception:
        cols = 80
    print(f"{CYAN}{'─' * cols}{RESET}")

def print_banner():
    banner = fr"""
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
        box=box.DOUBLE
    )
    console.print(panel)

def show_config():
    from rich import box
    table = Table(
        title="[bold yellow]🔱 System Configuration 🔱[/bold yellow]",
        style="cyan",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan"
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
        "auto_sort": "Auto Sort Platform",
        "rate_limit_hours": "Rate Limit (Hours)",
        "rate_limit_count": "Rate Limit (Count)",
        "force_rate_limit_count": "Force Limit Max",
        "retry_count": "Retry Count",
    }

    for key in sorted(config):
        label = setting_names.get(key, key.replace("_", " ").title())
        val = str(config[key])
        if val.lower() == "true":
            val_formatted = "[bold green]Enabled (True)[/bold green]"
        elif val.lower() == "false":
            val_formatted = "[bold red]Disabled (False)[/bold red]"
        else:
            val_formatted = f"[white]{val}[/white]"
        table.add_row(label, val_formatted)

    console.print(table)

def show_stats():
    stats = get_stats_data()
    if not stats:
        console.print("[yellow][!] No stats available yet. Start downloading to see statistics![/]")
        return
        
    from rich import box
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Stat", style="cyan", justify="right")
    table.add_column("Value", style="magenta")
    
    rate = stats['success_rate']
    bar_width = 10
    filled = int(round((rate / 100.0) * bar_width))
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
        expand=False
    )
    console.print(panel)
    console.print()

def show_platforms(search_term=""):
    try:
        import yt_dlp
        extractors = yt_dlp.extractor.gen_extractors()
        platforms = sorted(list(set(ie.IE_NAME.split(':')[0].capitalize() for ie in extractors if ie.IE_NAME != 'generic')))
        if search_term:
            platforms = [p for p in platforms if search_term.lower() in p.lower()]
            if not platforms:
                print(f"{YELLOW}[!] No platforms found matching '{search_term}'.{RESET}")
                return
            print(f"\n{BOLD}--- Matching Supported Platforms ({len(platforms)}) ---{RESET}")
        else:
            print(f"\n{BOLD}--- All Supported Platforms ({len(platforms)}) ---{RESET}")
        
        import shutil
        cols = shutil.get_terminal_size().columns
        col_width = 20
        num_cols = max(1, cols // col_width)
        for i in range(0, len(platforms), num_cols):
            row = platforms[i:i+num_cols]
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

def print_help():
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
        ("/history [filter]", "View history; filters: failed, audio, media, search <text>"),
        ("/batch <file>", "Download multiple URLs from a text file"),
        ("/instagram <url>", "Download post, reel, igtv from Instagram with description & metadata"),
        ("/video <url>", "Download video from a URL"),
        ("/audio <url>", "Download video/song directly as MP3"),
        ("/video_quality [value]", "Set video quality (interactive if value is omitted)"),
        ("/audio_quality [value]", "Set audio quality in kbps (interactive if value is omitted)"),
        ("/video_format [value]", "Set video format (e.g. mp4, mkv) (interactive if value is omitted)"),
        ("/audio_format [value]", "Set audio format (e.g. mp3, m4a) (interactive if value is omitted)"),
        ("/platform [search]", "List or search supported platforms"),
        ("/trim <start>-<end>", "Trim video/audio (e.g. /trim 01:15-02:30 <url>)"),
        ("/subs", "Toggle automatic subtitle/lyric extraction"),
        ("/sort", "Toggle auto-sorting into platform directories"),
        ("/username [name]", "Change and save your username"),
        ("/greeting [text]", "Change and save your greeting statement"),
        ("/delete_his <target>", "Delete history: all, index (e.g. 3), or range (e.g. 2-4)"),
        ("/update", "Update the core downloading engine (yt-dlp)"),
        ("/exit, exit, quit", "Exit the CLI safely"),
    ]

    for cmd_str, desc in sorted(help_items, key=lambda x: x[0]):
        table.add_row(cmd_str, desc)

    console.print(table)
    
    output_dir = config.get("output_dir", "downloads")
    tips = f"""[bold]Download Tips:[/]
  - Paste any media URL directly to start downloading.
  - To bypass the safety rate limit, append [yellow]--force[/] to your URL.
  - Current output: [yellow]{output_dir}[/]
  - Current quality: [yellow]{config.get("quality", "best")}[/]
"""
    console.print(Panel(tips, border_style="cyan"))

def show_history_rendered(filter_text=""):
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
    
    from prompt_toolkit.application import Application
    from prompt_toolkit.formatted_text import ANSI
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import Layout
    from prompt_toolkit.layout.containers import HSplit, Window
    from prompt_toolkit.layout.controls import FormattedTextControl
    from prompt_toolkit.keys import Keys
    import io

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
            header_style="bold cyan"
        )
        table.add_column("S.No.", justify="right", width=6)
        table.add_column("Date", style="cyan", width=20)
        table.add_column("Status", justify="center", width=12)
        table.add_column("Mode", style="magenta", width=10)
        table.add_column("Quality", style="magenta", width=10)
        table.add_column("URL", style="blue")
        table.add_column(" ", justify="center", width=1) # Scrollbar column!

        for i, d in enumerate(page_items):
            absolute_idx = start + i
            is_selected = (absolute_idx == selected_val)
            
            dt = datetime.datetime.fromtimestamp(d["time"]).strftime('%Y-%m-%d %H:%M:%S')
            url = d.get("url", "Unknown URL")
            status = d.get("status", "unknown")
            mode = d.get("mode", "media")
            quality = d.get("quality", "best")
            
            status_text = "[green]SUCCESS[/]" if status == "success" else f"[red]{status.upper()}[/]"
            
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
                style=row_style
            )
            
        buf = io.StringIO()
        temp_console = Console(file=buf, color_system="truecolor", force_terminal=True)
        temp_console.print(table)
        temp_console.print()
        temp_console.print("  [yellow]Use [bold]Up/Down[/] arrow keys to scroll log entries.[/]")
        temp_console.print("  [yellow]Use [bold]Left/Right[/] arrow keys to scroll by 10 entries.[/]")
        temp_console.print("  [yellow]Press [bold]ESC[/] or [bold]q[/] to exit history view.[/]")
        return buf.getvalue()

    # If it is interactive, use prompt_toolkit Application to handle arrow keys and escape
    try:
        initial_text = get_rendered_page(0, 0)
        content_control = FormattedTextControl(text=ANSI(initial_text))
        
        kb = KeyBindings()
        
        @kb.add('up')
        def _(event):
            if selected_idx[0] > 0:
                selected_idx[0] -= 1
                if selected_idx[0] < scroll_offset[0]:
                    scroll_offset[0] = selected_idx[0]
                content_control.text = ANSI(get_rendered_page(scroll_offset[0], selected_idx[0]))

        @kb.add('down')
        def _(event):
            if selected_idx[0] < total - 1:
                selected_idx[0] += 1
                if selected_idx[0] >= scroll_offset[0] + viewport_size:
                    scroll_offset[0] = selected_idx[0] - viewport_size + 1
                content_control.text = ANSI(get_rendered_page(scroll_offset[0], selected_idx[0]))

        @kb.add('left')
        def _(event):
            if selected_idx[0] > 0:
                selected_idx[0] = max(0, selected_idx[0] - 10)
                if selected_idx[0] < scroll_offset[0]:
                    scroll_offset[0] = selected_idx[0]
                content_control.text = ANSI(get_rendered_page(scroll_offset[0], selected_idx[0]))

        @kb.add('right')
        def _(event):
            if selected_idx[0] < total - 1:
                selected_idx[0] = min(total - 1, selected_idx[0] + 10)
                if selected_idx[0] >= scroll_offset[0] + viewport_size:
                    scroll_offset[0] = selected_idx[0] - viewport_size + 1
                content_control.text = ANSI(get_rendered_page(scroll_offset[0], selected_idx[0]))

        @kb.add('escape')
        @kb.add('q')
        def _(event):
            event.app.exit()

        layout = Layout(HSplit([Window(content=content_control)]))
        app = Application(layout=layout, key_bindings=kb, full_screen=False, mouse_support=False)
        app.run()
    except Exception:
        # Non-interactive fallback: print all rows
        fallback_console = Console()
        fallback_console.print("[yellow][!] Non-interactive fallback: showing all history records.[/]")
        table = Table(title="Downloads History (All Records)", style="blue")
        table.add_column("S.No.", justify="right", width=6)
        table.add_column("Date", style="cyan")
        table.add_column("Status", justify="center")
        table.add_column("Mode", style="magenta")
        table.add_column("Quality", style="magenta")
        table.add_column("URL", style="blue")

        for idx, d in enumerate(downloads):
            dt = datetime.datetime.fromtimestamp(d["time"]).strftime('%Y-%m-%d %H:%M:%S')
            url = d.get("url", "Unknown URL")
            status = d.get("status", "unknown")
            mode = d.get("mode", "media")
            quality = d.get("quality", "best")
            
            status_text = "[green]SUCCESS[/]" if status == "success" else f"[red]{status.upper()}[/]"
            table.add_row(str(idx + 1), dt, status_text, mode, quality, url)
            
        fallback_console.print(table)


def open_output_folder():
    output_dir = config.get("output_dir", "downloads")
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.abspath(output_dir)
    try:
        import webbrowser
        if sys.platform.startswith("win"):
            os.startfile(path)
        else:
            webbrowser.open(Path(path).as_uri())
        print(f"{GREEN}[+] Opened: {path}{RESET}")
    except Exception as e:
        print(f"{RED}[X] Could not open folder: {e}{RESET}")

def get_greeting_message():
    username = config.get("username", "").strip()
    greeting = config.get("greeting", "Har Har Mahadev 🔱").strip()
    return f"{greeting}, {username}"

def print_welcome_screen():
    greeting_msg = get_greeting_message()
    output_dir = config.get("output_dir", "downloads")
    quality = config.get("quality", "best")
    audio_quality = config.get("audio_quality", "192")
    embed_subs = "Enabled" if config.get("embed_subs", False) else "Disabled"
    auto_sort = "Enabled" if config.get("auto_sort", False) else "Disabled"
    
    from .history import get_rate_limit_info
    
    rate_limit_hours = int(config.get("rate_limit_hours", 1))
    rate_limit_count = int(config.get("rate_limit_count", 5))
    force_rate_limit_count = int(config.get("force_rate_limit_count", 5))
    info = get_rate_limit_info(rate_limit_hours, rate_limit_count, force_rate_limit_count)
    
    limit_text = f"⏳ [cyan]Limits     :[/cyan] [yellow]{info['reset_time_str']} left (for Reset)[/yellow]  |  Normal [yellow]{info['normal_remaining']}/{rate_limit_count}[/yellow]  |  Force [yellow]{info['force_remaining']}/{force_rate_limit_count}[/yellow]\n\n" if info["active"] else f"⏳ [cyan]Limits     :[/cyan] [yellow]Fresh window! Next download starts timer.[/yellow]\n\n"
    
    welcome_text = (
        f"[bold green]🔱 {greeting_msg}[/bold green]\n\n"
        f"  📂 [cyan]Output Dir :[/cyan] [magenta]{output_dir}[/magenta]\n"
        f"  🎬 [cyan]Video Qual :[/cyan] [magenta]{quality}[/magenta]  |  🎵 [cyan]Audio Qual :[/cyan] [magenta]{audio_quality} kbps[/magenta]\n"
        f"  💬 [cyan]Subtitles  :[/cyan] [magenta]{embed_subs}[/magenta]  |  🗂️  [cyan]Auto-Sort  :[/cyan] [magenta]{auto_sort}[/magenta]\n"
        f"  {limit_text}"
        f"[dim white]Type any media URL directly to download, or type [bold yellow]/help[/] for commands.[/]"
    )
    console.print(Panel(welcome_text, title="[bold yellow]PINAK CONTROL PANEL[/]", border_style="cyan", expand=False))
    console.print()

def print_exit_screen(interrupted=False):
    greeting_msg = get_greeting_message()
    from rich.panel import Panel
    from rich import box
    
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
        expand=False
    )
    console.print(panel)

def repl_loop():
    print_banner()
    username = config.get("username", "").strip()
    if not username:
        console.print("[yellow][!] Before we begin, please tell us your name.[/]")
        username = ask_with_esc(questionary.text("Enter your name:"))
        if not username:
            print(f"\n{CYAN}[*] Goodbye!{RESET}")
            sys.exit(0)
        config["username"] = username.strip()
        save_config()
        console.print() # Add empty line for neatness instead of clearing
    print_welcome_screen()
    commands_meta = {
        '/help': 'Show this help menu',
        '/doctor': 'Check dependencies and output folder',
        '/config': 'Show saved preferences',
        '/stats': 'Show download analytics and insights',
        '/setout': 'Change and save the output directory',
        '/open': 'Open the current output folder',
        '/history': 'View download history',
        '/batch': 'Download multiple URLs from a text file',
        '/instagram': 'Download post, reel, igtv from Instagram',
        '/video': 'Download video from a URL',
        '/audio': 'Download video/song directly as MP3',
        '/video_quality': 'Set video quality (interactive if value is omitted)',
        '/audio_quality': 'Set audio quality in kbps (interactive if value is omitted)',
        '/video_format': 'Set video format (e.g. mp4, mkv) (interactive if value is omitted)',
        '/audio_format': 'Set audio format (e.g. mp3, m4a) (interactive if value is omitted)',
        '/platform': 'List or search supported platforms',
        '/trim': 'Trim video/audio (e.g. /trim 01:15-02:30 <url>)',
        '/subs': 'Toggle automatic subtitle/lyric extraction',
        '/sort': 'Toggle auto-sorting into platform directories',
        '/delete_his': 'Delete history: all, index (e.g. 3), or range (e.g. 2-4)',
        '/update': 'Update the core downloading engine (yt-dlp)',
        '/username': 'Change and save your username',
        '/greeting': 'Change and save your greeting statement',
        '/exit': 'Exit the CLI safely',
    }
    
    commands_completer = WordCompleter(
        sorted(list(commands_meta.keys())), 
        meta_dict=commands_meta, 
        ignore_case=True,
        pattern=re.compile(r'[a-zA-Z0-9_]*\/?')
    )

    custom_style = Style.from_dict({
        'prompt': 'ansicyan bold',
        'completion-menu.completion': 'bg:#005588 #ffffff',
        'completion-menu.completion.current': 'bg:#0088ff #ffffff',
        'completion-menu.meta.completion': 'bg:#003355 #cccccc',
        'completion-menu.meta.completion.current': 'bg:#005588 #ffffff',
    })
    
    class FilteredHistory(FileHistory):
        def append_string(self, string: str) -> None:
            lower_str = string.strip().lower()
            if lower_str in ['/video', '/audio', '/trim', '/setout', '/batch', '/delete_his', '/instagram']:
                return
            super().append_string(string)
            
    history_file = os.path.expanduser("~/.pinak_cli_history")
    session = PromptSession(history=FilteredHistory(history_file))

    kb = KeyBindings()
    @kb.add('enter')
    def _(event):
        buffer = event.current_buffer
        text = buffer.text.strip().lower()
        if text in ['/video', '/audio', '/trim', '/setout', '/batch', '/delete_his', '/instagram']:
            buffer.text = buffer.text.strip() + ' '
            buffer.cursor_position = len(buffer.text)
        else:
            buffer.validate_and_handle()

    default_cmd = ""
    has_shown_update = False
    updater.start_background_update_check()
    initialize_session()  # Generate a fresh session ID for telemetry tracking
    push_session_start()  # Fire session_start event to backend

    while True:
        try:
            if updater.UPDATE_AVAILABLE and not has_shown_update:
                console.print(f"\n[yellow]💡 A new version of {updater.UPDATE_PACKAGE} ({updater.UPDATE_AVAILABLE}) is available! Type [bold]/update[/bold] to install it.[/]")
                has_shown_update = True
                
            cmd = session.prompt(
                "Pinak 🔱 > ", 
                default=default_cmd,
                completer=commands_completer,
                complete_while_typing=True,
                style=custom_style,
                mouse_support=False,
                key_bindings=kb
            ).strip()
            
            default_cmd = ""
            
            if not cmd:
                continue

            lower_cmd = cmd.lower()
            
            # Fallback if somehow submitted (e.g. mouse double click)
            if lower_cmd in ['/video', '/audio', '/trim', '/setout', '/batch', '/delete_his', '/instagram', '/facebook']:
                default_cmd = f"{cmd} "
                continue


            if lower_cmd in ['/exit', 'exit', 'quit']:
                push_command_event("/exit")  # Log exit as a command; session_start already marks session open
                print_exit_screen(interrupted=False)
                print_separator()
                break

            if lower_cmd == '/update':
                push_command_event("/update")
                console.print(f"[cyan]🔄 Updating {updater.UPDATE_PACKAGE} to the latest version...[/]")
                import subprocess
                try:
                    with console.status("[cyan]Downloading and installing...[/]", spinner="dots"):
                        result = subprocess.run(
                            [sys.executable, "-m", "pip", "install", "--upgrade", updater.UPDATE_PACKAGE],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True
                        )
                    if result.returncode == 0:
                        console.print(f"[green][+] Successfully updated {updater.UPDATE_PACKAGE}![/]")
                        updater.UPDATE_AVAILABLE = None
                    else:
                        console.print(f"[red][X] Update failed. Error:\n{result.stderr}[/]")
                except Exception as e:
                    console.print(f"[red][X] Update error: {e}[/]")
                continue


            if lower_cmd == '/delete_his' or lower_cmd.startswith('/delete_his '):
                push_command_event(cmd)
                arg = cmd[11:].strip()
                if not arg:
                    console.print("[yellow][!] Usage: /delete_his all | <number> | <range> (e.g. /delete_his 3 or /delete_his 2-4)[/]")
                    continue
                
                # 1. /delete_his all
                if arg.lower() == 'all':
                    clear_all_history()
                    console.print("[green][+] Successfully cleared entire downloads history log.[/]")
                    continue
                    
                # 2. /delete_his X-Y (Range)
                match_range = re.match(r"^(\d+)-(\d+)$", arg)
                if match_range:
                    start_sno = int(match_range.group(1))
                    end_sno = int(match_range.group(2))
                    if start_sno <= 0 or end_sno <= 0 or start_sno > end_sno:
                        console.print(f"[red][X] Error: Invalid range '{arg}'. Start and end values must be positive integers, and start <= end.[/]")
                        continue
                    
                    # Fetch history ids (newest first)
                    ids = get_history_ids_desc()
                    total_records = len(ids)
                    if start_sno > total_records:
                        console.print(f"[red][X] Error: Range start {start_sno} exceeds total history count ({total_records}).[/]")
                        continue
                    
                    actual_end_sno = min(end_sno, total_records)
                    ids_to_delete = ids[start_sno - 1 : actual_end_sno]
                    
                    if not ids_to_delete:
                        console.print(f"[red][X] Error: No records found in range '{arg}'.[/]")
                        continue
                    
                    delete_history_by_ids(ids_to_delete)
                    console.print(f"[green][+] Successfully deleted log entries in range {start_sno} to {actual_end_sno} (Total: {len(ids_to_delete)}).[/]")
                    continue
                
                # 3. /delete_his X (Single log number)
                match_single = re.match(r"^(\d+)$", arg)
                if match_single:
                    sno = int(match_single.group(1))
                    if sno <= 0:
                        console.print(f"[red][X] Error: Log number must be a positive integer.[/]")
                        continue
                    
                    ids = get_history_ids_desc()
                    total_records = len(ids)
                    if sno > total_records:
                        console.print(f"[red][X] Error: Log number {sno} exceeds total history count ({total_records}).[/]")
                        continue
                    
                    id_to_delete = ids[sno - 1]
                    delete_history_by_ids([id_to_delete])
                    console.print(f"[green][+] Successfully deleted log entry #{sno}.[/]")
                    continue
                    
                console.print(f"[red][X] Error: Unknown input '{arg}'. Use /delete_his all, or a number (e.g. 3), or a range (e.g. 2-4).[/]")
                continue

            if lower_cmd in ('/', '/help'):
                push_command_event("/help")
                print_help()
                continue

            if lower_cmd == '/doctor':
                push_command_event("/doctor")
                run_doctor()
                continue

            if lower_cmd == '/config':
                push_command_event("/config")
                show_config()
                continue

            if lower_cmd == '/stats':
                push_command_event("/stats")
                show_stats()
                continue

            if lower_cmd == '/open':
                push_command_event("/open")
                open_output_folder()
                continue

            if lower_cmd.startswith('/history'):
                push_command_event("/history")
                show_history_rendered(cmd[8:].strip())
                continue

            if lower_cmd == '/username' or lower_cmd.startswith('/username '):
                push_command_event("/username")
                new_username = cmd[9:].strip()
                if not new_username:
                    try:
                        new_username = input(f"Enter new username [current: {config.get('username')}]: ").strip()
                    except (KeyboardInterrupt, EOFError):
                        print(f"{YELLOW}[*] Canceled.{RESET}")
                        continue
                if new_username:
                    config["username"] = new_username
                    save_config()
                    print(f"{GREEN}[+] Username updated to: {new_username}{RESET}")
                else:
                    print(f"{YELLOW}[*] Username unchanged.{RESET}")
                continue

            if lower_cmd == '/greeting' or lower_cmd.startswith('/greeting ') or lower_cmd == '/gretting' or lower_cmd.startswith('/gretting '):
                push_command_event("/greeting")
                # Determine prefix length based on the actual command typed
                if lower_cmd.startswith('/greeting'):
                    arg_start = len('/greeting')
                else:
                    arg_start = len('/gretting')
                new_greeting = cmd[arg_start:].strip()
                if not new_greeting:
                    try:
                        new_greeting = input(f"Enter new greeting [current: {config.get('greeting')}]: ").strip()
                    except (KeyboardInterrupt, EOFError):
                        print(f"{YELLOW}[*] Canceled.{RESET}")
                        continue
                if new_greeting:
                    config["greeting"] = new_greeting
                    save_config()
                    print(f"{GREEN}[+] Greeting updated to: {new_greeting}{RESET}")
                else:
                    print(f"{YELLOW}[*] Greeting unchanged.{RESET}")
                continue

            if lower_cmd == '/video_quality' or lower_cmd.startswith('/video_quality '):
                push_command_event(cmd)
                arg = cmd[14:].strip()
                if not arg:
                    options = ["best", "1080p", "720p", "480p", "360p", "worst"]
                    current = config.get("quality", "best")
                    choice = ask_with_esc(questionary.select(
                        "Select video/media quality:",
                        choices=options,
                        default=current,
                        instruction="(Press Esc to cancel)"
                    ))
                    if choice:
                        config["quality"] = choice
                        save_config()
                        print(f"{GREEN}[+] Quality set to: {choice}{RESET}")
                    else:
                        print(f"{YELLOW}[*] Canceled.{RESET}")
                    continue
                else:
                    new_quality = normalize_quality(arg)
                    if not new_quality:
                        print(f"{RED}[!] Error: Invalid quality. Use best, worst, audio, 360p, 720p, 1080p.{RESET}")
                        continue
                    config["quality"] = new_quality
                    save_config()
                    print(f"{GREEN}[+] Quality set to: {new_quality}{RESET}")
                    continue

            if lower_cmd == '/audio_quality' or lower_cmd.startswith('/audio_quality '):
                push_command_event(cmd)
                arg = cmd[14:].strip()
                if not arg:
                    options = ["320", "256", "192", "128", "96"]
                    current = str(config.get("audio_quality", "192"))
                    choice = ask_with_esc(questionary.select(
                        "Select audio quality (kbps):",
                        choices=options,
                        default=current,
                        instruction="(Press Esc to cancel)"
                    ))
                    if choice:
                        config["audio_quality"] = choice
                        save_config()
                        print(f"{GREEN}[+] Audio quality set to: {choice} kbps{RESET}")
                    else:
                        print(f"{YELLOW}[*] Canceled.{RESET}")
                    continue
                else:
                    if arg in ["320", "256", "192", "128", "96"]:
                        config["audio_quality"] = arg
                        save_config()
                        print(f"{GREEN}[+] Audio quality set to: {arg} kbps{RESET}")
                    else:
                        print(f"{RED}[!] Error: Invalid audio quality. Use 320, 256, 192, 128, 96.{RESET}")
                    continue
                
            if lower_cmd == '/video_format' or lower_cmd.startswith('/video_format '):
                push_command_event(cmd)
                arg = cmd[14:].strip()
                if not arg:
                    options = ["mp4", "mkv", "webm", "flv", "avi"]
                    current = config.get("video_format", "mp4")
                    choice = ask_with_esc(questionary.select(
                        "Select video format:",
                        choices=options,
                        default=current,
                        instruction="(Press Esc to cancel)"
                    ))
                    if choice:
                        config["video_format"] = choice
                        save_config()
                        print(f"{GREEN}[+] Video format set to: {choice}{RESET}")
                    else:
                        print(f"{YELLOW}[*] Canceled.{RESET}")
                    continue
                else:
                    if arg.lower() in ["mp4", "mkv", "webm", "flv", "avi"]:
                        config["video_format"] = arg.lower()
                        save_config()
                        print(f"{GREEN}[+] Video format set to: {arg.lower()}{RESET}")
                    else:
                        print(f"{RED}[!] Error: Invalid format. Supported: mp4, mkv, webm, flv, avi.{RESET}")
                    continue

            if lower_cmd == '/audio_format' or lower_cmd.startswith('/audio_format '):
                push_command_event(cmd)
                arg = cmd[14:].strip()
                if not arg:
                    options = ["mp3", "m4a", "wav", "flac", "opus"]
                    current = config.get("audio_format", "mp3")
                    choice = ask_with_esc(questionary.select(
                        "Select audio format:",
                        choices=options,
                        default=current,
                        instruction="(Press Esc to cancel)"
                    ))
                    if choice:
                        config["audio_format"] = choice
                        save_config()
                        print(f"{GREEN}[+] Audio format set to: {choice}{RESET}")
                    else:
                        print(f"{YELLOW}[*] Canceled.{RESET}")
                    continue
                else:
                    if arg.lower() in ["mp3", "m4a", "wav", "flac", "opus"]:
                        config["audio_format"] = arg.lower()
                        save_config()
                        print(f"{GREEN}[+] Audio format set to: {arg.lower()}{RESET}")
                    else:
                        print(f"{RED}[!] Error: Invalid format. Supported: mp3, m4a, wav, flac, opus.{RESET}")
                    continue
            if lower_cmd == '/subs':
                push_command_event("/subs")
                config["embed_subs"] = not config.get("embed_subs", False)
                save_config()
                state = "enabled" if config["embed_subs"] else "disabled"
                console.print(f"[green][+] Subtitle extraction {state}.[/]")
                continue

            if lower_cmd == '/sort':
                push_command_event("/sort")
                config["auto_sort"] = not config.get("auto_sort", False)
                save_config()
                state = "enabled" if config["auto_sort"] else "disabled"
                console.print(f"[green][+] Auto-sorting by platform {state}.[/]")
                continue

            if lower_cmd.startswith('/trim '):
                parts = cmd[6:].strip().split(' ', 1)
                if len(parts) < 2:
                    console.print("[yellow]Usage: /trim <start>-<end> <url> (e.g. /trim 00:15-01:30 https://...)[/]")
                    continue
                trim_str, raw_url_text = parts[0], parts[1]
                url, extract_audio, force, req_quality = parse_download_text(raw_url_text)
                final_quality = req_quality or config.get("quality", "best")
                handle_download(url, extract_audio=extract_audio, force=force, quality=final_quality, interactive=True, trim_range=trim_str)
                continue

            if lower_cmd.startswith('/setout '):
                push_command_event(cmd)
                new_dir = cmd[8:].strip()
                if new_dir:
                    config["output_dir"] = new_dir
                    save_config()
                    print(f"{GREEN}[+] Output directory updated to: {new_dir}{RESET}")
                else:
                    print(f"{RED}[!] Error: Please specify a folder path.{RESET}")
                continue

            if lower_cmd.startswith('/platform'):
                push_command_event(cmd)
                search_term = cmd[9:].strip()
                show_platforms(search_term)
                continue

            if lower_cmd.startswith('/batch '):
                push_command_event("/batch")
                filename = cmd[7:].strip()
                if not os.path.exists(filename):
                    print(f"{RED}[!] Error: Batch file '{filename}' not found.{RESET}")
                    continue
                with open(filename, 'r', encoding='utf-8') as f:
                    lines = [l.strip() for l in f if l.strip() and not l.startswith('#')]

                print(f"\n[*] Found {len(lines)} URLs in {filename}.")
                for idx, batch_url in enumerate(lines):
                    rate_limit_hours = int(config.get("rate_limit_hours", 1))
                    force_rate_limit_count = int(config.get("force_rate_limit_count", 5))
                    url, extract_audio, force, quality = parse_download_text(batch_url)
                    limit_to_check = force_rate_limit_count if force else int(config.get("rate_limit_count", 5))
                    if not check_rate_limit(rate_limit_hours, limit_to_check, check_forced=force):
                        print(f"{RED}[!] Safety Lock reached during batch. Stopping batch.{RESET}")
                        break
                    print(f"\n{BOLD}--- Batch Item {idx+1}/{len(lines)} ---{RESET}")
                    handle_download(url, extract_audio=extract_audio, force=force, quality=quality, interactive=False)
                continue



            if cmd.startswith('/'):
                if not (lower_cmd.startswith('/audio ') or lower_cmd.startswith('/video ') or lower_cmd.startswith('/instagram ')):
                    print(f"{YELLOW}[!] Unknown command: {cmd}. Type /help for assistance.{RESET}")
                    continue
                url, extract_audio, force, quality = parse_download_text(cmd)
                handle_download(url, extract_audio=extract_audio, force=force, quality=quality)
            else:
                if cmd.lower().startswith("http"):
                    print(f"{YELLOW}[!] Direct URL detected. Use /video, /audio, or /instagram before the link.")
                    print(f"    Example: /instagram {cmd}{RESET}")
                else:
                    print(f"{YELLOW}[!] Unknown input: '{cmd}'. Type /help to see all commands.{RESET}")
                continue

        except KeyboardInterrupt:
            if is_downloading:
                print(f"\n{YELLOW}[!] Download in progress. Exiting now might corrupt files. Please wait...{RESET}")
            else:
                push_command_event("/exit")  # Ctrl+C exit — log as command, no redundant session_end
                print_exit_screen(interrupted=True)
                break

app = typer.Typer(invoke_without_command=True, add_completion=False)

@app.callback()
def main(
    url: Optional[str] = typer.Argument(None, help="The URL to download from"),
    output: Optional[str] = typer.Option(None, "-o", "--output", help="Output directory"),
    force: bool = typer.Option(False, "--force", help="Bypass safety rate limits"),
    audio: bool = typer.Option(False, "--audio", help="Extract audio directly as MP3"),
    quality: Optional[str] = typer.Option(None, "--quality", help="Quality: best, worst, audio, 360p, 720p, 1080p"),
    doctor: bool = typer.Option(False, "--doctor", help="Run environment checks and exit")
):
    init_config()
    init_db()
    initialize_session()  # Generate session ID for telemetry even in single-command mode
    
    if len(sys.argv) > 1 and not (len(sys.argv) == 2 and sys.argv[1] == '--help'):
        if output:
            config["output_dir"] = output
            save_config()

        if doctor:
            run_doctor()
            raise typer.Exit()

        if not url:
            console.print("[red][!] Error: URL is required in single-command mode.[/red]")
            raise typer.Exit(code=1)
            
        if not url.startswith("http"):
            console.print("[red][!] Error: Please provide a valid URL starting with http:// or https://[/red]")
            raise typer.Exit(code=1)

        norm_quality = normalize_quality(quality or config.get("quality", "best"))
        if not norm_quality:
            console.print("[red][!] Error: Invalid quality. Use best, worst, audio, 360p, 720p, or 1080p.[/red]")
            raise typer.Exit(code=1)

        extract_audio = audio or norm_quality == "audio"
        handle_download(url, extract_audio=extract_audio, force=force, quality=norm_quality, interactive=False)
    else:
        repl_loop()

def run_cli():
    app()

if __name__ == "__main__":
    run_cli()
