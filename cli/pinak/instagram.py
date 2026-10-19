import contextlib
import contextvars
import os
import re
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

import yt_dlp
from rich.console import Console
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeRemainingColumn,
)
from yt_dlp.utils import DownloadError, sanitize_filename

from .config import config as config  # Public compatibility for callers/tests patching settings.
from .engine import SilentProgress, active_setting, emit_message, emit_progress, in_engine
from .exceptions import (
    InstagramError,
    InstagramPrivateContentError,
    InstagramRateLimitedError,
)
from .logging_setup import get_logger
from .retry import backoff_delay
from .text_safety import safe_rich, safe_text
from .utils import (
    GREEN,
    RED,
    RESET,
    YELLOW,
    changed_files,
    ffmpeg_available,
    get_ffmpeg_path,
    get_file_snapshot,
    normalize_quality,
    video_format_for_quality,
)
from .utils import (
    sanitize_filename as safe_filename,
)

console = Console()
logger = get_logger("pinak.instagram")


def _console_print(*args, **kwargs):
    if not emit_message(*args):
        console.print(*args, **kwargs)


def _progress_factory(*args, **kwargs):
    return SilentProgress() if in_engine() else Progress(*args, **kwargs)


# Serializes status prints when carousel slides download concurrently.
_PRINT_LOCK = threading.Lock()


def _say(message: str, *, locked: bool = False) -> None:
    """Print a status line, optionally under the parallel-download lock."""
    if locked:
        with _PRINT_LOCK:
            _console_print(message)
    else:
        _console_print(message)


def _friendly_instagram_error(exc: Exception) -> InstagramError:
    text = f"{type(exc).__name__}: {exc}".lower()
    if "429" in text or "rate-limit" in text or "rate limit" in text or "too many requests" in text:
        return InstagramRateLimitedError(str(exc))
    if (
        "private" in text
        or "login required" in text
        or "not found" in text
        or "unavailable" in text
    ):
        return InstagramPrivateContentError(str(exc))
    return InstagramError(str(exc) or "Failed to download the Instagram content.")


# Module-level progress references so the yt-dlp hook can update them
_progress = None
_task_id = None


def _yt_dlp_hook(d):
    """yt-dlp progress hook — updates the rich progress bar for video downloads."""
    global _progress, _task_id
    if emit_progress(d):
        return
    if _progress is None or _task_id is None:
        return
    if d["status"] == "downloading":
        total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
        downloaded = d.get("downloaded_bytes", 0)
        fname = safe_rich(os.path.basename(d.get("filename", "")))[:24]
        if total > 0:
            _progress.update(
                _task_id,
                total=total,
                completed=downloaded,
                description=f"[cyan]Downloading: {fname}...",
            )
        else:
            _progress.update(
                _task_id,
                total=None,
                completed=downloaded,
                description=f"[cyan]Downloading: {fname}...",
            )
    elif d["status"] == "finished":
        _progress.update(_task_id, description="[green]Merging streams...")


