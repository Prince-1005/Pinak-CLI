import os
import time
import urllib.parse
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError

import yt_dlp
from yt_dlp.utils import DownloadError, sanitize_filename
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, DownloadColumn, TimeRemainingColumn

from .config import config
from .utils import (
    get_ffmpeg_path, get_file_snapshot, changed_files,
    CYAN, GREEN, YELLOW, RED, RESET, BOLD
)

console = Console()

# Module-level progress references so the yt-dlp hook can update them
_progress = None
_task_id = None


def _yt_dlp_hook(d):
    """yt-dlp progress hook — updates the rich progress bar for video downloads."""
    global _progress, _task_id
    if _progress is None or _task_id is None:
        return
    if d['status'] == 'downloading':
        total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
        downloaded = d.get('downloaded_bytes', 0)
        fname = os.path.basename(d.get('filename', ''))[:24]
        if total > 0:
            _progress.update(_task_id, total=total, completed=downloaded,
                             description=f"[cyan]Downloading: {fname}...")
        else:
            _progress.update(_task_id, total=None, completed=downloaded,
                             description=f"[cyan]Downloading: {fname}...")
    elif d['status'] == 'finished':
        _progress.update(_task_id, description="[green]Merging streams...")


def download_instagram_media(url, output_path, extract_audio=False, quality=None, filename_suffix=""):
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

    ydl_opts = {
        'outtmpl': str(output_dir / f"%(id)s_%(title)s{filename_suffix}.%(ext)s"),
        'ignore_no_formats_error': True,
        'quiet': True,
        'no_warnings': True,
        'ffmpeg_location': app_dir,
        # FIX #2: register the progress hook so the rich bar updates
        'progress_hooks': [_yt_dlp_hook],
    }

    if extract_audio:
        ydl_opts['format'] = 'bestaudio/best'
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': config.get("audio_format", "mp3"),
            'preferredquality': str(config.get("audio_quality", "192")),
        }]

    before_files = get_file_snapshot(str(output_dir))

    console.print(f"\n[*] Extracting Instagram metadata for: [blue underline]{url}[/]")

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False, process=False)
            if not info:
                raise RuntimeError("Could not retrieve post information. Make sure it is public.")

            metadata = extract_metadata(info)
            _download_extracted_info(ydl, info, output_dir, filename_suffix, metadata)

    except DownloadError as exc:
        raise RuntimeError(
            "Failed to download the Instagram content. "
            "Check that the URL is public, valid, and that network access is allowed."
        ) from exc

    after_files = get_file_snapshot(str(output_dir))
    new_files = changed_files(before_files, after_files)

    return {
        "success": len(new_files) > 0,
        "url": url,
        "audio": extract_audio,
        "quality": "audio" if extract_audio else (quality or config.get("quality", "best")),
        "info": info,
        "files": new_files,
        "errors": []
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


def _download_extracted_info(ydl, info, output_dir, filename_suffix, metadata):
    """Processes the extracted info dictionary and downloads each entry."""
    if info.get('_type') == 'playlist':
        entries = info.get('entries') or []
        total = len(entries)
        console.print(f"[*] Detected carousel post with {total} items.")
        for index, entry in enumerate(entries, start=1):
            if entry:
                console.print(f"\n[*] Processing slide {index}/{total}...")
                _download_entry(ydl, entry, output_dir, index, filename_suffix, metadata)
        return

    _download_entry(ydl, info, output_dir, 1, filename_suffix, metadata)


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
        exif[270] = title_val                              # ImageDescription
        exif[40091] = title_val.encode('utf-16le')         # XPTitle

        # 2. Description -> Subtitle (XPSubject)
        exif[40095] = desc_val.encode('utf-16le')

        # 3. Uploader -> Contributing Artist
        exif[315] = uploader_val                           # Artist
        exif[40093] = uploader_val.encode('utf-16le')      # XPAuthor

        # 4. Webpage URL -> Copyright
        exif[33432] = url_val

        # 5. Comment -> XPComment + UserComment
        exif[40092] = comment_val.encode('utf-16le')       # XPComment

        # FIX #5: use UNICODE prefix + utf-16le for non-ASCII text
        if comment_val.isascii():
            exif[37510] = b'ASCII\x00\x00\x00' + comment_val.encode('ascii')
        else:
            exif[37510] = b'UNICODE\x00' + comment_val.encode('utf-16le')

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
        ffmpeg_path, "-y",
        "-i", str(file_path),
        "-map_metadata", "-1",
        "-codec", "copy",
        str(temp_path)
    ]
    try:
        import subprocess
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        if temp_path.exists():
            os.replace(temp_path, file_path)

            ext = file_path.suffix.lower()
            if ext in ('.mp4', '.m4v', '.mov'):
                try:
                    from mutagen.mp4 import MP4
                    video = MP4(file_path)

                    id_val = metadata.get("id") or ""
                    uploader_val = metadata.get("uploader") or ""
                    title_val = metadata.get("title") or ""

                    video["©nam"] = [title_val or id_val]
                    video["©ART"] = [uploader_val]
                    video["©pub"] = [title_val]
                    video["----:com.apple.iTunes:PUBLISHER"] = [title_val.encode('utf-8')]
                    video["desc"] = [desc_val]
                    video["©snt"] = [desc_val]
                    video["----:com.apple.iTunes:SUBTITLE"] = [desc_val.encode('utf-8')]
                    video["cprt"] = [url_val]
                    video["----:com.apple.iTunes:Copyright"] = [url_val.encode('utf-8')]
                    video["©cmt"] = [comment_val]
                    video["----:com.apple.iTunes:COMMENT"] = [comment_val.encode('utf-8')]

                    allowed_keys = (
                        "©nam", "©ART", "©pub", "----:com.apple.iTunes:PUBLISHER",
                        "desc", "©snt", "----:com.apple.iTunes:SUBTITLE",
                        "cprt", "----:com.apple.iTunes:Copyright",
                        "©cmt", "----:com.apple.iTunes:COMMENT", "©too"
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
            try:
                os.remove(temp_path)
            except OSError:          # FIX #7: specific exception, not bare except
                pass
        console.print(f"{YELLOW}[!] Warning: Could not embed metadata in video {file_path.name}: {e}{RESET}")
    return False


def _download_entry(ydl, entry, output_dir, index, filename_suffix, metadata):
    """
    Resolves a single entry and downloads it as video or image.
    All image slides are saved as high-quality JPEG with EXIF in one pass.
    """
    global _progress, _task_id

    resolved = _resolve_entry(ydl, entry)
    if not resolved:
        console.print(f"{RED}[X] Could not resolve entry at slide {index}.{RESET}")
        return

    if resolved.get('_type') == 'playlist':
        _download_extracted_info(ydl, resolved, output_dir, filename_suffix, metadata)
        return

    post_id = resolved.get('id') or f'item_{index}'
    before = get_file_snapshot(str(output_dir))

    is_video = _has_video_formats(resolved)

    if is_video:
        # FIX #2: wrap video download in a rich progress bar
        console.print(f"[*] Slide {index} contains video content. Downloading...")
        try:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                DownloadColumn(),
                TimeRemainingColumn(),
                console=console
            ) as progress:
                _progress = progress
                _task_id = progress.add_task("[cyan]Starting video download...", total=None)
                ydl.process_video_result(resolved, download=True)
                _progress = None
                _task_id = None
            console.print(f"{GREEN}[+] Slide {index} downloaded successfully.{RESET}")
        except Exception as e:
            _progress = None
            _task_id = None
            console.print(f"{RED}[X] Error downloading video slide {index}: {e}{RESET}")
    else:
        # Image slide
        thumbnail_url = _best_thumbnail_url(resolved)
        if not thumbnail_url:
            console.print(f"{RED}[X] No downloadable media found for slide {index}.{RESET}")
            return

        filename = _image_filename(resolved, output_dir, index, filename_suffix)
        console.print(f"[*] Slide {index} contains image content. Fetching image...")

        temp_img_path = output_dir / f"temp_download_{index}_{post_id}.tmp"
        try:
            # FIX #3: retry image download
            _download_binary_with_retry(thumbnail_url, temp_img_path, resolved.get('http_headers'))

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

            try:
                os.remove(temp_img_path)
            except OSError:          # FIX #7
                pass

            console.print(f"{GREEN}[+] Image saved as JPG: {filename.name}{RESET}")
        except Exception as e:
            try:
                os.remove(temp_img_path)
            except OSError:          # FIX #7
                pass
            console.print(f"{RED}[X] Error downloading image slide {index}: {e}{RESET}")

    # Snapshot diff — find newly created files
    after = get_file_snapshot(str(output_dir))
    new_files = changed_files(before, after)

    # Embed metadata into video files (images are handled above inline)
    for f in new_files:
        f_path = Path(f)
        if f_path.suffix.lower() in ('.mp4', '.mkv', '.webm', '.avi', '.m4v'):
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
    for depth in range(5):
        if resolved.get('_type') in {'url', 'url_transparent'} and resolved.get('url'):
            try:
                next_entry = ydl.extract_info(resolved['url'], download=False, process=False)
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
    for fmt in info.get('formats') or []:
        if fmt.get('url') and fmt.get('vcodec') not in (None, 'none'):
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
    thumbnails = entry.get('thumbnails') or []

    def _area(t):
        w = t.get('width') or 0
        h = t.get('height') or 0
        return w * h

    for thumb in sorted(thumbnails, key=_area, reverse=True):
        url = thumb.get('url')
        if url:
            return url
    return entry.get('thumbnail')


