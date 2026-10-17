"""Universal media container and format probing engine."""

from __future__ import annotations

import json
import logging
import math
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from ...ffmpeg_setup import ensure_ffprobe

logger = logging.getLogger("pinak.media.probe")


def _safe_int(value: object, default: int = 0) -> int:
    try:
        return max(0, int(str(value)))
    except (ValueError, TypeError, OverflowError):
        return default


@dataclass
class MediaMetadata:
    """Consolidated media stream and container attributes."""

    media_type: Literal["picture", "video", "audio"]
    file_path: Path
    file_size_bytes: int
    duration_seconds: float = 0.0
    # Video properties
    video_codec: str | None = None
    width: int = 0
    height: int = 0
    fps: float = 0.0
    aspect_ratio: float = 1.0
    video_bitrate: int = 0
    # Audio properties
    audio_codec: str | None = None
    sample_rate: int = 0
    channels: int = 0
    audio_bitrate: int = 0
    # Tags & Artwork
    title: str | None = None
    artist: str | None = None
    album: str | None = None
    album_art_bytes: bytes | None = None


class MediaProbe:
    """Probes media files using fast header signatures, Mutagen, Pillow, and FFprobe."""

    @classmethod
    def probe(cls, file_path: str | Path) -> MediaMetadata:
        is_url = isinstance(file_path, str) and file_path.lower().startswith(
            ("http://", "https://", "rtsp://", "rtmp://")
        )
        if is_url:
            raise ValueError(
                "The media player accepts local files; download the URL first with pinak URL"
            )

        path = Path(file_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Media file not found: {path}")

        file_size = path.stat().st_size
        magic_type = cls._probe_magic_bytes(path)

        # 1. Image path
        if magic_type == "picture":
            return cls._probe_image(path, file_size)

        # 2. Audio/Video path: Try FFprobe first if installed
        ffprobe_meta = cls._probe_with_ffprobe(path, file_size)
        if ffprobe_meta is not None:
            if ffprobe_meta.duration_seconds <= 0.0:
                ffprobe_meta.duration_seconds = cls._probe_duration_with_ffmpeg(path)
            cls._enrich_tags(path, ffprobe_meta)
            return ffprobe_meta

        # 3. Fallback: Mutagen for audio
        if magic_type == "audio" or path.suffix.lower() in (
            ".m4a",
            ".mp3",
            ".flac",
            ".wav",
            ".opus",
            ".ogg",
        ):
            audio_meta = cls._probe_audio_mutagen(path, file_size)
            if audio_meta is not None:
                return audio_meta

        # Default fallback container with ffmpeg duration probe
        ffmpeg_dur = cls._probe_duration_with_ffmpeg(path)
        media_type: Literal["picture", "video", "audio"] = (
            cast(Literal["picture", "video", "audio"], magic_type)
            if magic_type in ("picture", "video", "audio")
            else "video"
        )
        meta = MediaMetadata(
            media_type=media_type,
            file_path=path,
            file_size_bytes=file_size,
            duration_seconds=ffmpeg_dur,
        )
        cls._enrich_tags(path, meta)
        return meta

    @classmethod
    def _probe_magic_bytes(cls, path: Path) -> str:
        """Inspects header bytes for immediate classification."""
        try:
            with open(path, "rb") as f:
                header = f.read(32)
        except OSError:
            return "unknown"

        if header.startswith(b"\xff\xd8\xff"):
            return "picture"  # JPEG
        if header.startswith(b"\x89PNG\r\n\x1a\n"):
            return "picture"  # PNG
        if header.startswith(b"GIF8"):
            return "picture"  # GIF
        if header.startswith(b"BM"):
            return "picture"  # BMP
        if len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"WEBP":
            return "picture"  # WebP
        if header.startswith(b"ID3") or (
            len(header) >= 2 and header[0] == 0xFF and (header[1] & 0xE0) == 0xE0
        ):
            return "audio"  # MP3
        if header.startswith(b"fLaC"):
            return "audio"  # FLAC
        if header.startswith(b"OggS"):
            return "audio"  # OGG / Opus
        if len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"WAVE":
            return "audio"  # WAV
        if len(header) >= 8 and header[4:8] == b"ftyp":
            return "audio" if path.suffix.lower() == ".m4a" or header[8:11] == b"M4A" else "video"
        if header.startswith(b"\x1a\x45\xdf\xa3"):
            return "video"  # MKV / WebM

        # Extension heuristic fallback
        ext = path.suffix.lower()
        if ext in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tiff"):
            return "picture"
        if ext in (".mp3", ".flac", ".wav", ".aac", ".ogg", ".opus", ".m4a", ".wma"):
            return "audio"
        if ext in (".mp4", ".mkv", ".webm", ".avi", ".mov", ".flv", ".wmv", ".m4v"):
            return "video"

        return "unknown"

    @classmethod
    def _probe_image(cls, path: Path, file_size: int) -> MediaMetadata:
        """Inspects picture dimensions using Pillow."""
        meta = MediaMetadata(
            media_type="picture",
            file_path=path,
            file_size_bytes=file_size,
        )
        try:
            from PIL import Image

            with Image.open(path) as img:
                meta.width, meta.height = img.size
                if meta.height > 0:
                    meta.aspect_ratio = meta.width / meta.height
                meta.video_codec = img.format
        except Exception:
            pass
        return meta

    @classmethod
    def _find_ffmpeg(cls) -> str | None:
        try:
            from ...ffmpeg_setup import ensure_ffmpeg

            fetched = ensure_ffmpeg()
            if fetched and (os.path.exists(fetched) or shutil.which(fetched)):
                return fetched
        except Exception:
            pass
        return None

    @classmethod
    def _probe_duration_with_ffmpeg(cls, path: Path) -> float:
        """Extracts container duration using ffmpeg -hide_banner -i when ffprobe is missing."""
        ffmpeg_bin = cls._find_ffmpeg()
        if not ffmpeg_bin:
            return 0.0
        try:
            cmd = [ffmpeg_bin, "-hide_banner", "-i", str(path)]
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=3.0,
            )
            match = re.search(r"Duration:\s*(\d{2}):(\d{2}):(\d{2}(?:\.\d+)?)", proc.stderr or "")
            if match:
                h, m, s = match.groups()
                return int(h) * 3600 + int(m) * 60 + float(s)
        except Exception:
            pass
        return 0.0

    @classmethod
    def _probe_with_ffprobe(cls, path: Path, file_size: int) -> MediaMetadata | None:
        """Invokes ffprobe sub-process if available."""
        ffprobe_bin = ensure_ffprobe()
        if not ffprobe_bin or not (os.path.isfile(ffprobe_bin) or shutil.which(ffprobe_bin)):
            return None

        cmd = [
            ffprobe_bin,
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=3.0,
            )
            if proc.returncode != 0 or not proc.stdout:
                return None
            data = json.loads(proc.stdout)
        except Exception:
            return None

        if not isinstance(data, dict):
            return None
        streams = data.get("streams", [])
        if not isinstance(streams, list):
            return None
        streams = [s for s in streams if isinstance(s, dict)]
        fmt = data.get("format", {})
        if not isinstance(fmt, dict):
            fmt = {}
        try:
            duration = float(fmt.get("duration", 0.0))
        except (ValueError, TypeError):
            duration = 0.0
        if not math.isfinite(duration):
            duration = 0.0

        if duration <= 0.0:
            for s in streams:
                try:
                    s_dur = float(s.get("duration", 0.0))
                    if math.isfinite(s_dur) and s_dur > duration:
                        duration = s_dur
                except (ValueError, TypeError):
                    pass

        v_stream = next(
            (
                s
                for s in streams
                if s.get("codec_type") == "video"
                and isinstance(s.get("disposition", {}), dict)
                and not s.get("disposition", {}).get("attached_pic")
            ),
            None,
        )
        a_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

        # Distinguish attached cover art from genuine video stream
        has_real_video = False
        if v_stream is not None:
            disposition = v_stream.get("disposition", {})
            is_attached_pic = disposition.get("attached_pic", 0) == 1
            if (
                not is_attached_pic
                and _safe_int(v_stream.get("nb_frames", 2), 2) > 1
                or not is_attached_pic
                and duration > 0.0
            ):
                has_real_video = True

        media_type: Literal["picture", "video", "audio"] = "video" if has_real_video else "audio"

        meta = MediaMetadata(
            media_type=media_type,
            file_path=path,
            file_size_bytes=file_size,
            duration_seconds=duration,
        )

        if v_stream and has_real_video:
            meta.video_codec = v_stream.get("codec_name")
            meta.width = _safe_int(v_stream.get("width", 0))
            meta.height = _safe_int(v_stream.get("height", 0))
            if meta.height > 0:
                meta.aspect_ratio = meta.width / meta.height
            fps_val = 0.0
            for rate_key in ("avg_frame_rate", "r_frame_rate"):
                rate_str = str(v_stream.get(rate_key, ""))
                if "/" in rate_str:
                    try:
                        num, den = rate_str.split("/")
                        n, d = float(num), float(den)
                        if d > 0 and n > 0:
                            calc = n / d
                            if 1.0 <= calc <= 144.0:
                                fps_val = calc
                                break
                    except Exception:
                        pass
            if fps_val > 0.0:
                meta.fps = fps_val

        if a_stream:
            meta.audio_codec = a_stream.get("codec_name")
            meta.sample_rate = _safe_int(a_stream.get("sample_rate", 0))
            meta.channels = _safe_int(a_stream.get("channels", 0))

        tags = fmt.get("tags", {})
        if not isinstance(tags, dict):
            tags = {}
        meta.title = tags.get("title") or tags.get("TITLE")
        meta.artist = tags.get("artist") or tags.get("ARTIST")
        meta.album = tags.get("album") or tags.get("ALBUM")

        return meta

    @classmethod
    def _probe_audio_mutagen(cls, path: Path, file_size: int) -> MediaMetadata | None:
        """Inspects audio tags using Mutagen."""
        try:
            import mutagen

            audio = mutagen.File(str(path))
            if audio is None:
                return None

            meta = MediaMetadata(
                media_type="audio",
                file_path=path,
                file_size_bytes=file_size,
                duration_seconds=getattr(audio.info, "length", 0.0),
                sample_rate=getattr(audio.info, "sample_rate", 0),
                channels=getattr(audio.info, "channels", 2),
                audio_bitrate=getattr(audio.info, "bitrate", 0),
            )
            cls._enrich_tags(path, meta)
            return meta
        except Exception:
            return None

    @classmethod
    def _enrich_tags(cls, path: Path, meta: MediaMetadata) -> None:
        """Extracts artist, title, album, and embedded album art."""
        try:
            import mutagen

            f = mutagen.File(str(path))
            if not f or not f.tags:
                return

            if not meta.title:
                title_val = f.tags.get("TIT2") or f.tags.get("title")
                if title_val:
                    meta.title = str(title_val[0])
            if not meta.artist:
                artist_val = f.tags.get("TPE1") or f.tags.get("artist")
                if artist_val:
                    meta.artist = str(artist_val[0])
            if not meta.album:
                album_val = f.tags.get("TALB") or f.tags.get("album")
                if album_val:
                    meta.album = str(album_val[0])

            # Extract embedded album artwork
            if meta.album_art_bytes is None:
                # ID3v2 APIC tag
                for tag_name in f.tags:
                    if tag_name.startswith("APIC:"):
                        meta.album_art_bytes = f.tags[tag_name].data
                        break
                # FLAC picture block
                if not meta.album_art_bytes and hasattr(f, "pictures") and f.pictures:
                    meta.album_art_bytes = f.pictures[0].data
                # MP4 'covr' tag
                if not meta.album_art_bytes and "covr" in f.tags and f.tags["covr"]:
                    meta.album_art_bytes = bytes(f.tags["covr"][0])
        except Exception:
            pass
