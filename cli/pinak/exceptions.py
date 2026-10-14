"""Pinak custom exception hierarchy.

All user-facing errors should raise (or be wrapped into) one of these types
so that CLI handlers can render *actionable* messages instead of raw
tracebacks.

Example:
    try:
        ...
    except PinakError as exc:
        console.print(f"[red][X] {exc.hint}[/]")
"""

from __future__ import annotations


class PinakError(Exception):
    """Base class for all Pinak errors."""

    hint: str = "An unexpected error occurred. Run `pinak --doctor` for diagnostics."

    def __init__(self, message: str = "", *, hint: str = "") -> None:
        super().__init__(message or self.hint)
        if hint:
            self.hint = hint


class InvalidURLError(PinakError):
    hint = "Please provide a valid URL starting with http:// or https://."


class InvalidQualityError(PinakError):
    hint = "Invalid quality. Use best, worst, audio, 360p, 720p, or 1080p."


class NetworkError(PinakError):
    hint = (
        "Network error. Check your internet connection and try again. "
        "If the problem persists run `pinak --doctor --verbose`."
    )


class FFmpegNotFoundError(PinakError):
    hint = (
        "FFmpeg not found. Install FFmpeg and ensure it is on PATH, "
        "place ffmpeg(.exe)/ffprobe(.exe) next to the cli/ folder, "
        "set a custom path in config (ffmpeg_path / ffprobe_path), "
        "or install the auto-fetch extra: `pip install pinak-cli[ffmpeg]`. "
        "Then run `pinak --doctor` to verify."
    )


class DownloadFailedError(PinakError):
    hint = (
        "Download failed. Verify the URL is public and reachable, "
        "then retry. Use --verbose / --log-file for details."
    )


class UnsupportedLinkTypeError(DownloadFailedError):
    hint = (
        "This link type is not supported by yt-dlp. "
        "Use /platform to view supported platforms or supply a direct media stream URL."
    )


class InstagramError(DownloadFailedError):
    hint = (
        "Instagram download failed. Make sure the post/reel/story is public "
        "and the URL is correct. Instagram may rate-limit frequent requests — "
        "wait a few minutes and retry."
    )


class InstagramRateLimitedError(InstagramError):
    hint = (
        "Instagram appears to be rate-limiting requests (HTTP 429). "
        "Wait a few minutes before retrying, and avoid bulk downloads."
    )


class InstagramPrivateContentError(InstagramError):
    hint = (
        "This Instagram content appears to be private or unavailable. "
        "Only public posts/reels can be downloaded."
    )


class ConfigError(PinakError):
    hint = (
        "Configuration error. Delete the corrupt config file or run "
        "`pinak config --show` to inspect it, then retry."
    )


class OutputDirError(PinakError):
    hint = (
        "Cannot write to the output directory. Choose a writable folder with "
        "`--output <dir>` or `/setout <dir>`, and check disk space."
    )
