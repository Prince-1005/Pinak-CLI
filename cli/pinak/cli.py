import contextlib
import os
import re
import sys

# Configure UTF-8 encoding for stdout/stderr to prevent emoji rendering errors on Windows
if hasattr(sys.stdout, "reconfigure"):
    with contextlib.suppress(Exception):
        sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    with contextlib.suppress(Exception):
        sys.stderr.reconfigure(encoding="utf-8")

import questionary
import typer
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.styles import Style
from rich.console import Console

from . import updater
from .commands.info import (
    open_output_folder,
    print_help,
    show_config,
    show_history_rendered,
    show_platforms,
    show_stats,
)
from .commands.panels import (
    print_banner,
    print_exit_screen,
    print_separator,
    print_welcome_screen,
)
from .config import CONFIG_FILE, config, init_config, save_config
from .doctor import run_doctor
from .downloader import handle_download, is_downloading, parse_download_text
from .history import (
    clear_all_history,
    delete_history_by_ids,
    get_history_ids_desc,
    init_db,
    initialize_session,
    push_command_event,
    push_session_start,
)
from .logging_setup import setup_logging
from .notify import print_offline_notice
from .utils import BOLD, CYAN, GREEN, RED, RESET, YELLOW, normalize_quality

console = Console()


def ask_with_esc(q):
    """Wrapper to allow Esc key to cancel questionary prompts."""
    try:

        @q.application.key_bindings.add(Keys.Escape, eager=True)
        def _(event):
            event.app.exit(result=None)

    except AttributeError:
        from prompt_toolkit.key_binding import KeyBindings, merge_key_bindings

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