def download_instagram_media(
    url, output_path, extract_audio=False, quality=None, filename_suffix=""
):
    """
    Downloads Instagram content (images, videos, reels, carousels).

    Leverages yt-dlp for extraction and video processing, and urllib for
    high-res image thumbnails. Embeds metadata into every downloaded file.
    """
    output_dir = Path(output_path)
    if active_setting("auto_sort", False):
        output_dir = output_dir / "Instagram"
    output_dir.mkdir(parents=True, exist_ok=True)

    app_dir = os.path.dirname(get_ffmpeg_path())

    from .downloader import (
        _resilience_opts,
    )  # late import to avoid cycle at module load

    ydl_opts = {
        "outtmpl": str(output_dir / f"%(id)s_%(title)s{filename_suffix}.%(ext)s"),
        "ignore_no_formats_error": True,
        "quiet": True,
        "no_warnings": True,
        "ffmpeg_location": app_dir,
        # FIX #2: register the progress hook so the rich bar updates
        "progress_hooks": [_yt_dlp_hook],
        **_resilience_opts(),
    }

    if extract_audio:
        ydl_opts["format"] = "bestaudio/best"
        ydl_opts["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": active_setting("audio_format", "mp3"),
                "preferredquality": str(active_setting("audio_quality", "192")),
            }
        ]
    else:
        ydl_opts["format"] = video_format_for_quality(
            normalize_quality(quality) or "best", has_ffmpeg=ffmpeg_available()
        )

    _console_print(f"\n[*] Extracting Instagram metadata for: [blue underline]{safe_rich(url)}[/]")

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False, process=False)
            if not info:
                raise RuntimeError("Could not retrieve post information. Make sure it is public.")

            metadata = extract_metadata(info)
            outcomes = _download_extracted_info(
                ydl, info, output_dir, filename_suffix, metadata, ydl_opts
            )

    except DownloadError as exc:
        friendly = _friendly_instagram_error(exc)
        _console_print(f"{RED}[X] {friendly}{RESET}")
        _console_print(f"{YELLOW}Tip: {friendly.hint}{RESET}")
        logger.debug("Instagram download failed for %s: %r", url, exc)
        raise friendly from exc

    new_files = [f for outcome in outcomes for f in outcome.get("files", [])]

    from .downloader import verify_files  # late import to avoid cycle at module load

    valid_files, bad_files = verify_files(new_files)
    errors: list = [outcome["error"] for outcome in outcomes if outcome.get("error")]
    if bad_files:
        errors.append(f"Integrity check failed for {len(bad_files)} file(s): {bad_files}")
        _console_print(f"{YELLOW}[!] Warning: {errors[-1]}{RESET}")

    return {
        "success": len(valid_files) > 0 and not errors,
        "partial": bool(valid_files) and bool(errors),
        "url": url,
        "audio": extract_audio,
        "quality": ("audio" if extract_audio else (quality or active_setting("quality", "best"))),
        "info": info,
        "files": valid_files,
        "errors": errors,
    }


def extract_metadata(info):
    """Extracts structured metadata from the yt-dlp info dictionary."""
    return {
        "id": info.get("id"),
        "title": info.get("title"),
        "description": info.get("description"),
        "uploader": info.get("uploader"),
        "uploader_id": info.get("uploader_id"),
        "upload_date": info.get("upload_date"),
        "timestamp": info.get("timestamp"),
        "like_count": info.get("like_count"),
        "comment_count": info.get("comment_count"),
        "webpage_url": info.get("webpage_url"),
    }


def _download_extracted_info(ydl, info, output_dir, filename_suffix, metadata, ydl_opts=None):
    """Processes the extracted info dictionary and downloads each entry.

    Carousel slides are downloaded concurrently (bounded thread pool) when
    ``ydl_opts`` is provided so each worker gets its own yt-dlp instance.
    Falls back to sequential downloads otherwise.
    """
    if info.get("_type") == "playlist":
        entries = [e for e in (info.get("entries") or []) if e]
        total = len(entries)
        _console_print(f"[*] Detected carousel post with {total} items.")
        if total > 1 and ydl_opts is not None:
            return _download_carousel_parallel(
                ydl_opts, entries, output_dir, filename_suffix, metadata
            )
        else:
            outcomes = []
            for index, entry in enumerate(entries, start=1):
                _console_print(f"\n[*] Processing slide {index}/{total}...")
                outcomes.append(
                    _download_entry(ydl, entry, output_dir, index, filename_suffix, metadata)
                )
            return outcomes

    return [_download_entry(ydl, info, output_dir, 1, filename_suffix, metadata)]


