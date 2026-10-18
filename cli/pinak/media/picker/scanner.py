"""High-speed directory scanning and supported media classification."""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

from ...text_safety import safe_text

SUPPORTED_EXTENSIONS: dict[str, str] = {
    # Video
    ".mp4": "video",
    ".mkv": "video",
    ".webm": "video",
    ".avi": "video",
    ".mov": "video",
    ".flv": "video",
    ".wmv": "video",
    ".m4v": "video",
    # Audio
    ".mp3": "audio",
    ".flac": "audio",
    ".wav": "audio",
    ".aac": "audio",
    ".ogg": "audio",
    ".opus": "audio",
    ".m4a": "audio",
    ".wma": "audio",
    # Picture
    ".jpg": "picture",
    ".jpeg": "picture",
    ".png": "picture",
    ".webp": "picture",
    ".gif": "picture",
    ".bmp": "picture",
    ".tiff": "picture",
}


@dataclass
class MediaItem:
    """Represents a discovered media or directory item."""

    path: Path
    name: str
    is_dir: bool
    media_type: str | None  # "video", "audio", "picture", or None
    size_bytes: int
    child_media_count: int = 0


def natural_sort_key(s: str) -> list[int | str]:
    """Generates natural alphanumeric sort tokens."""
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r"(\d+)", s)]


class MediaScanner:
    """Scans directories for valid media containers with natural alphanumeric sorting."""

    @classmethod
    def count_media_in_dir(
        cls,
        dir_path: Path,
        max_check: int = 10000,
        max_depth: int = 8,
        budget_seconds: float = 0.05,
    ) -> int:
        """
        Recursively counts supported media files (video, audio, picture) inside a directory
        and all its subdirectories.
        """
        try:
            count = 0
            examined = 0
            deadline = time.monotonic() + max(0.0, budget_seconds)
            visited: set[str] = set()
            stack: list[tuple[str, int]] = [(str(dir_path), 0)]
            while stack and examined < max_check and time.monotonic() < deadline:
                curr_dir, depth = stack.pop()
                if depth > max_depth:
                    continue
                try:
                    real = os.path.realpath(curr_dir)
                    if real in visited:
                        continue
                    visited.add(real)
                except OSError:
                    continue
                try:
                    with os.scandir(curr_dir) as it:
                        for entry in it:
                            examined += 1
                            if examined > max_check or time.monotonic() >= deadline:
                                return count
                            try:
                                if entry.is_file(follow_symlinks=False):
                                    ext = os.path.splitext(entry.name)[1].lower()
                                    if ext in SUPPORTED_EXTENSIONS:
                                        count += 1
                                        if count >= max_check:
                                            break
                                elif entry.is_dir(follow_symlinks=False):
                                    stack.append((entry.path, depth + 1))
                            except OSError:
                                continue
                except (PermissionError, OSError):
                    continue
            return count
        except Exception:
            return 0

    @classmethod
    def scan_directory(
        cls, dir_path: str | Path, max_entries: int | None = None
    ) -> list[MediaItem]:
        path = Path(dir_path).resolve()
        if not path.is_dir():
            return []

        items: list[MediaItem] = []
        truncated = False
        count_deadline = time.monotonic() + 0.25
        try:
            with os.scandir(path) as entries:
                for entry in entries:
                    if max_entries is not None and len(items) >= max_entries:
                        truncated = True
                        break

                    entry_path = Path(entry.path)
                    try:
                        is_dir = entry.is_dir(follow_symlinks=False)
                        is_file = entry.is_file(follow_symlinks=False)
                        size_bytes = entry.stat(follow_symlinks=False).st_size if is_file else 0
                    except OSError:
                        is_dir = False
                        is_file = False
                        size_bytes = 0

                    media_cnt = (
                        cls.count_media_in_dir(
                            entry_path,
                            budget_seconds=min(0.02, max(0.0, count_deadline - time.monotonic())),
                        )
                        if is_dir
                        else 0
                    )
                    media_type = (
                        SUPPORTED_EXTENSIONS.get(entry_path.suffix.lower()) if is_file else None
                    )
                    items.append(
                        MediaItem(
                            path=entry_path,
                            name=safe_text(entry.name),
                            is_dir=is_dir,
                            media_type=media_type,
                            size_bytes=size_bytes,
                            child_media_count=media_cnt,
                        )
                    )
        except (PermissionError, OSError):
            return []

        dirs = sorted([x for x in items if x.is_dir], key=lambda x: natural_sort_key(x.name))
        files = sorted([x for x in items if not x.is_dir], key=lambda x: natural_sort_key(x.name))
        if truncated and max_entries is not None:
            files.append(
                MediaItem(
                    path=path,
                    name=f"[... Capped at {max_entries} items; use [p] for an omitted file's full path ...]",
                    is_dir=False,
                    media_type=None,
                    size_bytes=0,
                )
            )

        # Add parent directory indicator if not root
        result: list[MediaItem] = []
        if path.parent != path:
            result.append(
                MediaItem(
                    path=path.parent,
                    name=".. [Parent Directory]",
                    is_dir=True,
                    media_type=None,
                    size_bytes=0,
                )
            )

        result.extend(dirs)
        result.extend(files)
        return result