def repl_loop():  # pragma: no cover - interactive TTY loop, exercised manually
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
        console.print()  # Add empty line for neatness instead of clearing
    print_welcome_screen()
    commands_meta = {
        "/help": "Show this help menu",
        "/doctor": "Check dependencies and output folder",
        "/config": "Show saved preferences",
        "/stats": "Show download analytics and insights",
        "/setout": "Change and save the output directory",
        "/open": "Open the current output folder",
        "/history": "View download history",
        "/batch": "Download multiple URLs from a text file",
        "/instagram": "Download post, reel, igtv from Instagram",
        "/video": "Download video from a URL",
        "/audio": "Download video/song directly as MP3",
        "/video_quality": "Set video quality (interactive if value is omitted)",
        "/audio_quality": "Set audio quality in kbps (interactive if value is omitted)",
        "/video_format": "Set video format (e.g. mp4, mkv) (interactive if value is omitted)",
        "/audio_format": "Set audio format (e.g. mp3, m4a) (interactive if value is omitted)",
        "/platform": "List or search supported platforms",
        "/trim": "Trim video/audio (e.g. /trim 01:15-02:30 <url>)",
        "/subs": "Toggle automatic subtitle/lyric extraction",
        "/sort": "Toggle auto-sorting into platform directories",
        "/delete_his": "Delete history: all, index (e.g. 3), or range (e.g. 2-4)",
        "/ffmpeg": "Download a static FFmpeg build automatically",
        "/update": "Update yt-dlp and Pinak itself to the latest versions",
        "/username": "Change and save your username",
        "/greeting": "Change and save your greeting statement",
        "/exit": "Exit the CLI safely",
    }

    commands_completer = WordCompleter(
        sorted(commands_meta),
        meta_dict=commands_meta,
        ignore_case=True,
        pattern=re.compile(r"[a-zA-Z0-9_]*\/?"),
    )

    custom_style = Style.from_dict(
        {
            "prompt": "ansicyan bold",
            "completion-menu.completion": "bg:#005588 #ffffff",
            "completion-menu.completion.current": "bg:#0088ff #ffffff",
            "completion-menu.meta.completion": "bg:#003355 #cccccc",
            "completion-menu.meta.completion.current": "bg:#005588 #ffffff",
        }
    )

    class FilteredHistory(FileHistory):
        def append_string(self, string: str) -> None:
            lower_str = string.strip().lower()
            if lower_str in [
                "/video",
                "/audio",
                "/trim",
                "/setout",
                "/batch",
                "/delete_his",
                "/instagram",
            ]:
                return
            super().append_string(string)

    history_file = os.path.expanduser("~/.pinak_cli_history")
    session = PromptSession(history=FilteredHistory(history_file))

    kb = KeyBindings()

    @kb.add("enter")
    def _(event):
        buffer = event.current_buffer
        text = buffer.text.strip().lower()
        if text in [
            "/video",
            "/audio",
            "/trim",
            "/setout",
            "/batch",
            "/delete_his",
            "/instagram",
        ]:
            buffer.text = buffer.text.strip() + " "
            buffer.cursor_position = len(buffer.text)
        else:
            buffer.validate_and_handle()

    default_cmd = ""
    has_shown_update = False
    has_shown_pinak_update = False
    updater.start_background_update_check()
    initialize_session()  # Generate a fresh session ID for telemetry tracking
    push_session_start()  # Fire session_start event to backend

    while True:
        try:
            if updater.UPDATE_AVAILABLE and not has_shown_update:
                console.print(
                    f"\n[yellow]💡 A new version of {updater.UPDATE_PACKAGE} ({updater.UPDATE_AVAILABLE}) is available! Type [bold]/update[/bold] to install it.[/]"
                )
                has_shown_update = True

            if updater.PINAK_UPDATE_AVAILABLE and not has_shown_pinak_update:
                from .notify import print_update_notice

                print_update_notice(updater.PINAK_PACKAGE, updater.PINAK_UPDATE_AVAILABLE)
                has_shown_pinak_update = True

            cmd = session.prompt(
                "Pinak 🔱 > ",
                default=default_cmd,
                completer=commands_completer,
                complete_while_typing=True,
                style=custom_style,
                mouse_support=False,
                key_bindings=kb,
            ).strip()

            default_cmd = ""

            if not cmd:
                continue

            lower_cmd = cmd.lower()

            # Fallback if somehow submitted (e.g. mouse double click)
            if lower_cmd in [
                "/video",
                "/audio",
                "/trim",
                "/setout",
                "/batch",
                "/delete_his",
                "/instagram",
            ]:
                default_cmd = f"{cmd} "
                continue

            if lower_cmd in ["/exit", "exit", "quit"]:
                push_command_event(
                    "/exit"
                )  # Log exit as a command; session_start already marks session open
                print_exit_screen(interrupted=False)
                print_separator()
                break

            if lower_cmd == "/ffmpeg":
                push_command_event("/ffmpeg")
                from .ffmpeg_setup import ensure_ffmpeg, install_ffmpeg_extra

                existing = ensure_ffmpeg()
                import shutil as _shutil

                if existing and (os.path.exists(existing) or _shutil.which(existing)):
                    console.print(f"[green][+] FFmpeg already available: {existing}[/]")
                else:
                    console.print("[cyan]Fetching a static FFmpeg build (pinak-cli[ffmpeg])...[/]")
                    fetched = install_ffmpeg_extra()
                    if fetched:
                        console.print(f"[green][+] FFmpeg ready at: {fetched}[/]")
                    else:
                        console.print(
                            "[red][X] Automatic install failed. Install FFmpeg from "
                            "https://ffmpeg.org/download.html, add it to PATH, or run: "
                            'pip install "pinak-cli[ffmpeg]"[/]'
                        )
                continue

            if lower_cmd == "/update":
                push_command_event("/update")
                console.print("[cyan]🔄 Updating the downloader engine and Pinak itself...[/]")
                try:
                    with console.status("[cyan]Downloading and installing...[/]", spinner="dots"):
                        results = updater.perform_update()
                    for package, message in results.items():
                        if message.startswith("Updated ") or "already the latest" in message:
                            console.print(f"[green][+] {message}[/]")
                        else:
                            console.print(f"[red][X] {package}: {message}[/]")
                    # "→" only appears on a real pinak version bump.
                    if "→" in results.get(updater.PINAK_PACKAGE, ""):
                        console.print(
                            "[yellow]Pinak itself was updated — "
                            "restart the CLI (/exit, then run pinak again) "
                            "to use the new version.[/]"
                        )
                except Exception as e:
                    console.print(f"[red][X] Update error: {e}[/]")
                continue

            if lower_cmd == "/delete_his" or lower_cmd.startswith("/delete_his "):
                push_command_event(cmd)
                arg = cmd[11:].strip()
                if not arg:
                    console.print(
                        "[yellow][!] Usage: /delete_his all | <number> | <range> (e.g. /delete_his 3 or /delete_his 2-4)[/]"
                    )
                    continue

                # 1. /delete_his all
                if arg.lower() == "all":
                    clear_all_history()
                    console.print(
                        "[green][+] Successfully cleared entire downloads history log.[/]"
                    )
                    continue

                # 2. /delete_his X-Y (Range)
                match_range = re.match(r"^(\d+)-(\d+)$", arg)
                if match_range:
                    start_sno = int(match_range.group(1))
                    end_sno = int(match_range.group(2))
                    if start_sno <= 0 or end_sno <= 0 or start_sno > end_sno:
                        console.print(
                            f"[red][X] Error: Invalid range '{arg}'. Start and end values must be positive integers, and start <= end.[/]"
                        )
                        continue

                    # Fetch history ids (newest first)
                    ids = get_history_ids_desc()
                    total_records = len(ids)
                    if start_sno > total_records:
                        console.print(
                            f"[red][X] Error: Range start {start_sno} exceeds total history count ({total_records}).[/]"
                        )
                        continue

                    actual_end_sno = min(end_sno, total_records)
                    ids_to_delete = ids[start_sno - 1 : actual_end_sno]

                    if not ids_to_delete:
                        console.print(f"[red][X] Error: No records found in range '{arg}'.[/]")
                        continue

                    delete_history_by_ids(ids_to_delete)
                    console.print(
                        f"[green][+] Successfully deleted log entries in range {start_sno} to {actual_end_sno} (Total: {len(ids_to_delete)}).[/]"
                    )
                    continue

                # 3. /delete_his X (Single log number)
                match_single = re.match(r"^(\d+)$", arg)
                if match_single:
                    sno = int(match_single.group(1))
                    if sno <= 0:
                        console.print("[red][X] Error: Log number must be a positive integer.[/]")
                        continue

                    ids = get_history_ids_desc()
                    total_records = len(ids)
                    if sno > total_records:
                        console.print(
                            f"[red][X] Error: Log number {sno} exceeds total history count ({total_records}).[/]"
                        )
                        continue

                    id_to_delete = ids[sno - 1]
                    delete_history_by_ids([id_to_delete])
                    console.print(f"[green][+] Successfully deleted log entry #{sno}.[/]")
                    continue

                console.print(
                    f"[red][X] Error: Unknown input '{arg}'. Use /delete_his all, or a number (e.g. 3), or a range (e.g. 2-4).[/]"
                )
                continue

            if lower_cmd in ("/", "/help"):
                push_command_event("/help")
                print_help()
                continue

            if lower_cmd == "/doctor" or lower_cmd.startswith("/doctor "):
                push_command_event("/doctor")
                _doc_verbose = "--verbose" in lower_cmd or " -v" in lower_cmd
                run_doctor(verbose=_doc_verbose)
                continue

            if lower_cmd == "/config":
                push_command_event("/config")
                show_config()
                continue

            if lower_cmd == "/stats":
                push_command_event("/stats")
                show_stats()
                continue

            if lower_cmd == "/open":
                push_command_event("/open")
                open_output_folder()
                continue

            if lower_cmd.startswith("/history"):
                push_command_event("/history")
                show_history_rendered(cmd[8:].strip())
                continue

            if lower_cmd == "/username" or lower_cmd.startswith("/username "):
                push_command_event("/username")
                new_username = cmd[9:].strip()
                if not new_username:
                    try:
                        new_username = input(
                            f"Enter new username [current: {config.get('username')}]: "
                        ).strip()
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

            if (
                lower_cmd == "/greeting"
                or lower_cmd.startswith("/greeting ")
                or lower_cmd == "/gretting"
                or lower_cmd.startswith("/gretting ")
            ):
                push_command_event("/greeting")
                # Determine prefix length based on the actual command typed
                if lower_cmd.startswith("/greeting"):
                    arg_start = len("/greeting")
                else:
                    arg_start = len("/gretting")
                new_greeting = cmd[arg_start:].strip()
                if not new_greeting:
                    try:
                        new_greeting = input(
                            f"Enter new greeting [current: {config.get('greeting')}]: "
                        ).strip()
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

            if lower_cmd == "/video_quality" or lower_cmd.startswith("/video_quality "):
                push_command_event(cmd)
                arg = cmd[14:].strip()
                if not arg:
                    options = ["best", "1080p", "720p", "480p", "360p", "worst"]
                    current = config.get("quality", "best")
                    choice = ask_with_esc(
                        questionary.select(
                            "Select video/media quality:",
                            choices=options,
                            default=current,
                            instruction="(Press Esc to cancel)",
                        )
                    )
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
                        print(
                            f"{RED}[!] Error: Invalid quality. Use best, worst, audio, 360p, 720p, 1080p.{RESET}"
                        )
                        continue
                    config["quality"] = new_quality
                    save_config()
                    print(f"{GREEN}[+] Quality set to: {new_quality}{RESET}")
                    continue

            if lower_cmd == "/audio_quality" or lower_cmd.startswith("/audio_quality "):
                push_command_event(cmd)
                arg = cmd[14:].strip()
                if not arg:
                    options = ["320", "256", "192", "128", "96"]
                    current = str(config.get("audio_quality", "192"))
                    choice = ask_with_esc(
                        questionary.select(
                            "Select audio quality (kbps):",
                            choices=options,
                            default=current,
                            instruction="(Press Esc to cancel)",
                        )
                    )
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
                        print(
                            f"{RED}[!] Error: Invalid audio quality. Use 320, 256, 192, 128, 96.{RESET}"
                        )
                    continue

            if lower_cmd == "/video_format" or lower_cmd.startswith("/video_format "):
                push_command_event(cmd)
                arg = cmd[14:].strip()
                if not arg:
                    options = ["mp4", "mkv", "webm", "flv", "avi"]
                    current = config.get("video_format", "mp4")
                    choice = ask_with_esc(
                        questionary.select(
                            "Select video format:",
                            choices=options,
                            default=current,
                            instruction="(Press Esc to cancel)",
                        )
                    )
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
                        print(
                            f"{RED}[!] Error: Invalid format. Supported: mp4, mkv, webm, flv, avi.{RESET}"
                        )
                    continue

            if lower_cmd == "/audio_format" or lower_cmd.startswith("/audio_format "):
                push_command_event(cmd)
                arg = cmd[14:].strip()
                if not arg:
                    options = ["mp3", "m4a", "wav", "flac", "opus"]
                    current = config.get("audio_format", "mp3")
                    choice = ask_with_esc(
                        questionary.select(
                            "Select audio format:",
                            choices=options,
                            default=current,
                            instruction="(Press Esc to cancel)",
                        )
                    )
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
                        print(
                            f"{RED}[!] Error: Invalid format. Supported: mp3, m4a, wav, flac, opus.{RESET}"
                        )
                    continue
            if lower_cmd == "/subs":
                push_command_event("/subs")
                config["embed_subs"] = not config.get("embed_subs", False)
                save_config()
                state = "enabled" if config["embed_subs"] else "disabled"
                console.print(f"[green][+] Subtitle extraction {state}.[/]")
                continue

            if lower_cmd == "/sort":
                push_command_event("/sort")
                config["auto_sort"] = not config.get("auto_sort", False)
                save_config()
                state = "enabled" if config["auto_sort"] else "disabled"
                console.print(f"[green][+] Auto-sorting by platform {state}.[/]")
                continue

            if lower_cmd.startswith("/trim "):
                parts = cmd[6:].strip().split(" ", 1)
                if len(parts) < 2:
                    console.print(
                        "[yellow]Usage: /trim <start>-<end> <url> (e.g. /trim 00:15-01:30 https://...)[/]"
                    )
                    continue
                trim_str, raw_url_text = parts[0], parts[1]
                url, extract_audio, force, req_quality = parse_download_text(raw_url_text)
                final_quality = req_quality or config.get("quality", "best")
                handle_download(
                    url,
                    extract_audio=extract_audio,
                    force=force,
                    quality=final_quality,
                    interactive=True,
                    trim_range=trim_str,
                )
                continue

            if lower_cmd.startswith("/setout "):
                push_command_event(cmd)
                new_dir = cmd[8:].strip()
                if new_dir:
                    config["output_dir"] = new_dir
                    save_config()
                    print(f"{GREEN}[+] Output directory updated to: {new_dir}{RESET}")
                else:
                    print(f"{RED}[!] Error: Please specify a folder path.{RESET}")
                continue

            if lower_cmd.startswith("/platform"):
                push_command_event(cmd)
                search_term = cmd[9:].strip()
                show_platforms(search_term)
                continue

            if lower_cmd.startswith("/batch "):
                push_command_event("/batch")
                filename = cmd[7:].strip()
                if not os.path.exists(filename):
                    print(f"{RED}[!] Error: Batch file '{filename}' not found.{RESET}")
                    continue
                with open(filename, encoding="utf-8") as f:
                    lines = [
                        line.strip() for line in f if line.strip() and not line.startswith("#")
                    ]

                print(f"\n[*] Found {len(lines)} URLs in {filename}.")
                # Rate limits have been removed as per user request.
                for idx, batch_url in enumerate(lines):
                    url, extract_audio, force, quality = parse_download_text(batch_url)
                    print(f"\n{BOLD}--- Batch Item {idx + 1}/{len(lines)} ---{RESET}")
                    handle_download(
                        url,
                        extract_audio=extract_audio,
                        force=force,
                        quality=quality,
                        interactive=False,
                    )
                continue

            if cmd.startswith("/"):
                if not (
                    lower_cmd.startswith("/audio ")
                    or lower_cmd.startswith("/video ")
                    or lower_cmd.startswith("/instagram ")
                ):
                    print(f"{YELLOW}[!] Unknown command: {cmd}. Type /help for assistance.{RESET}")
                    continue
                url, extract_audio, force, quality = parse_download_text(cmd)
                handle_download(url, extract_audio=extract_audio, force=force, quality=quality)
            else:
                if cmd.lower().startswith("http"):
                    print(
                        f"{YELLOW}[!] Direct URL detected. Use /video, /audio, or /instagram before the link."
                    )
                    print(f"    Example: /instagram {cmd}{RESET}")
                else:
                    print(
                        f"{YELLOW}[!] Unknown input: '{cmd}'. Type /help to see all commands.{RESET}"
                    )
                continue

        except KeyboardInterrupt:
            if is_downloading:
                print(
                    f"\n{YELLOW}[!] Download in progress. Exiting now might corrupt files. Please wait...{RESET}"
                )
            else:
                push_command_event(
                    "/exit"
                )  # Ctrl+C exit — log as command, no redundant session_end
                print_exit_screen(interrupted=True)
                break


