import contextlib
import datetime
import os
import time

import yt_dlp
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeRemainingColumn,
)
from rich.table import Table

from .config import config
from .exceptions import (
    DownloadFailedError,
    FFmpegNotFoundError,
    InstagramError,
    InvalidQualityError,
    InvalidURLError,
    NetworkError,
    OutputDirError,
)
from .history import record_download, url_downloaded_successfully
from .instagram import download_instagram_media
from .logging_setup import get_logger
from .notify import notify, print_instagram_notice
from .retry import backoff_delay, is_retryable
from .utils import (
    GREEN,
    RED,
    RESET,
    YELLOW,
    changed_files,
    ffmpeg_available,
    get_ffmpeg_path,
    get_file_snapshot,
    get_platform,
    has_embedded_subtitle,
    has_embedded_thumbnail,
    human_duration,
    human_size,
    is_online,
    normalize_quality,
    video_format_for_quality,
)

console = Console()
logger = get_logger("pinak.downloader")
is_downloading = False
rich_progress = None
rich_task = None


def _socket_timeout() -> float:
    """Separate connect/read timeouts: yt-dlp gets the read timeout."""
    try:
        return float(config.get("read_timeout", 30))
    except (TypeError, ValueError):
        return 30.0


def _connect_timeout() -> float:
    try:
        return float(config.get("connect_timeout", 10))
    except (TypeError, ValueError):
        return 10.0


def _retry_count() -> int:
    try:
        return max(1, int(config.get("retry_count", 3)))
    except (TypeError, ValueError):
        return 3


def _resilience_opts() -> dict:
    """yt-dlp options for resume + retries + timeouts.

    - ``continuedl`` keeps partial files so retries *resume* instead of restarting.
    - ``retries``/``fragment_retries`` handle transient segment failures.
    - ``socket_timeout`` prevents infinite hangs.
    """
    retries = _retry_count()
    return {
        "continuedl": True,
        "retries": retries,
        "fragment_retries": retries,
        "skip_unavailable_fragments": True,
        "socket_timeout": _socket_timeout(),
        "nocheckcertificate": False,
    }


def _classify_download_error(exc: Exception, url: str) -> Exception:
    """Map raw exceptions to actionable Pinak errors."""
    text = f"{type(exc).__name__}: {exc}".lower()
    if "instagram" in url.lower() or "instagram" in text:
        if "429" in text or "rate" in text:
            from .exceptions import InstagramRateLimitedError

            return InstagramRateLimitedError(
                str(exc),
                hint=InstagramRateLimitedError.hint,
            )
        if "private" in text or "login required" in text or "not found" in text:
            from .exceptions import InstagramPrivateContentError

            return InstagramPrivateContentError(
                str(exc),
                hint=InstagramPrivateContentError.hint,
            )
        return InstagramError(str(exc))
    if is_retryable(exc) or "urlopen" in text or "network" in text:
        return NetworkError(str(exc))
    return DownloadFailedError(str(exc) or f"Failed to download {url}")


def verify_files(files: list) -> tuple:
    """Integrity check: keep only files that exist and are non-empty.

    Returns ``(valid, problems)``. Guards against silent partial/corrupt
    downloads being recorded as successes.
    """
    valid: list = []
    problems: list = []
    for path in files or []:
        try:
            if os.path.exists(path) and os.path.getsize(path) > 0:
                valid.append(path)
            else:
                problems.append(path)
        except OSError:
            problems.append(path)
    return valid, problems


class YTDLLogger:
    def __init__(self):
        self.errors = []

    def debug(self, msg):
        pass

    def warning(self, msg):
        pass

    def error(self, msg):
        self.errors.append(msg)


