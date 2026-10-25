"""Reusable, in-process download contract shared by CLI and queue clients."""

from __future__ import annotations

import contextlib
import contextvars
import logging
import os
import re
from collections.abc import Callable, Iterator
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import urlsplit

from rich.text import Text

from .config import config, validate_settings
from .utils import normalize_quality


def parse_trim_range(value: str) -> tuple[int, int]:
    """Validate a MM:SS or HH:MM:SS clip with a positive duration."""
    if len(value) > 64 or not re.fullmatch(
        r"\d+(?::\d{1,2}){1,2}-\d+(?::\d{1,2}){1,2}", value
    ):
        raise ValueError("Trim range must look like 01:15-02:30")

    def seconds(part: str) -> int:
        fields = [int(piece) for piece in part.split(":")]
        if fields[-1] >= 60 or (len(fields) == 3 and fields[-2] >= 60):
            raise ValueError("Trim minutes and seconds must be below 60")
        return sum(field * 60**power for power, field in enumerate(reversed(fields)))

    start, end = (seconds(part) for part in value.split("-"))
    if end <= start:
        raise ValueError("Trim end must be after trim start")
    return start, end


@dataclass(frozen=True)
class DownloadRequest:
    url: str
    output_dir: str
    quality: str
    extract_audio: bool = False
    force: bool = False
    is_any_command: bool = False
    trim_range: str | None = None
    audio_format: str = "mp3"
    audio_quality: str = "192"
    video_format: str = "mp4"
    auto_sort: bool = False
    embed_subs: bool = False
    subtitle_languages: tuple[str, ...] = ("en",)
    duplicate_action: str = "ask"
    retry_count: int = 3
    connect_timeout: float = 10.0
    read_timeout: float = 30.0
    ffmpeg_path: str = ""
    ffprobe_path: str = ""

    @classmethod
    def capture(
        cls,
        url: str,
        *,
        output_dir: str | None = None,
        quality: str | None = None,
        extract_audio: bool = False,
        force: bool = False,
        is_any_command: bool = False,
        trim_range: str | None = None,
    ) -> DownloadRequest:
        parsed = urlsplit(url)
        if (
            parsed.scheme not in {"https", "http"}
            or not parsed.hostname
            or any(c.isspace() for c in url)
        ):
            raise ValueError("URL must start with http:// or https://")
        resolved_quality = normalize_quality(quality or config.get("quality", "best"))
        if resolved_quality is None:
            raise ValueError("Invalid quality; use best, worst, audio, or a height such as 720p")
        settings = validate_settings(config).model_dump()
        if output_dir is not None and not output_dir.strip():
            raise ValueError("Output directory is required")
        path = os.path.abspath(output_dir or settings["output_dir"])
        if trim_range is not None:
            parse_trim_range(trim_range)
        return cls(
            url=url,
            output_dir=path,
            quality=resolved_quality,
            extract_audio=extract_audio or resolved_quality == "audio",
            force=force,
            is_any_command=is_any_command,
            trim_range=trim_range,
            audio_format=settings["audio_format"],
            audio_quality=settings["audio_quality"],
            video_format=settings["video_format"],
            auto_sort=settings["auto_sort"],
            embed_subs=settings["embed_subs"],
            subtitle_languages=tuple(settings["subtitle_languages"]),
            # A saved job cannot prompt after restart. The interactive "ask"
            # preference resolves conservatively; --force remains explicit.
            duplicate_action=(
                "skip" if settings["duplicate_action"] == "ask" else settings["duplicate_action"]
            ),
            retry_count=settings["retry_count"],
            connect_timeout=settings["connect_timeout"],
            read_timeout=settings["read_timeout"],
            ffmpeg_path=settings["ffmpeg_path"],
            ffprobe_path=settings["ffprobe_path"],
        )

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> DownloadRequest:
        # Jobs saved before configurable subtitle languages used the English default.
        if "subtitle_languages" not in payload:
            payload = {**payload, "subtitle_languages": ["en"]}
        if set(payload) != set(cls.__dataclass_fields__):
            raise ValueError("Saved download request has an unsupported schema")
        payload = {**payload, "subtitle_languages": tuple(payload["subtitle_languages"])}
        request = cls(**payload)
        if request.trim_range is not None:
            parse_trim_range(request.trim_range)
        parsed = urlsplit(request.url)
        if (
            parsed.scheme not in {"https", "http"}
            or not parsed.hostname
            or not os.path.isabs(request.output_dir)
        ):
            raise ValueError("Saved download request has invalid URL or output directory")
        validate_settings(request.settings())
        return request

    def settings(self) -> dict[str, Any]:
        return {
            "output_dir": self.output_dir,
            "quality": self.quality,
            "audio_format": self.audio_format,
            "audio_quality": self.audio_quality,
            "video_format": self.video_format,
            "auto_sort": self.auto_sort,
            "embed_subs": self.embed_subs,
            "subtitle_languages": list(self.subtitle_languages),
            "duplicate_action": self.duplicate_action,
            "retry_count": self.retry_count,
            "connect_timeout": self.connect_timeout,
            "read_timeout": self.read_timeout,
            "ffmpeg_path": self.ffmpeg_path,
            "ffprobe_path": self.ffprobe_path,
        }

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DownloadEvent:
    kind: str
    message: str = ""
    downloaded: int | None = None
    total: int | None = None
    files: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class DownloadResult:
    status: str
    url: str
    files: tuple[str, ...]
    errors: tuple[str, ...]
    duration: int = 0