app = typer.Typer(add_completion=True)


def _version_callback(value: bool) -> None:
    if value:
        from . import __version__

        console.print(f"pinak-cli {__version__}")
        raise typer.Exit()


def _install_ffmpeg_callback(value: bool) -> None:
    if value:
        from .ffmpeg_setup import install_ffmpeg_extra

        console.print("[cyan]Fetching a static FFmpeg build (pinak-cli[ffmpeg])...[/]")
        path = install_ffmpeg_extra()
        if path:
            console.print(f"[green][+] FFmpeg ready at: {path}[/]")
            raise typer.Exit()
        console.print(
            "[red][X] Automatic FFmpeg install failed.[/]\n"
            "[yellow]Manual options: install FFmpeg from https://ffmpeg.org/download.html "
            'and add it to PATH, or run: pip install "pinak-cli[ffmpeg]"[/]'
        )
        raise typer.Exit(code=1)


def _config_path_callback(value: bool) -> None:
    if value:
        console.print(f"Config file: {os.path.abspath(CONFIG_FILE)}")
        raise typer.Exit()


def maybe_print_offline_notice() -> bool:
    """Print an offline notice when the device has no internet. Returns online state."""
    from .utils import is_online

    if is_online():
        return True
    print_offline_notice()
    return False


@app.command()
def main(
    url: str | None = typer.Argument(None, help="The URL to download from"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output directory"),
    force: bool = typer.Option(False, "--force", help="Force download despite duplicates"),
    audio: bool = typer.Option(False, "--audio", help="Extract audio directly as MP3"),
    quality: str | None = typer.Option(
        None, "--quality", help="Quality: best, worst, audio, 360p, 720p, 1080p"
    ),
    doctor: bool = typer.Option(False, "--doctor", help="Run environment checks and exit"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose debug output"),
    log_file: str | None = typer.Option(
        None, "--log-file", help="Write detailed logs to this file"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be downloaded without downloading"
    ),
    as_json: bool = typer.Option(
        False, "--json", help="Emit machine-readable JSON output (pairs with --dry-run)"
    ),
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        callback=_version_callback,
        is_eager=True,
        help="Show version and exit",
    ),
    install_ffmpeg: bool = typer.Option(
        False,
        "--install-ffmpeg",
        callback=_install_ffmpeg_callback,
        is_eager=True,
        help="Download a static FFmpeg build (pinak-cli[ffmpeg]) and exit",
    ),
    config_path: bool = typer.Option(
        False,
        "--config-path",
        callback=_config_path_callback,
        is_eager=True,
        help="Print the config file path and exit",
    ),
):
    init_config()
    init_db()
    # Persist CLI-level logging prefs so retries/errors also land in the file.
    if log_file:
        config["log_file"] = log_file
        save_config()
    setup_logging(verbose=verbose, log_file=log_file or config.get("log_file") or None)
    initialize_session()  # Generate session ID for telemetry even in single-command mode
    updater.start_background_update_check()
    maybe_print_offline_notice()

    has_args = bool(
        url
        or output
        or force
        or audio
        or quality
        or doctor
        or verbose
        or dry_run
        or as_json
        or log_file
    )
    # Testing tools like CliRunner don't mock sys.argv, so this is safer
    if has_args or (len(sys.argv) > 1 and "pytest" not in sys.argv[0]):
        from .commands.run import run_single

        raise typer.Exit(
            code=run_single(url, output, force, audio, quality, doctor, verbose, dry_run, as_json)
        )
    repl_loop()


def run_cli():
    app()


if __name__ == "__main__":
    run_cli()