def _download_carousel_parallel(ydl_opts, entries, output_dir, filename_suffix, metadata):
    """Download carousel slides concurrently (max 3 workers).

    Each worker builds its own ``YoutubeDL`` (yt-dlp instances are not
    thread-safe) without the shared rich progress hook; status lines are
    serialized through a lock.
    """
    total = len(entries)
    workers = max(1, min(3, total))
    _console_print(f"[*] Downloading {total} slides with {workers} parallel workers...")
    # The shared rich progress hook is not thread-safe — workers go without it.
    worker_opts = {k: v for k, v in ydl_opts.items() if k != "progress_hooks"}
    if in_engine():
        worker_opts["progress_hooks"] = [_yt_dlp_hook]
    before = get_file_snapshot(str(output_dir))

    def _work(item):
        index, entry = item
        _say(f"\n[*] Processing slide {index}/{total}...", locked=True)
        try:
            with yt_dlp.YoutubeDL(dict(worker_opts)) as worker_ydl:
                return _download_entry(
                    worker_ydl,
                    entry,
                    output_dir,
                    index,
                    filename_suffix,
                    metadata,
                    show_progress=False,
                    use_lock=True,
                    defer_embed=True,
                )
        except Exception as exc:
            _say(f"{RED}[X] Error downloading slide {index}: {exc}{RESET}", locked=True)
            logger.debug("Parallel slide %d failed: %r", index, exc)
            return {"files": [], "error": f"Slide {index}: {exc}"}

    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="pinak-slide") as pool:
        futures = [
            pool.submit(contextvars.copy_context().run, _work, item)
            for item in enumerate(entries, start=1)
        ]
        outcomes = [future.result() for future in futures]

    # Single metadata pass: per-entry snapshots would otherwise see (and
    # re-tag) sibling threads' files.
    for f in changed_files(before, get_file_snapshot(str(output_dir))):
        f_path = Path(f)
        if f_path.suffix.lower() in (".mp4", ".mkv", ".webm", ".avi", ".m4v"):
            embed_metadata_in_video(f_path, metadata)
    return outcomes


# ---------------------------------------------------------------------------
# FIX #8: build the EXIF object without touching the file on disk.
#          This lets _download_entry() do conversion + EXIF in ONE save call.
# ---------------------------------------------------------------------------
def _build_image_exif(metadata):
    """
    Builds a fresh Pillow EXIF object with the requested property mappings.
    Returns an Image.Exif instance (or None if Pillow is unavailable).
    """
    try:
        from PIL import Image

        exif = Image.Exif()

        id_val = metadata.get("id") or ""
        desc_val = metadata.get("description") or ""
        uploader_val = metadata.get("uploader") or ""
        url_val = metadata.get("webpage_url") or ""
        title_val = metadata.get("title") or id_val
        comment_val = f"Description: {desc_val}\nURL: {url_val}"

        # 1. Title -> Title
        exif[270] = title_val  # ImageDescription
        exif[40091] = title_val.encode("utf-16le")  # XPTitle

        # 2. Description -> Subtitle (XPSubject)
        exif[40095] = desc_val.encode("utf-16le")

        # 3. Uploader -> Contributing Artist
        exif[315] = uploader_val  # Artist
        exif[40093] = uploader_val.encode("utf-16le")  # XPAuthor

        # 4. Webpage URL -> Copyright
        exif[33432] = url_val

        # 5. Comment -> XPComment + UserComment
        exif[40092] = comment_val.encode("utf-16le")  # XPComment

        # FIX #5: use UNICODE prefix + utf-16le for non-ASCII text
        if comment_val.isascii():
            exif[37510] = b"ASCII\x00\x00\x00" + comment_val.encode("ascii")
        else:
            exif[37510] = b"UNICODE\x00" + comment_val.encode("utf-16le")

        return exif
    except Exception:
        return None


