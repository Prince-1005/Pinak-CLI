import contextlib
import os
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

from .config import config
from .exceptions import (
    InstagramError,
    InstagramPrivateContentError,
    InstagramRateLimitedError,
)
from .logging_setup import get_logger
from .retry import backoff_delay
from .utils import (
    GREEN,
    RED,
    RESET,
    YELLOW,
    changed_files,
    get_ffmpeg_path,
    get_file_snapshot,
)

console = Console()
logger = get_logger("pinak.instagram")

# Serializes status prints when carousel slides download concurrently.
_PRINT_LOCK = threading.Lock()


def _say(message: str, *, locked: bool = False) -> None:
    """Print a status line, optionally under the parallel-download lock."""
    if locked:
        with _PRINT_LOCK:
            console.print(message)
    else:
        console.print(message)


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
    if _progress is None or _task_id is None:
        return
    if d["status"] == "downloading":
        total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
        downloaded = d.get("downloaded_bytes", 0)
        fname = os.path.basename(d.get("filename", ""))[:24]
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
    if config.get("auto_sort", False):
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
                "preferredcodec": config.get("audio_format", "mp3"),
                "preferredquality": str(config.get("audio_quality", "192")),
            }
        ]

    before_files = get_file_snapshot(str(output_dir))

    console.print(f"\n[*] Extracting Instagram metadata for: [blue underline]{url}[/]")

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False, process=False)
            if not info:
                raise RuntimeError("Could not retrieve post information. Make sure it is public.")

            metadata = extract_metadata(info)
            _download_extracted_info(ydl, info, output_dir, filename_suffix, metadata, ydl_opts)

    except DownloadError as exc:
        friendly = _friendly_instagram_error(exc)
        console.print(f"{RED}[X] {friendly}{RESET}")
        console.print(f"{YELLOW}Tip: {friendly.hint}{RESET}")
        logger.debug("Instagram download failed for %s: %r", url, exc)
        raise friendly from exc

    after_files = get_file_snapshot(str(output_dir))
    new_files = changed_files(before_files, after_files)

    from .downloader import verify_files  # late import to avoid cycle at module load

    valid_files, bad_files = verify_files(new_files)
    errors: list = []
    if bad_files:
        errors.append(f"Integrity check failed for {len(bad_files)} file(s): {bad_files}")
        console.print(f"{YELLOW}[!] Warning: {errors[-1]}{RESET}")

    return {
        "success": len(valid_files) > 0,
        "url": url,
        "audio": extract_audio,
        "quality": ("audio" if extract_audio else (quality or config.get("quality", "best"))),
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
        console.print(f"[*] Detected carousel post with {total} items.")
        if total > 1 and ydl_opts is not None:
            _download_carousel_parallel(ydl_opts, entries, output_dir, filename_suffix, metadata)
        else:
            for index, entry in enumerate(entries, start=1):
                console.print(f"\n[*] Processing slide {index}/{total}...")
                _download_entry(ydl, entry, output_dir, index, filename_suffix, metadata)
        return

    _download_entry(ydl, info, output_dir, 1, filename_suffix, metadata)


def _download_carousel_parallel(ydl_opts, entries, output_dir, filename_suffix, metadata):
    """Download carousel slides concurrently (max 3 workers).

    Each worker builds its own ``YoutubeDL`` (yt-dlp instances are not
    thread-safe) without the shared rich progress hook; status lines are
    serialized through a lock.
    """
    total = len(entries)
    workers = max(1, min(3, total))
    console.print(f"[*] Downloading {total} slides with {workers} parallel workers...")
    # The shared rich progress hook is not thread-safe — workers go without it.
    worker_opts = {k: v for k, v in ydl_opts.items() if k != "progress_hooks"}
    before = get_file_snapshot(str(output_dir))

    def _work(item):
        index, entry = item
        _say(f"\n[*] Processing slide {index}/{total}...", locked=True)
        try:
            with yt_dlp.YoutubeDL(dict(worker_opts)) as worker_ydl:
                _download_entry(
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

    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="pinak-slide") as pool:
        list(pool.map(_work, list(enumerate(entries, start=1))))

    # Single metadata pass: per-entry snapshots would otherwise see (and
    # re-tag) sibling threads' files.
    for f in changed_files(before, get_file_snapshot(str(output_dir))):
        f_path = Path(f)
        if f_path.suffix.lower() in (".mp4", ".mkv", ".webm", ".avi", ".m4v"):
            embed_metadata_in_video(f_path, metadata)


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
    temp_path = file_path.with_name(f"temp_{file_path.name}")

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
        str(temp_path),
    ]
    try:
        from .subproc import run_cmd

        run_cmd(cmd, timeout=120.0, check=True)
        if temp_path.exists():
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
                    console.print(
                        f"{YELLOW}[!] Warning: Mutagen tagging failed, "
                        f"falling back to FFmpeg tags: {e}{RESET}"
                    )

            console.print(f"{GREEN}[+] Embedded properties inside video: {file_path.name}{RESET}")
            return True
    except Exception as e:
        if temp_path.exists():
            with contextlib.suppress(OSError):
                os.remove(temp_path)
        console.print(
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
        return

    if resolved.get("_type") == "playlist":
        _download_extracted_info(ydl, resolved, output_dir, filename_suffix, metadata)
        return

    post_id = resolved.get("id") or f"item_{index}"
    before = get_file_snapshot(str(output_dir))

    is_video = _has_video_formats(resolved)

    if is_video:
        # FIX #2: wrap video download in a rich progress bar (sequential mode only)
        _say(f"[*] Slide {index} contains video content. Downloading...", locked=use_lock)
        try:
            if show_progress:
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    DownloadColumn(),
                    TimeRemainingColumn(),
                    console=console,
                ) as progress:
                    _progress = progress
                    _task_id = progress.add_task("[cyan]Starting video download...", total=None)
                    ydl.process_ie_result(resolved, download=True)
                    _progress = None
                    _task_id = None
            else:
                ydl.process_ie_result(resolved, download=True)
            _say(
                f"{GREEN}[+] Slide {index} downloaded successfully.{RESET}",
                locked=use_lock,
            )
        except Exception as e:
            _progress = None
            _task_id = None
            _say(
                f"{RED}[X] Error downloading video slide {index}: {e}{RESET}",
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
            return

        filename = _image_filename(resolved, output_dir, index, filename_suffix)
        _say(
            f"[*] Slide {index} contains image content. Fetching image...",
            locked=use_lock,
        )

        temp_img_path = output_dir / f"temp_download_{index}_{post_id}.tmp"
        try:
            # FIX #3: retry image download
            _download_binary_with_retry(thumbnail_url, temp_img_path, resolved.get("http_headers"))

            # FIX #8: convert + embed EXIF in a SINGLE save — no second open/save
            from PIL import Image as PILImage

            img = PILImage.open(temp_img_path)
            if img.mode not in ("RGB",):
                img = img.convert("RGB")

            exif = _build_image_exif(metadata)
            # FIX #6: explicit quality=95 — never quality='keep' on converted images
            save_kwargs = {"format": "JPEG", "quality": 95}
            if exif is not None:
                save_kwargs["exif"] = exif
            img.save(filename, **save_kwargs)

            with contextlib.suppress(OSError):
                os.remove(temp_img_path)

            _say(
                f"{GREEN}[+] Image saved as JPG: {filename.name}{RESET}",
                locked=use_lock,
            )
        except Exception as e:
            with contextlib.suppress(OSError):
                os.remove(temp_img_path)
            _say(
                f"{RED}[X] Error downloading image slide {index}: {e}{RESET}",
                locked=use_lock,
            )

    if defer_embed:
        return

    # Snapshot diff — find newly created files
    after = get_file_snapshot(str(output_dir))
    new_files = changed_files(before, after)

    # Embed metadata into video files (images are handled above inline)
    for f in new_files:
        f_path = Path(f)
        if f_path.suffix.lower() in (".mp4", ".mkv", ".webm", ".avi", ".m4v"):
            embed_metadata_in_video(f_path, metadata)


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
        console.print(
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
# FIX #9: sort thumbnails by actual pixel area (width × height)
# ---------------------------------------------------------------------------
def _best_thumbnail_url(entry):
    """
    Returns the URL of the highest-resolution thumbnail available,
    sorted by width × height descending.
    """
    thumbnails = entry.get("thumbnails") or []

    def _area(t):
        w = t.get("width") or 0
        h = t.get("height") or 0
        return w * h

    for thumb in sorted(thumbnails, key=_area, reverse=True):
        url = thumb.get("url")
        if url:
            return url
    return entry.get("thumbnail")


def _image_filename(entry, output_dir, index, filename_suffix):
    """
    Constructs a sanitized .jpg filename.
    Format: <index:02d>_<post_id>_<sanitized_title><suffix>.jpg
    """
    post_id = entry.get("id") or f"item_{index}"
    title = sanitize_filename(
        entry.get("title") or entry.get("id") or f"item_{index}", restricted=True
    )
    return output_dir / f"{index:02d}_{post_id}_{title}{filename_suffix}.jpg"


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
        max_attempts = max(1, int(config.get("retry_count", 3)))
    except (TypeError, ValueError):
        max_attempts = 3
    try:
        timeout = float(config.get("read_timeout", 30))
    except (TypeError, ValueError):
        timeout = 30.0
    request = Request(url, headers=headers or {"User-Agent": "Mozilla/5.0"})

    last_exc = None
    for attempt in range(1, max_attempts + 1):
        try:
            # Media thumbnail URL resolved by yt-dlp; core downloader behavior.
            response = urlopen(request, timeout=timeout)  # nosec B310
            with response, open(output_file, "wb") as file_obj:
                file_obj.write(response.read())
            return  # success
        except (URLError, OSError) as exc:
            last_exc = exc
            if attempt < max_attempts:
                wait = backoff_delay(attempt, base=2.0, cap=30.0)
                console.print(
                    f"{YELLOW}[~] Image download attempt {attempt}/{max_attempts} failed "
                    f"({exc}). Retrying in {wait}s...{RESET}"
                )
                time.sleep(wait)

    raise RuntimeError(
        f"Image download failed after {max_attempts} attempt(s): {last_exc}. "
        "Check your connection and retry. Use --log-file for details."
    ) from last_exc