def yt_dlp_progress_hook(d):
    global rich_progress, rich_task
    if rich_progress and rich_task is not None:
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes", 0)

            filename = os.path.basename(d.get("filename", "Unknown"))
            if total > 0:
                rich_progress.update(
                    rich_task,
                    total=total,
                    completed=downloaded,
                    description=f"[cyan]Downloading: {filename[:20]}...",
                )
            else:
                rich_progress.update(
                    rich_task,
                    total=None,
                    completed=downloaded,
                    description=f"[cyan]Downloading: {filename[:20]}...",
                )

        elif d["status"] == "finished":
            rich_progress.update(rich_task, description="[green]Finished stream, processing...")


def print_download_summary(result):
    files = result.get("files", [])
    info = result.get("info") or {}

    if result.get("canceled"):
        status_color = "bold yellow"
        status_text = "CANCELED"
        status_emoji = "⏹️"
    elif result.get("success"):
        status_color = "bold green"
        status_text = "SUCCESS"
        status_emoji = "✅"
    else:
        status_color = "bold red"
        status_text = "FAILED"
        status_emoji = "❌"

    from rich import box

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Property", style="cyan", justify="right")
    table.add_column("Value", style="magenta")

    table.add_row("🌐 Platform:", get_platform(result.get("url", "")))
    table.add_row("⚡ Status:", f"[{status_color}]{status_emoji} {status_text}[/]")

    # Determine True Mode & Quality
    is_audio = result.get("audio", False)
    if not is_audio and info.get("vcodec") == "none" and info.get("acodec") != "none":
        is_audio = True

    if is_audio:
        mode_str = "🎵 Audio"
        quality_str = (
            f"{config.get('audio_quality', '192')} kbps" if result.get("audio") else "best audio"
        )
    else:
        mode_str = "🎬 Video/Media"
        quality_str = result.get("quality", "best")

    table.add_row("🎛️ Mode:", mode_str)
    table.add_row("💎 Quality:", quality_str)

    # Determine Duration
    duration_val = info.get("duration")
    trim_range = result.get("trim_range")
    if trim_range:
        try:
            start_str, end_str = trim_range.split("-")

            def pt(t_str):
                s = 0
                for p in t_str.split(":"):
                    s = s * 60 + float(p)
                return s

            duration_val = pt(end_str) - pt(start_str)
        except Exception:
            pass

    table.add_row("⏱️ Duration:", human_duration(duration_val))

    if files:
        for path in files:
            size = human_size(os.path.getsize(path)) if os.path.exists(path) else "unknown"
            thumb = "embedded" if has_embedded_thumbnail(path) else "no"
            table.add_row("💾 Saved To:", f"[blue underline]{path}[/]")
            table.add_row("📏 File Size:", size)
            if path.lower().endswith((".mp3", ".m4a")):
                table.add_row("🖼️ Thumbnail:", thumb)
            if config.get("embed_subs", False) and not is_audio:
                subs = "embedded" if has_embedded_subtitle(path) else "no"
                table.add_row("💬 Subtitle:", subs)
    else:
        table.add_row("💾 Saved To:", "[yellow]no new file detected[/]")

    panel = Panel(
        table,
        title="[bold yellow]🔱 Download Summary 🔱[/bold yellow]",
        border_style="cyan",
        box=box.ROUNDED,
        expand=False,
    )
    console.print(panel)

    # Rate limits have been removed as per user request.