def embed_metadata_in_video(file_path, metadata):
    """
    Embeds metadata into video files.

    Step 1: FFmpeg lossless copy to strip old tags and write base tags.
    Step 2: mutagen writes Apple iTunes atoms for Publisher/Subtitle
            (required for Windows Explorer Details tab visibility).
    """
    ffmpeg_path = get_ffmpeg_path()
    file_path = Path(file_path)
    with tempfile.NamedTemporaryFile(
        dir=file_path.parent, suffix=file_path.suffix, delete=False
    ) as staged:
        temp_path = Path(staged.name)

    desc_val = metadata.get("description") or ""
    url_val = metadata.get("webpage_url") or ""
    comment_val = f"Description: {desc_val}\nURL: {url_val}"

    cmd = [
        ffmpeg_path,
        "-y",
        "-i",
        str(file_path),
        "-map_metadata",
        "-1",
        "-codec",
        "copy",
        "-metadata",
        f"title={metadata.get('title') or ''}",
        "-metadata",
        f"artist={metadata.get('uploader') or ''}",
        "-metadata",
        f"comment={comment_val}",
        str(temp_path),
    ]
    try:
        from .subproc import run_cmd

        run_cmd(cmd, timeout=120.0, check=True)
        if temp_path.is_file() and temp_path.stat().st_size > 0:
            os.replace(temp_path, file_path)

            ext = file_path.suffix.lower()
            if ext in (".mp4", ".m4v", ".mov"):
                try:
                    from mutagen.mp4 import MP4

                    video = MP4(file_path)

                    id_val = metadata.get("id") or ""
                    uploader_val = metadata.get("uploader") or ""
                    title_val = metadata.get("title") or ""

                    video["©nam"] = [title_val or id_val]
                    video["©ART"] = [uploader_val]
                    video["©pub"] = [title_val]
                    video["----:com.apple.iTunes:PUBLISHER"] = [title_val.encode("utf-8")]
                    video["desc"] = [desc_val]
                    video["©snt"] = [desc_val]
                    video["----:com.apple.iTunes:SUBTITLE"] = [desc_val.encode("utf-8")]
                    video["cprt"] = [url_val]
                    video["----:com.apple.iTunes:Copyright"] = [url_val.encode("utf-8")]
                    video["©cmt"] = [comment_val]
                    video["----:com.apple.iTunes:COMMENT"] = [comment_val.encode("utf-8")]

                    allowed_keys = (
                        "©nam",
                        "©ART",
                        "©pub",
                        "----:com.apple.iTunes:PUBLISHER",
                        "desc",
                        "©snt",
                        "----:com.apple.iTunes:SUBTITLE",
                        "cprt",
                        "----:com.apple.iTunes:Copyright",
                        "©cmt",
                        "----:com.apple.iTunes:COMMENT",
                        "©too",
                    )
                    for key in list(video.keys()):
                        if key not in allowed_keys:
                            del video[key]

                    video.save()
                except Exception as e:
                    _console_print(
                        f"{YELLOW}[!] Warning: Mutagen tagging failed, "
                        f"falling back to FFmpeg tags: {e}{RESET}"
                    )

            _console_print(f"{GREEN}[+] Embedded properties inside video: {file_path.name}{RESET}")
            return True
    except Exception as e:
        if temp_path.exists():
            with contextlib.suppress(OSError):
                os.remove(temp_path)
        _console_print(
            f"{YELLOW}[!] Warning: Could not embed metadata in video {file_path.name}: {e}{RESET}"
        )
    return False


