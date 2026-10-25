"""Parsers for SRT, WebVTT, and embedded FFmpeg subtitle streams."""

from __future__ import annotations

import json
import logging
import re
import subprocess
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from itertools import islice
from pathlib import Path

from ...ffmpeg_setup import ensure_ffmpeg
from ...subtitle_preferences import (
    MAX_SUBTITLE_LANGUAGES,
    SUBTITLE_LANGUAGES,
    subtitle_language_name,
)
from ...utils import get_ffprobe_path
from .model import SubtitleCue, SubtitleTrack

logger = logging.getLogger("pinak.media.subtitles")
MAX_SUBTITLE_BYTES = 8 * 1024 * 1024
MAX_SUBTITLE_CUES = 10_000
MAX_SIBLING_ENTRIES = 2_048
MAX_SIBLING_TRACKS = 32


def _run_bounded_stdout(
    cmd: list[str], *, timeout: float, max_bytes: int
) -> subprocess.CompletedProcess[bytes]:
    """Capture FFmpeg output with both a deadline and an in-memory byte ceiling."""
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    started = time.monotonic()

    def collect() -> bytes:
        assert process.stdout is not None
        output = bytearray()
        while chunk := process.stdout.read(65536):
            if len(output) + len(chunk) > max_bytes:
                raise ValueError("Subtitle process output exceeded its byte limit")
            output.extend(chunk)
        return bytes(output)

    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(collect)
            try:
                output = pending.result(timeout=timeout)
                code = process.wait(timeout=max(0.01, timeout - (time.monotonic() - started)))
            except (FutureTimeout, ValueError, subprocess.TimeoutExpired):
                process.kill()
                process.wait(timeout=2)
                raise
        return subprocess.CompletedProcess(cmd, code, stdout=output)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=2)
        if process.stdout is not None:
            process.stdout.close()