def download_instagram_content(
    post_url,
    target_dir,
    extract_audio=False,
    quality=None,
    filename_suffix="",
    trim_range=None,
):
    global is_downloading

    import urllib.parse

    parsed_url = urllib.parse.urlparse(post_url)
    query_params = urllib.parse.parse_qs(parsed_url.query)
    img_index = query_params.get("img_index", [None])[0]
    if not img_index:
        img_index = query_params.get("slide", [None])[0]

    # Reconstruct the URL without query parameters for the request (only for Instagram)
    if "instagram.com" in post_url.lower():
        clean_url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"
    else:
        clean_url = post_url

    auto_sort = config.get("auto_sort", False)
    if auto_sort:
        target_dir = f"{target_dir}/%(extractor_key)s"

    os.makedirs(target_dir.replace("/%(extractor_key)s", ""), exist_ok=True)
    logger = YTDLLogger()
    app_dir = os.path.dirname(get_ffmpeg_path())
    ffmpeg_path = get_ffmpeg_path()

    # Resolve exact path for snapshot
    actual_dir = target_dir
    if auto_sort:
        actual_dir = os.path.dirname(actual_dir)

    before_files = get_file_snapshot(actual_dir)
    chosen_quality = normalize_quality(quality or config.get("quality", "best")) or "best"
    audio_quality = str(config.get("audio_quality", "192"))
    suffix = f" {filename_suffix}" if filename_suffix else ""
    info = {}
    images_downloaded = 0

    ydl_opts = {
        "outtmpl": f"{target_dir}/%(title)s{suffix}.%(ext)s",
        "ignoreerrors": True,
        "quiet": True,
        "no_warnings": True,
        "logger": logger,
        "ffmpeg_location": app_dir,
        "progress_hooks": [yt_dlp_progress_hook],
        "postprocessors": [],
        **_resilience_opts(),
    }

    if img_index:
        ydl_opts["playlist_items"] = str(img_index)

    if trim_range:
        try:
            start_str, end_str = trim_range.split("-")

            def pt(t_str):
                s = 0
                for p in t_str.split(":"):
                    s = s * 60 + float(p)
                return s

            start_sec = pt(start_str)
            end_sec = pt(end_str)
            ydl_opts["download_ranges"] = yt_dlp.utils.download_range_func(
                None, [[start_sec, end_sec]]
            )
            suffix += f" (Trim {trim_range.replace(':', '.')})"
            ydl_opts["outtmpl"] = f"{target_dir}/%(title)s{suffix}.%(ext)s"
        except Exception as e:
            console.print(f"[yellow][!] Error parsing trim range: {e}. Downloading full file.[/]")

    if config.get("embed_subs", False) and not extract_audio:
        ydl_opts["writesubtitles"] = True
        ydl_opts["writeautomaticsub"] = True
        ydl_opts["subtitleslangs"] = ["en", "all"]
        ydl_opts["postprocessors"].append(
            {
                "key": "FFmpegSubtitlesConvertor",
                "format": "srt",
            }
        )
        ydl_opts["postprocessors"].append(
            {
                "key": "FFmpegEmbedSubtitle",
                "already_have_subtitle": False,
            }
        )

    ydl_opts["postprocessors"].append(
        {
            "key": "FFmpegMetadata",
            "add_metadata": True,
        }
    )

    if extract_audio:
        ydl_opts["format"] = "bestaudio/best"
        ydl_opts["writethumbnail"] = True
        ydl_opts["postprocessors"].insert(
            0,
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": config.get("audio_format", "mp3"),
                "preferredquality": audio_quality,
            },
        )
        ydl_opts["postprocessors"].append(
            {
                "key": "FFmpegThumbnailsConvertor",
                "format": "jpg",
            }
        )
        ydl_opts["postprocessors"].append(
            {
                "key": "EmbedThumbnail",
                "already_have_thumbnail": False,
            }
        )
        ydl_opts["postprocessor_args"] = {"ffmpeg": ["-id3v2_version", "3"]}
    else:
        ydl_opts["format"] = video_format_for_quality(chosen_quality)
        vid_fmt = config.get("video_format", "mp4")
        if vid_fmt:
            ydl_opts["merge_output_format"] = vid_fmt

    mode = "AUDIO" if extract_audio else "MEDIA"
    console.print(f"\n[*] Downloading [bold cyan]{mode}[/] from: [blue underline]{post_url}[/]")
    console.print(
        "[yellow]💡 Tip: Press [bold]Ctrl+C[/bold] at any time to cancel/stop the download.[/]"
    )
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            DownloadColumn(),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            global rich_progress, rich_task
            rich_progress = progress
            if trim_range:
                rich_task = progress.add_task(
                    f"[cyan]Downloading & Trimming ({trim_range})...", total=None
                )
            else:
                rich_task = progress.add_task("[cyan]Starting download...", total=100)

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                extracted = ydl.extract_info(clean_url, download=True)
                info = extracted if isinstance(extracted, dict) else {}

            rich_progress = None
            rich_task = None

            if extract_audio and info:
                audio_fmt = config.get("audio_format", "mp3")
                filename = ydl.prepare_filename(info)
                base = os.path.splitext(filename)[0]
                final_audio = base + f".{audio_fmt}"
                thumb_jpg = base + ".jpg"
                temp_audio = base + f"_temp.{audio_fmt}"

                if audio_fmt == "mp3" and os.path.exists(final_audio) and os.path.exists(thumb_jpg):
                    os.replace(final_audio, temp_audio)
                    ffmpeg_cmd = [
                        ffmpeg_path,
                        "-y",
                        "-i",
                        temp_audio,
                        "-i",
                        thumb_jpg,
                        "-map",
                        "0:0",
                        "-map",
                        "1:0",
                        "-c",
                        "copy",
                        "-id3v2_version",
                        "3",
                        "-metadata:s:v",
                        "title=Album cover",
                        "-metadata:s:v",
                        "comment=Cover (front)",
                        "-disposition:v:0",
                        "attached_pic",
                        final_audio,
                    ]
                    from .subproc import run_cmd

                    run_cmd(ffmpeg_cmd, timeout=120.0)
                    if os.path.exists(final_audio):
                        os.remove(temp_audio)
                        os.remove(thumb_jpg)
                    else:
                        os.replace(temp_audio, final_audio)

        after_files = get_file_snapshot(actual_dir)
        new_files = changed_files(before_files, after_files)
        # Integrity check: drop missing/empty files so corrupt partials
        # are never recorded as successes.
        valid_files, bad_files = verify_files(new_files)
        if bad_files:
            msg = f"Integrity check failed for {len(bad_files)} file(s): {bad_files}"
            logger.errors.append(msg)
            get_logger("pinak.downloader").warning("%s (url=%s)", msg, post_url)
            console.print(f"[yellow][!] Warning: {msg}[/]")
        new_files = valid_files
        success = bool(info or images_downloaded or new_files)
        if bad_files and not success:
            logger.errors.append("All downloaded files failed integrity verification.")

        if success:
            console.print("\n[bold green][+] Success! Process completed.[/]")
            title = info.get("title", "Media") if info else "Media"
            with contextlib.suppress(Exception):
                notify("PINAK-CLI", f"Successfully downloaded: {title}")
        else:
            console.print("\n[bold red][X] No downloadable media was found.[/]")

        return {
            "success": success,
            "url": post_url,
            "audio": extract_audio,
            "quality": "audio" if extract_audio else chosen_quality,
            "info": info,
            "files": new_files,
            "errors": logger.errors,
            "trim_range": trim_range,
        }
    except KeyboardInterrupt:
        # Keep partial files on disk so a later retry can *resume* via continuedl.
        console.print("\n[bold red][X] Download canceled by user.[/]")
        console.print(
            "[dim]Partial files were kept so you can resume by re-running the same command.[/]"
        )
        return {
            "success": False,
            "url": post_url,
            "audio": extract_audio,
            "quality": "audio" if extract_audio else chosen_quality,
            "info": {},
            "files": [],
            "errors": logger.errors + ["Canceled by user"],
            "trim_range": trim_range,
            "canceled": True,
        }
    except Exception as e:
        friendly = _classify_download_error(e, post_url)
        hint = getattr(friendly, "hint", str(e))
        console.print(f"[bold red][X][/] Error: {e}")
        console.print(f"[yellow]Tip: {hint}[/]")
        if isinstance(friendly, InstagramError):
            with contextlib.suppress(Exception):
                print_instagram_notice(str(e))
        get_logger("pinak.downloader").debug("Download failed for %s: %r", post_url, e)
        return {
            "success": False,
            "url": post_url,
            "audio": extract_audio,
            "quality": "audio" if extract_audio else chosen_quality,
            "info": {},
            "files": [],
            "errors": logger.errors + [str(e)],
            "trim_range": trim_range,
        }