def _download_entry(
    ydl,
    entry,
    output_dir,
    index,
    filename_suffix,
    metadata,
    show_progress=True,
    use_lock=False,
    defer_embed=False,
):
    """
    Resolves a single entry and downloads it as video or image.
    All image slides are saved as high-quality JPEG with EXIF in one pass.

    ``show_progress=False`` skips the live rich progress bar (used by parallel
    workers, where a shared live display would race); ``use_lock=True``
    serializes status prints across worker threads; ``defer_embed=True``
    skips the per-entry metadata pass (the parallel driver embeds once).
    """
    global _progress, _task_id

    resolved = _resolve_entry(ydl, entry)
    if not resolved:
        _say(
            f"{RED}[X] Could not resolve entry at slide {index}.{RESET}",
            locked=use_lock,
        )
        return {"files": [], "error": f"Could not resolve slide {index}"}

    if resolved.get("_type") == "playlist":
        nested = _download_extracted_info(ydl, resolved, output_dir, filename_suffix, metadata)
        return {
            "files": [f for item in nested for f in item.get("files", [])],
            "error": "; ".join(item["error"] for item in nested if item.get("error")),
        }

    post_id = safe_filename(str(resolved.get("id") or f"item_{index}"))
    before = get_file_snapshot(str(output_dir))

    is_video = _has_video_formats(resolved)
    created_files = []
    entry_error = ""

    if is_video:
        # FIX #2: wrap video download in a rich progress bar (sequential mode only)
        _say(f"[*] Slide {index} contains video content. Downloading...", locked=use_lock)
        try:
            process_fn = None
            for fn_name in ("process_video_result", "process_ie_result"):
                candidate = getattr(ydl, fn_name, None)
                if callable(candidate):
                    process_fn = candidate
                    break
            if show_progress:
                with _progress_factory(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    DownloadColumn(),
                    TimeRemainingColumn(),
                    console=console,
                ) as progress:
                    _progress = progress
                    _task_id = progress.add_task("[cyan]Starting video download...", total=None)
                    if process_fn:
                        process_fn(resolved, download=True)
                    else:
                        ydl.download([resolved.get("webpage_url") or resolved.get("url")])
                    _progress = None
                    _task_id = None
            else:
                if process_fn:
                    process_fn(resolved, download=True)
                else:
                    ydl.download([resolved.get("webpage_url") or resolved.get("url")])
            _say(
                f"{GREEN}[+] Slide {index} downloaded successfully.{RESET}",
                locked=use_lock,
            )
        except Exception as e:
            entry_error = f"Video slide {index}: {e}"
            _progress = None
            _task_id = None
            _say(
                f"{RED}[X] Error downloading video slide {index}: {safe_text(e)}{RESET}",
                locked=use_lock,
            )
    else:
        # Image slide
        thumbnail_url = _best_thumbnail_url(resolved)
        if not thumbnail_url:
            _say(
                f"{RED}[X] No downloadable media found for slide {index}.{RESET}",
                locked=use_lock,
            )
            return {"files": [], "error": f"No image available for slide {index}"}

        filename = _image_filename(resolved, output_dir, index, filename_suffix)
        _say(
            f"[*] Slide {index} contains image content. Fetching image...",
            locked=use_lock,
        )

        with tempfile.NamedTemporaryFile(dir=output_dir, suffix=".tmp", delete=False) as download:
            temp_img_path = Path(download.name)
        staged_image = None
        try:
            # FIX #3: retry image download
            _download_binary_with_retry(thumbnail_url, temp_img_path, resolved.get("http_headers"))

            # FIX #8: convert + embed EXIF in a SINGLE save — no second open/save
            from PIL import Image as PILImage

            with PILImage.open(temp_img_path) as raw:
                if raw.width * raw.height > 32_000_000:
                    raise ValueError("Image exceeds the decode budget")
                with raw.convert("RGB") as img:
                    exif = _build_image_exif(metadata)
                    save_kwargs = {"format": "JPEG", "quality": 95}
                    if exif is not None:
                        save_kwargs["exif"] = exif
                    with tempfile.NamedTemporaryFile(
                        dir=output_dir, suffix=".jpg", delete=False
                    ) as staging:
                        staged_image = Path(staging.name)
                    img.save(staged_image, **save_kwargs)
            os.replace(staged_image, filename)
            created_files = [str(filename)]

            with contextlib.suppress(OSError):
                os.remove(temp_img_path)

            _say(
                f"{GREEN}[+] Image saved as JPG: {filename.name}{RESET}",
                locked=use_lock,
            )
        except Exception as e:
            entry_error = f"Image slide {index}: {e}"
            if staged_image:
                with contextlib.suppress(OSError):
                    staged_image.unlink()
            with contextlib.suppress(OSError):
                os.remove(temp_img_path)
            _say(
                f"{RED}[X] Error downloading image slide {index}: {safe_text(e)}{RESET}",
                locked=use_lock,
            )
        finally:
            temp_img_path.unlink(missing_ok=True)
            if staged_image:
                staged_image.unlink(missing_ok=True)

    if defer_embed:
        new_files = changed_files(before, get_file_snapshot(str(output_dir)))
        if is_video:
            created_files = [
                f
                for f in new_files
                if Path(f).stem == post_id or Path(f).stem.startswith(post_id + "_")
            ]
        from .downloader import verify_files

        valid, _ = verify_files(created_files)
        return {
            "files": valid,
            "error": entry_error or ("" if valid else f"Slide {index} produced no media"),
        }

    # Snapshot diff — find newly created files
    after = get_file_snapshot(str(output_dir))
    new_files = changed_files(before, after)
    if is_video:
        created_files = [
            f
            for f in new_files
            if Path(f).stem == post_id or Path(f).stem.startswith(post_id + "_")
        ]

    # Embed metadata into video files (images are handled above inline)
    for f in created_files:
        f_path = Path(f)
        if f_path.suffix.lower() in (".mp4", ".mkv", ".webm", ".avi", ".m4v"):
            embed_metadata_in_video(f_path, metadata)
    from .downloader import verify_files

    valid, _ = verify_files(created_files)
    return {
        "files": valid,
        "error": entry_error or ("" if valid else f"Slide {index} produced no media"),
    }