class SubtitleParser:
    """Parses subtitle files and discovers tracks for media playback."""

    SUPPORTED_SUB_EXTS = {".srt", ".vtt"}

    @classmethod
    def timestamp_to_seconds(cls, ts_str: str) -> float:
        """Converts SRT (00:01:23,456) or VTT (00:01:23.456) timestamp to seconds."""
        ts_str = ts_str.strip().replace(",", ".")
        parts = ts_str.split(":")
        try:
            if len(parts) == 3:
                h = float(parts[0])
                m = float(parts[1])
                s = float(parts[2])
                return h * 3600.0 + m * 60.0 + s
            elif len(parts) == 2:
                m = float(parts[0])
                s = float(parts[1])
                return m * 60.0 + s
            elif len(parts) == 1:
                return float(parts[0])
        except ValueError:
            pass
        return 0.0

    @classmethod
    def parse_srt(cls, text: str) -> list[SubtitleCue]:
        """Parses standard SubRip (.srt) subtitle content."""
        cues: list[SubtitleCue] = []
        # Normalize newlines
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        blocks = re.split(r"\n\s*\n", text.strip())

        cue_idx = 1
        for block in blocks:
            lines = [line.strip() for line in block.split("\n") if line.strip()]
            if not lines:
                continue

            time_line_idx = 0
            if lines[0].isdigit() and len(lines) > 1:
                time_line_idx = 1

            if time_line_idx >= len(lines):
                continue

            time_match = re.search(
                r"(\d+:\d+:\d+[\.,]\d+|\d+:\d+[\.,]\d+)\s*-->\s*(\d+:\d+:\d+[\.,]\d+|\d+:\d+[\.,]\d+)",
                lines[time_line_idx],
            )
            if not time_match:
                continue

            start_sec = cls.timestamp_to_seconds(time_match.group(1))
            end_sec = cls.timestamp_to_seconds(time_match.group(2))
            text_lines = lines[time_line_idx + 1 :]
            # Strip simple HTML formatting tags like <i>, <b>, <font>
            clean_text = "\n".join(text_lines)
            clean_text = re.sub(r"<[^>]+>", "", clean_text).strip()

            if clean_text and end_sec >= start_sec:
                cues.append(
                    SubtitleCue(
                        index=cue_idx,
                        start_sec=start_sec,
                        end_sec=end_sec,
                        text=clean_text,
                    )
                )
                cue_idx += 1
                if len(cues) >= MAX_SUBTITLE_CUES:
                    break

        return cues

    @classmethod
    def parse_vtt(cls, text: str) -> list[SubtitleCue]:
        """Parses WebVTT (.vtt) subtitle content."""
        # Strip WEBVTT header line if present
        text = re.sub(r"^WEBVTT.*?\n", "", text.strip(), flags=re.IGNORECASE)
        return cls.parse_srt(text)

    @classmethod
    def parse_file(cls, file_path: str | Path, track_id: int = 1) -> SubtitleTrack | None:
        """Reads and parses an external subtitle file."""
        path = Path(file_path).resolve()
        if not path.is_file():
            return None

        try:
            with path.open("rb") as source:
                raw = source.read(MAX_SUBTITLE_BYTES + 1)
            if len(raw) > MAX_SUBTITLE_BYTES:
                logger.warning(
                    "Subtitle file exceeds the %d-byte limit: %s", MAX_SUBTITLE_BYTES, path
                )
                return None
            content = raw.decode("utf-8", errors="replace")
        except Exception as e:
            logger.warning(f"Failed to read subtitle file {path}: {e}")
            return None

        ext = path.suffix.lower()
        cues = cls.parse_vtt(content) if ext == ".vtt" else cls.parse_srt(content)

        language_codes = {code.lower(): code for code in SUBTITLE_LANGUAGES}
        language = next(
            (
                language_codes[token.lower()]
                for token in reversed(re.split(r"[._]", path.stem))
                if token.lower() in language_codes
            ),
            "und",
        )
        return SubtitleTrack(
            track_id=track_id,
            title=path.stem,
            language=language,
            cues=cues,
            is_external=True,
            file_path=path,
        )

    @classmethod
    def discover_sibling_subtitles(cls, media_path: str | Path) -> list[SubtitleTrack]:
        """Discovers any matching sibling subtitle files in the media file's directory."""
        media = Path(media_path).resolve()
        if not media.is_file():
            return []

        parent = media.parent
        stem = media.stem.lower()
        tracks: list[SubtitleTrack] = []
        track_id = 1

        try:
            candidates = list(islice(parent.iterdir(), MAX_SIBLING_ENTRIES + 1))
            if len(candidates) > MAX_SIBLING_ENTRIES:
                logger.warning(
                    "Subtitle search limited to %d siblings: %s", MAX_SIBLING_ENTRIES, parent
                )
                candidates.pop()
            for item in sorted(candidates):
                if item.is_file() and item.suffix.lower() in cls.SUPPORTED_SUB_EXTS:
                    # Match if subtitle starts with same stem or shares base name
                    sub_stem = item.stem.lower()
                    if (
                        sub_stem == stem
                        or sub_stem.startswith(f"{stem}.")
                        or sub_stem.startswith(f"{stem}_")
                    ):
                        track = cls.parse_file(item, track_id=track_id)
                        if track and track.cues:
                            tracks.append(track)
                            track_id += 1
                            if len(tracks) >= MAX_SIBLING_TRACKS:
                                break
        except Exception as e:
            logger.warning(f"Error scanning sibling subtitles for {media}: {e}")

        return tracks

    @classmethod
    def extract_embedded_subtitles(
        cls,
        media_path: str | Path,
        start_track_id: int = 1,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> list[SubtitleTrack]:
        """Extracts text subtitle streams embedded in the media container using FFmpeg."""
        media = Path(media_path).resolve()
        if not media.is_file():
            return []

        ffmpeg_bin = ensure_ffmpeg()
        if not ffmpeg_bin:
            return []

        tracks: list[SubtitleTrack] = []
        # Match the download selection limit so every selected track is playable.
        stream_tags = []
        if is_cancelled is not None and is_cancelled():
            return []
        try:
            probe = _run_bounded_stdout(
                [
                    get_ffprobe_path(),
                    "-v",
                    "quiet",
                    "-select_streams",
                    "s",
                    "-show_entries",
                    "stream_tags=language,title",
                    "-of",
                    "json",
                    str(media),
                ],
                timeout=4.0,
                max_bytes=65536,
            )
            if probe.returncode == 0:
                stream_tags = json.loads(probe.stdout).get("streams", [])
        except (OSError, ValueError, subprocess.SubprocessError):
            pass  # Labels are optional; still extract tracks if probing fails.
        for s_idx in range(MAX_SUBTITLE_LANGUAGES):
            if is_cancelled is not None and is_cancelled():
                break
            cmd = [
                str(ffmpeg_bin),
                "-v",
                "quiet",
                "-i",
                str(media),
                "-map",
                f"0:s:{s_idx}",
                "-f",
                "srt",
                "pipe:1",
            ]
            try:
                res = _run_bounded_stdout(cmd, timeout=4.0, max_bytes=MAX_SUBTITLE_BYTES)
                if res.returncode == 0 and res.stdout:
                    srt_text = res.stdout.decode("utf-8", errors="replace")
                    cues = cls.parse_srt(srt_text)
                    if cues:
                        tags = (
                            stream_tags[s_idx].get("tags", {}) if s_idx < len(stream_tags) else {}
                        )
                        language = tags.get("language", "und")
                        title = tags.get("title") or (
                            subtitle_language_name(language)
                            if language != "und"
                            else f"Embedded #{s_idx + 1}"
                        )
                        track = SubtitleTrack(
                            track_id=start_track_id + len(tracks),
                            title=title,
                            language=language,
                            cues=cues,
                            is_external=False,
                            file_path=None,
                        )
                        tracks.append(track)
            except Exception:
                continue

        return tracks