def parse_download_text(text):
    raw = text.strip()
    force = False
    extract_audio = False
    quality = None

    if raw.lower().startswith("/audio "):
        extract_audio = True
        raw = raw[7:].strip()
    elif raw.lower().startswith("/video "):
        extract_audio = False
        raw = raw[7:].strip()
    elif raw.lower().startswith("/instagram "):
        extract_audio = False
        raw = raw[11:].strip()

    parts = raw.split()
    cleaned = []
    for idx, part in enumerate(parts):
        lower = part.lower()
        if lower == "--force":
            force = True
        elif lower == "--audio":
            extract_audio = True
        elif lower.startswith("--quality="):
            quality = lower.split("=", 1)[1]
        elif lower == "--quality" and idx + 1 < len(parts):
            quality = parts[idx + 1]
        elif idx > 0 and parts[idx - 1].lower() == "--quality":
            continue
        else:
            cleaned.append(part)

    url = " ".join(cleaned).strip()
    return url, extract_audio, force, quality


def handle_duplicate(url, interactive=True):
    action = str(config.get("duplicate_action", "ask")).lower()
    if not url_downloaded_successfully(url):
        return "download"
    if action in ("skip", "download", "rename"):
        return action
    if not interactive:
        return "download"
    console.print("[yellow][!] This URL is already in successful history.[/]")

    import questionary

    try:
        choice = questionary.select(
            "Choose action for duplicate URL:",
            choices=["Skip", "Download again", "Rename copy"],
        ).ask(kbi_msg="")
    except TypeError:
        choice = questionary.select(
            "Choose action for duplicate URL:",
            choices=["Skip", "Download again", "Rename copy"],
        ).ask()

    if not choice:
        return "download"

    choice_lower = choice.lower()
    if choice_lower.startswith("s"):
        return "skip"
    if choice_lower.startswith("r"):
        return "rename"
    return "download"


