from __future__ import annotations

import json
import os
import shutil
from typing import Any

import platformdirs
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .exceptions import ConfigError

APP_NAME = "pinak-cli"
APP_AUTHOR = "pinak"

# Determine standard config directory
config_dir = platformdirs.user_config_dir(APP_NAME, APP_AUTHOR)
os.makedirs(config_dir, exist_ok=True)
CONFIG_FILE = os.path.join(config_dir, "config.json")
LOCAL_CONFIG = ".pinak_config.json"

VALID_VIDEO_FORMATS = {"mp4", "mkv", "webm", "flv", "avi"}
VALID_AUDIO_FORMATS = {"mp3", "m4a", "wav", "flac", "opus"}
VALID_AUDIO_QUALITIES = {"320", "256", "192", "128", "96"}
VALID_QUALITIES = {"best", "worst", "audio"}


class PinakSettings(BaseSettings):
    output_dir: str = Field(default="downloads", description="Directory to save downloaded files")
    quality: str = Field(default="best", description="Video quality preference")
    audio_quality: str = Field(default="192", description="Audio quality preference (kbps)")
    video_format: str = Field(default="mp4", description="Preferred video format")
    audio_format: str = Field(default="mp3", description="Preferred audio format")
    retry_count: int = Field(
        default=3, ge=1, le=10, description="Number of retries for failed downloads"
    )
    connect_timeout: float = Field(
        default=10.0, ge=1.0, le=120.0, description="Connection timeout in seconds"
    )
    read_timeout: float = Field(
        default=30.0, ge=5.0, le=600.0, description="Read/download timeout in seconds"
    )
    ffmpeg_path: str = Field(
        default="", description="Custom ffmpeg binary path (empty = auto-detect)"
    )
    ffprobe_path: str = Field(
        default="", description="Custom ffprobe binary path (empty = auto-detect)"
    )
    history_enabled: bool = Field(default=True, description="Track downloads in local history DB")
    log_file: str = Field(default="", description="Optional file path for debug logs")
    embed_subs: bool = Field(default=False, description="Whether to embed subtitles")
    auto_sort: bool = Field(default=False, description="Auto sort into platform folders")

    duplicate_action: str = Field(default="ask", description="Action to take for duplicate URLs")
    username: str = Field(default="", description="User's preferred name")
    greeting: str = Field(default="Har Har Mahadev", description="Greeting message")
    last_update_check: float = Field(default=0.0, description="Timestamp of the last update check")

    model_config = SettingsConfigDict(
        env_prefix="PINAK_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("video_format")
    @classmethod
    def _validate_video_format(cls, v: str) -> str:
        v = (v or "mp4").strip().lower()
        if v not in VALID_VIDEO_FORMATS:
            raise ValueError(f"video_format must be one of {sorted(VALID_VIDEO_FORMATS)}")
        return v

    @field_validator("audio_format")
    @classmethod
    def _validate_audio_format(cls, v: str) -> str:
        v = (v or "mp3").strip().lower()
        if v not in VALID_AUDIO_FORMATS:
            raise ValueError(f"audio_format must be one of {sorted(VALID_AUDIO_FORMATS)}")
        return v

    @field_validator("audio_quality")
    @classmethod
    def _validate_audio_quality(cls, v: Any) -> str:
        v = str(v).strip()
        if v not in VALID_AUDIO_QUALITIES:
            raise ValueError(f"audio_quality must be one of {sorted(VALID_AUDIO_QUALITIES)}")
        return v

    @field_validator("quality")
    @classmethod
    def _validate_quality(cls, v: str) -> str:
        import re

        v = (v or "best").strip().lower()
        if v in VALID_QUALITIES:
            return v
        if re.fullmatch(r"\d{3,4}p?", v):
            digits = re.match(r"(\d{3,4})", v)
            if digits is None:  # pragma: no cover - unreachable given fullmatch above
                raise ValueError("quality must be best/worst/audio or like 360p/720p/1080p")
            return f"{digits.group(1)}p"
        raise ValueError("quality must be best/worst/audio or like 360p/720p/1080p")

    @field_validator("duplicate_action")
    @classmethod
    def _validate_duplicate_action(cls, v: str) -> str:
        v = (v or "ask").strip().lower()
        if v not in {"ask", "skip", "download", "rename"}:
            raise ValueError("duplicate_action must be ask/skip/download/rename")
        return v

    @field_validator("ffmpeg_path", "ffprobe_path", "log_file", "output_dir")
    @classmethod
    def _strip_strings(cls, v: str) -> str:
        return (v or "").strip()


# Legacy global dictionary for backward compatibility across modules
config: dict[str, Any] = PinakSettings().model_dump()


def _migrate_legacy_keys(data: dict[str, Any]) -> dict[str, Any]:
    """Map old/renamed keys to the current schema so old configs keep working."""
    key_map = {
        "retries": "retry_count",
        "timeout": "read_timeout",
    }
    migrated = dict(data)
    for old, new in key_map.items():
        if old in migrated and new not in migrated:
            migrated[new] = migrated.pop(old)
    # Drop unknown keys gracefully (Pydantic extra=ignore also handles this,
    # but we keep config.json clean on save).
    allowed = set(PinakSettings.model_fields.keys())
    return {k: v for k, v in migrated.items() if k in allowed}


def init_config() -> dict[str, Any]:
    global config

    # Migrate legacy ~/.pinak_config.json if exists
    legacy_home_config = os.path.expanduser("~/.pinak_config.json")
    if not os.path.exists(CONFIG_FILE):
        if os.path.exists(legacy_home_config):
            shutil.copy(legacy_home_config, CONFIG_FILE)
        elif os.path.exists(LOCAL_CONFIG):
            shutil.copy(LOCAL_CONFIG, CONFIG_FILE)

    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                data = _migrate_legacy_keys(data)
                # Load with Pydantic for validation
                settings = PinakSettings(**data)
                config.update(settings.model_dump())
    except Exception:
        pass

    return config


def validate_settings(config_data: dict[str, Any]) -> PinakSettings:
    """Validate a settings dictionary against PinakSettings schema, raising ConfigError on failure."""
    try:
        clean = _migrate_legacy_keys(config_data)
        return PinakSettings(**clean)
    except Exception as exc:
        raise ConfigError(f"Invalid configuration: {exc}") from exc


def save_config(config_data: dict[str, Any] | None = None) -> bool:
    global config
    if config_data is not None:
        config.update(config_data)

    try:
        valid_settings = validate_settings(config)
        config.update(valid_settings.model_dump())
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            f.write(valid_settings.model_dump_json(indent=4))
        return True
    except ConfigError as ce:
        print(f"\033[91m[X] Could not write {CONFIG_FILE}: {ce}\033[0m")
        print(f"\033[93m[!] Tip: {ce.hint}\033[0m")
        return False
    except Exception as e:
        print(f"\033[91m[X] Could not write {CONFIG_FILE}: {e}\033[0m")
        print(
            "\033[93m[!] Tip: check that values are valid (e.g. quality=best/720p, video_format=mp4). Run `pinak --doctor` for details.\033[0m"
        )
        return False