# ---------------------------------------------------------------------------
# FIX #4: increase resolution depth from 2 → 5 and warn if still unresolved
# ---------------------------------------------------------------------------
def _resolve_entry(ydl, entry):
    """
    Follows url/url_transparent references up to 5 levels deep to extract
    the underlying concrete media entry.
    """
    resolved = entry
    for _depth in range(5):
        if resolved.get("_type") in {"url", "url_transparent"} and resolved.get("url"):
            try:
                next_entry = ydl.extract_info(resolved["url"], download=False, process=False)
                if next_entry:
                    resolved = next_entry
                    continue
            except Exception:
                pass
        break
    else:
        # Loop exhausted without breaking — still unresolved after 5 hops
        _console_print(
            f"{YELLOW}[!] Warning: Entry resolution exceeded 5 levels and may be incomplete.{RESET}"
        )
    return resolved


def _has_video_formats(info):
    """Checks if there are any valid video formats inside the info dict."""
    for fmt in info.get("formats") or []:
        if fmt.get("url") and fmt.get("vcodec") not in (None, "none"):
            return True
    return False


# ---------------------------------------------------------------------------
# FIX #9: sort thumbnails by actual pixel area (width x height)
# ---------------------------------------------------------------------------
def _is_direct_image_url(url: str | None) -> bool:
    """Checks whether a URL points directly to an image asset rather than a post page."""
    if not url or not isinstance(url, str):
        return False
    if not url.startswith(("http://", "https://")):
        return False
    lower = url.lower()
    for segment in ("/p/", "/reel/", "/reels/", "/tv/", "/stories/"):
        if segment in lower and "cdninstagram.com" not in lower and "fbcdn.net" not in lower:
            return False
    return True


def _infer_area_from_url(url: str) -> int:
    """Extracts pixel area from dimensions embedded in Instagram CDN URL paths."""
    if not url:
        return 0
    dim_match = re.search(r"[/_ps]?(\d{3,4})x(\d{3,4})", url)
    if dim_match:
        try:
            return int(dim_match.group(1)) * int(dim_match.group(2))
        except (ValueError, TypeError):
            pass
    width_match = re.search(r"[/_](\d{3,4})w[/_.]", url)
    if width_match:
        try:
            w = int(width_match.group(1))
            return w * w
        except (ValueError, TypeError):
            pass
    return 0


def _best_thumbnail_url(entry: dict) -> str | None:
    """Returns the URL of the highest-resolution image available for an entry.

    Prioritizes:
    1. Direct master display URL (`display_url`) when present.
    2. Candidates from `thumbnails`, `formats`, `url`, and `thumbnail`, ranked
       by explicit pixel area (width x height), regex-inferred dimensions from
       Instagram CDN paths, and list position (preferring later candidates).
    """
    if not entry or not isinstance(entry, dict):
        return None

    display_url = entry.get("display_url")
    if _is_direct_image_url(display_url):
        display_area = _infer_area_from_url(display_url) or (1080 * 1080)
    else:
        display_url = None
        display_area = 0

    candidates: list[tuple[int, int, str]] = []  # (area, index, url)
    candidate_urls: set[str] = set()

    def add_candidate(
        url: str | None,
        width: object = None,
        height: object = None,
        idx: int = 0,
        default_area: int = 0,
    ) -> None:
        if not _is_direct_image_url(url) or url in candidate_urls:
            return
        candidate_urls.add(url)  # type: ignore[arg-type]
        area = 0
        try:
            w = int(width) if width is not None else 0  # type: ignore[arg-type]
            h = int(height) if height is not None else 0  # type: ignore[arg-type]
            if w > 0 and h > 0:
                area = w * h
        except (ValueError, TypeError):
            area = 0

        if area == 0:
            area = _infer_area_from_url(url)  # type: ignore[arg-type]
        if area == 0:
            area = default_area

        candidates.append((area, idx, url))  # type: ignore[arg-type]

    # Add display_url if valid
    if display_url:
        add_candidate(display_url, idx=999, default_area=display_area)

    # Add items from thumbnails list (yt-dlp lists them in ascending order of quality)
    raw_thumbnails = entry.get("thumbnails") or []
    for idx, thumb in enumerate(raw_thumbnails):
        if isinstance(thumb, dict):
            add_candidate(
                thumb.get("url"),
                width=thumb.get("width"),
                height=thumb.get("height"),
                idx=idx,
                default_area=idx,
            )

    # Add items from formats (for image formats if present)
    for idx, fmt in enumerate(entry.get("formats") or []):
        if isinstance(fmt, dict) and fmt.get("vcodec") in (None, "none"):
            add_candidate(
                fmt.get("url"),
                width=fmt.get("width"),
                height=fmt.get("height"),
                idx=idx,
            )

    # Add single entry url if it points directly to an image asset
    entry_url = entry.get("url")
    if _is_direct_image_url(entry_url) and not _has_video_formats(entry):
        add_candidate(entry_url, idx=100, default_area=1080 * 1080)

    # Add fallback thumbnail
    fallback_thumb = entry.get("thumbnail")
    if _is_direct_image_url(fallback_thumb):
        add_candidate(fallback_thumb, idx=50, default_area=0)

    if not candidates:
        return None

    # Sort by area descending, then list index descending (later elements preferred on ties)
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return candidates[0][2]