EventSink = Callable[[DownloadEvent], None]
_active: contextvars.ContextVar[tuple[DownloadRequest, EventSink] | None] = contextvars.ContextVar(
    "pinak_download_context", default=None
)
_queue_owns_history: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "pinak_queue_owns_history", default=False
)
_log = logging.getLogger("pinak.engine")
_stop_check: contextvars.ContextVar[Callable[[], bool] | None] = contextvars.ContextVar(
    "pinak_stop_check", default=None
)


@contextlib.contextmanager
def managed_downloads(stop: Callable[[], bool]) -> Iterator[None]:
    token = _stop_check.set(stop)
    try:
        yield
    finally:
        _stop_check.reset(token)


def cancellation_requested() -> bool:
    callback = _stop_check.get()
    return callback is not None and callback()


def managed_stop_enabled() -> bool:
    return _stop_check.get() is not None


def check_cancelled() -> None:
    if cancellation_requested():
        raise KeyboardInterrupt("Managed download stop requested")


def binary_provision_allowed() -> bool:
    return _stop_check.get() is None


@contextlib.contextmanager
def _request_context(request: DownloadRequest, on_event: EventSink) -> Iterator[None]:
    token = _active.set((request, on_event))
    try:
        yield
    finally:
        _active.reset(token)


def in_engine() -> bool:
    return _active.get() is not None


@contextlib.contextmanager
def queue_owns_history() -> Iterator[None]:
    """Let the queue persist its result and history in one transaction."""
    token = _queue_owns_history.set(True)
    try:
        yield
    finally:
        _queue_owns_history.reset(token)


def history_owned_by_queue() -> bool:
    return _queue_owns_history.get()


def active_setting(key: str, default: Any = None) -> Any:
    active = _active.get()
    return (active[0].settings() if active else config).get(key, default)


def emit(event: DownloadEvent) -> None:
    active = _active.get()
    if active is not None:
        try:
            active[1](event)
        except Exception:
            _log.exception("Download event listener failed")


def emit_message(*parts: object) -> bool:
    """Return True when a headless client consumed a display message."""
    check_cancelled()
    if not in_engine():
        return False
    plain = " ".join(str(part) for part in parts)
    with contextlib.suppress(Exception):
        plain = Text.from_markup(plain).plain
    plain = re.sub(r"\x1b\[[0-9;]*m", "", plain).strip()
    if plain:
        emit(DownloadEvent("message", plain))
    return True


def emit_progress(data: dict[str, Any]) -> bool:
    check_cancelled()
    if not in_engine():
        return False
    state = data.get("status")
    if state in {"downloading", "finished"}:
        emit(
            DownloadEvent(
                "progress" if state == "downloading" else "processing",
                os.path.basename(str(data.get("filename") or "")),
                int(data.get("downloaded_bytes") or 0) if state == "downloading" else None,
                (
                    int(data.get("total_bytes") or data.get("total_bytes_estimate") or 0)
                    if state == "downloading"
                    else None
                ),
            )
        )
    return True


class SilentProgress:
    def __enter__(self) -> SilentProgress:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def add_task(self, *_args: object, **_kwargs: object) -> int:
        return 0

    def update(self, *_args: object, **_kwargs: object) -> None:
        return None


def run_download(request: DownloadRequest, on_event: EventSink | None = None) -> DownloadResult:
    """Run one captured request without writing terminal UI from the downloader."""
    from .downloader import handle_download

    with _request_context(request, on_event or (lambda _event: None)):
        raw = handle_download(
            request.url,
            extract_audio=request.extract_audio,
            force=request.force,
            quality=request.quality,
            interactive=False,
            trim_range=request.trim_range,
            is_any_command=request.is_any_command,
        )
    if raw.get("skipped"):
        status = "skipped"
    elif raw.get("success"):
        status = "succeeded"
    elif raw.get("canceled"):
        status = "interrupted"
    else:
        status = "failed"
    info = raw.get("info") or {}
    try:
        duration = int(info.get("duration") or 0)
    except (TypeError, ValueError, OverflowError):
        duration = 0
    errors = tuple(str(e) for e in (raw.get("errors") or ()))
    if status == "failed" and not errors:
        errors = (str(raw.get("error") or "Download failed"),)
    result = DownloadResult(
        status=status,
        url=request.url,
        files=tuple(raw.get("files") or ()),
        errors=errors,
        duration=duration,
    )
    if on_event:
        try:
            on_event(DownloadEvent("result", status))
        except Exception:
            _log.exception("Download event listener failed")
    return result