def handle_download(
    url,
    extract_audio=False,
    force=False,
    quality=None,
    interactive=True,
    trim_range=None,
):
    global is_downloading
    log = get_logger("pinak.downloader")
    if not is_online(timeout=_connect_timeout()):
        err = NetworkError("No internet connection detected.")
        print(f"{RED}[!] Error: {err}{RESET}")
        print(f"{YELLOW}Tip: {err.hint}{RESET}")
        log.debug("Offline — aborting download for %s", url)
        return {
            "success": False,
            "url": url,
            "files": [],
            "audio": extract_audio,
            "quality": quality or config.get("quality", "best"),
        }

    if not url.startswith("http"):
        err = InvalidURLError(f"Invalid URL: {url!r}")
        print(f"{RED}[!] Error: {err}{RESET}")
        print(f"{YELLOW}Tip: {err.hint}{RESET}")
        return {
            "success": False,
            "url": url,
            "files": [],
            "audio": extract_audio,
            "quality": quality or config.get("quality", "best"),
        }

    if quality is not None and normalize_quality(quality) is None:
        err = InvalidQualityError(f"Invalid quality: {quality!r}")
        print(f"{RED}[!] Error: {err}{RESET}")
        print(f"{YELLOW}Tip: {err.hint}{RESET}")
        return {
            "success": False,
            "url": url,
            "files": [],
            "audio": extract_audio,
            "quality": quality,
        }

    if not ffmpeg_available():
        from .ffmpeg_setup import ensure_ffmpeg

        fetched = ensure_ffmpeg()
        if not ffmpeg_available():
            err = FFmpegNotFoundError("ffmpeg binary not found.")
            print(f"{YELLOW}[!] Warning: {err}{RESET}")
            print(f"{YELLOW}Tip: {err.hint}{RESET}")
            log.warning("ffmpeg not found; continuing — merging/conversion may fail")
        else:
            log.info("ffmpeg provisioned via fallback: %s", fetched)

    detected_platform = get_platform(url)
    if detected_platform == "Unknown":
        print(
            f"{YELLOW}[!] Notice: The URL does not match any officially supported platform.{RESET}"
        )
        print(f"    You can use the /platform command to see valid platforms.{RESET}")
    else:
        print(f"{GREEN}[*] Detected Platform: {detected_platform}{RESET}")

    # Rate limits have been removed as per user request.

    duplicate_action = handle_duplicate(url, interactive=interactive)
    if duplicate_action == "skip":
        print(f"{YELLOW}[!] Skipped duplicate URL.{RESET}")
        return {
            "success": True,
            "url": url,
            "files": [],
            "audio": extract_audio,
            "quality": quality or config.get("quality", "best"),
        }

    filename_suffix = ""
    if duplicate_action == "rename":
        filename_suffix = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")

    retries = _retry_count()
    result = {
        "success": False,
        "url": url,
        "files": [],
        "audio": extract_audio,
        "quality": quality or config.get("quality", "best"),
    }

    output_dir = str(config.get("output_dir", "downloads"))
    try:
        os.makedirs(output_dir, exist_ok=True)
    except OSError as exc:
        err = OutputDirError(str(exc))
        print(f"{RED}[!] Error: {err}{RESET}")
        print(f"{YELLOW}Tip: {err.hint}{RESET}")
        return {
            "success": False,
            "url": url,
            "files": [],
            "audio": extract_audio,
            "quality": quality or config.get("quality", "best"),
        }

    for attempt in range(1, retries + 1):
        if attempt > 1:
            wait = backoff_delay(attempt - 1, base=2.0, cap=30.0)
            print(
                f"{YELLOW}[~] Retry {attempt}/{retries} after {wait}s (exponential backoff)...{RESET}"
            )
            log.debug("Retry %d/%d for %s after %.1fs", attempt, retries, url, wait)
            try:
                time.sleep(wait)
            except KeyboardInterrupt:
                print(f"\n{RED}[!] Cancelled during retry wait.{RESET}")
                result = {
                    "success": False,
                    "url": url,
                    "files": [],
                    "audio": extract_audio,
                    "quality": quality or config.get("quality", "best"),
                    "canceled": True,
                }
                break
        is_downloading = True
        try:
            if detected_platform == "Instagram":
                result = download_instagram_media(
                    url,
                    output_dir,
                    extract_audio=extract_audio,
                    quality=quality,
                    filename_suffix=filename_suffix,
                )

            else:
                result = download_instagram_content(
                    url,
                    output_dir,
                    extract_audio=extract_audio,
                    quality=quality,
                    filename_suffix=filename_suffix,
                    trim_range=trim_range,
                )
        except KeyboardInterrupt:
            is_downloading = False
            print(f"\n{RED}[!] Download canceled by user.{RESET}")
            result = {
                "success": False,
                "url": url,
                "files": [],
                "audio": extract_audio,
                "quality": quality or config.get("quality", "best"),
                "canceled": True,
            }
            break
        is_downloading = False
        if result.get("success") or result.get("canceled"):
            break

    # Calculate actual duration of trimmed range
    duration = 0
    info = result.get("info") or {}
    if result.get("success"):
        duration = info.get("duration") or 0
        if trim_range:
            try:
                start_str, end_str = trim_range.split("-")

                def pt(t_str):
                    s = 0
                    for p in t_str.split(":"):
                        s = s * 60 + float(p)
                    return s

                duration = int(pt(end_str) - pt(start_str))
            except Exception:
                pass

    status_val = (
        "canceled" if result.get("canceled") else ("success" if result.get("success") else "failed")
    )
    record_download(
        url,
        status_val,
        mode=(
            "audio"
            if extract_audio or (info.get("vcodec") == "none" and info.get("acodec") != "none")
            else "media"
        ),
        files=result.get("files", []),
        quality=result.get("quality"),
        duration=duration,
        is_forced=force,
    )
    print_download_summary(result)
    return result