def _image_filename(entry, output_dir, index, filename_suffix):
    """
    Constructs a sanitized .jpg filename.
    Format: <index:02d>_<post_id>_<sanitized_title><suffix>.jpg
    """
    post_id = safe_filename(str(entry.get("id") or f"item_{index}"))
    title = sanitize_filename(
        entry.get("title") or entry.get("id") or f"item_{index}", restricted=True
    )
    return (
        output_dir
        / f"{index:02d}_{post_id}_{title}{safe_filename(filename_suffix) if filename_suffix else ''}.jpg"
    )


# ---------------------------------------------------------------------------
# FIX #3: retry wrapper  |  FIX #10: 30-second timeout on urlopen
# ---------------------------------------------------------------------------
def _download_binary_with_retry(url, output_file, headers=None):
    """
    Downloads a binary file with timeout and exponential-backoff retry.

    Retries up to config['retry_count'] times (default 3) with
    exponential backoff + jitter between attempts.
    """
    try:
        max_attempts = max(1, int(active_setting("retry_count", 3)))
    except (TypeError, ValueError):
        max_attempts = 3
    try:
        timeout = float(active_setting("read_timeout", 30))
    except (TypeError, ValueError):
        timeout = 30.0
    default_headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Sec-Fetch-Dest": "image",
        "Sec-Fetch-Mode": "no-cors",
        "Sec-Fetch-Site": "cross-site",
    }
    if not (url.startswith("https://") or url.startswith("http://")):
        raise ValueError(f"Unsupported or unsafe URL scheme: {url}")

    request_headers = {**default_headers, **(headers or {})}
    request = Request(url, headers=request_headers)

    last_exc = None
    for attempt in range(1, max_attempts + 1):
        try:
            # Media thumbnail URL resolved by yt-dlp; core downloader behavior.
            response = urlopen(request, timeout=timeout)  # nosec B310
            with response, open(output_file, "wb") as file_obj:
                transferred = 0
                deadline = time.monotonic() + timeout
                while True:
                    if time.monotonic() > deadline:
                        raise TimeoutError("Image transfer exceeded its deadline")
                    chunk = response.read(64 * 1024)
                    if not chunk:
                        break
                    transferred += len(chunk)
                    if transferred > 32 * 1024 * 1024:
                        raise ValueError("Image transfer exceeds the 32 MiB limit")
                    file_obj.write(chunk)
            return  # success
        except (URLError, OSError) as exc:
            last_exc = exc
            if attempt < max_attempts:
                wait = backoff_delay(attempt, base=2.0, cap=30.0)
                _console_print(
                    f"{YELLOW}[~] Image download attempt {attempt}/{max_attempts} failed "
                    f"({exc}). Retrying in {wait}s...{RESET}"
                )
                time.sleep(wait)

    raise RuntimeError(
        f"Image download failed after {max_attempts} attempt(s): {last_exc}. "
        "Check your connection and retry. Use --log-file for details."
    ) from last_exc