def _image_filename(entry, output_dir, index, filename_suffix):
    """
    Constructs a sanitized .jpg filename.
    Format: <index:02d>_<post_id>_<sanitized_title><suffix>.jpg
    """
    post_id = entry.get('id') or f'item_{index}'
    title = sanitize_filename(
        entry.get('title') or entry.get('id') or f'item_{index}', restricted=True
    )
    return output_dir / f"{index:02d}_{post_id}_{title}{filename_suffix}.jpg"


# ---------------------------------------------------------------------------
# FIX #3: retry wrapper  |  FIX #10: 30-second timeout on urlopen
# ---------------------------------------------------------------------------
def _download_binary_with_retry(url, output_file, headers=None):
    """
    Downloads a binary file with timeout and automatic retry.

    Retries up to config['retry_count'] times (default 3) with a short
    back-off between each attempt.
    """
    max_attempts = max(1, int(config.get("retry_count", 3)))
    request = Request(url, headers=headers or {'User-Agent': 'Mozilla/5.0'})

    last_exc = None
    for attempt in range(1, max_attempts + 1):
        try:
            # FIX #10: explicit 30-second timeout prevents infinite hang
            with urlopen(request, timeout=30) as response, \
                    open(output_file, 'wb') as file_obj:
                file_obj.write(response.read())
            return  # success
        except (URLError, OSError) as exc:
            last_exc = exc
            if attempt < max_attempts:
                wait = min(2 * attempt, 8)
                console.print(
                    f"{YELLOW}[~] Image download attempt {attempt}/{max_attempts} failed "
                    f"({exc}). Retrying in {wait}s...{RESET}"
                )
                time.sleep(wait)

    raise RuntimeError(
        f"Image download failed after {max_attempts} attempt(s): {last_exc}"
    )
