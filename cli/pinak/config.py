from __future__ import annotations

import contextlib
import json
import logging
import os
import shutil
import tempfile
import threading
from typing import Any

import platformdirs
from filelock import FileLock
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .exceptions import ConfigError
from .subtitle_preferences import MAX_SUBTITLE_LANGUAGES, normalize_subtitle_languages

_config_lock = threading.RLock()
_loaded_snapshots: dict[str, dict[str, Any]] = {}
log = logging.getLogger("pinak.config")

APP_NAME = "pinak-cli"
APP_AUTHOR = "pinak"

# Determine standard config directory
config_dir = platformdirs.user_config_dir(APP_NAME, APP_AUTHOR)
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
        default=10.0,
        ge=1.0,
        le=120.0,
        description="yt-dlp socket timeout cap in seconds (also applies while reading)",
    )
    read_timeout: float = Field(
        default=30.0,
        ge=5.0,
        le=600.0,
        description="Read/download socket timeout cap, also limited by connect_timeout",
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
    subtitle_languages: list[str] = Field(
        default_factory=lambda: ["en"],
        description=f"Subtitle language codes (1 to {MAX_SUBTITLE_LANGUAGES})",
    )
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

    @field_validator("subtitle_languages", mode="before")
    @classmethod
    def _validate_subtitle_languages(cls, value: Any) -> list[str]:
        return normalize_subtitle_languages(value)

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


class _StoredSettings(PinakSettings):
    """Validate persisted preferences without importing invocation environment values."""

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: Any,
        env_settings: Any,
        dotenv_settings: Any,
        file_secret_settings: Any,
    ) -> tuple[Any, ...]:
        return (init_settings,)


# Legacy global dictionary for backward compatibility across modules
config: dict[str, Any] = PinakSettings.model_construct().model_dump()


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
    with _config_lock:
        # Migrate legacy ~/.pinak_config.json if exists
        legacy_home_config = os.path.expanduser("~/.pinak_config.json")
        try:
            os.makedirs(os.path.dirname(CONFIG_FILE) or ".", exist_ok=True)
            with FileLock(CONFIG_FILE + ".lock", timeout=5):
                if not os.path.exists(CONFIG_FILE):
                    if os.path.exists(legacy_home_config):
                        shutil.copy(legacy_home_config, CONFIG_FILE)
                    elif os.path.exists(LOCAL_CONFIG):
                        shutil.copy(LOCAL_CONFIG, CONFIG_FILE)
        except (OSError, TimeoutError) as exc:
            log.warning("Configuration storage unavailable: %s", exc)

        def _load_from_path(path: str) -> bool:
            if not os.path.exists(path):
                return False
            with open(path, encoding="utf-8") as f:
                raw = f.read().strip()
            if not raw:
                return False
            data = json.loads(raw)
            if isinstance(data, dict):
                data = _migrate_legacy_keys(data)
                # Environment overrides apply to the invocation; they are not saved
                # unless explicitly changed by a preferences command.
                data = {k: v for k, v in data.items() if "PINAK_" + k.upper() not in os.environ}
                settings = PinakSettings(**data)
                config.update(settings.model_dump())
                return True
            return False

        loaded = False
        try:
            loaded = _load_from_path(CONFIG_FILE)
        except Exception:
            loaded = False

        # Fallback to backup file if primary CONFIG_FILE was missing, empty, or corrupted
        if not loaded:
            bak_file = CONFIG_FILE + ".bak"
            with contextlib.suppress(Exception):
                if _load_from_path(bak_file):
                    loaded = True
                    with FileLock(CONFIG_FILE + ".lock", timeout=5):
                        try:
                            primary_valid = _load_from_path(CONFIG_FILE)
                        except (ValueError, OSError):
                            primary_valid = False
                        if not primary_valid:
                            with tempfile.NamedTemporaryFile(
                                dir=os.path.dirname(CONFIG_FILE) or ".", delete=False
                            ) as recovery:
                                recovery_path = recovery.name
                            try:
                                shutil.copy2(bak_file, recovery_path)
                                os.replace(recovery_path, CONFIG_FILE)
                            finally:
                                if os.path.exists(recovery_path):
                                    os.unlink(recovery_path)

        if not loaded:
            try:
                config.update(PinakSettings().model_dump())
            except Exception as exc:
                log.warning("Invalid environment settings; using safe defaults: %s", exc)
        _loaded_snapshots[CONFIG_FILE] = config.copy()
        return config


def validate_settings(config_data: dict[str, Any]) -> PinakSettings:
    """Validate a settings dictionary against PinakSettings schema, raising ConfigError on failure."""
    try:
        clean = _migrate_legacy_keys(config_data)
        return _StoredSettings(**clean)
    except Exception as exc:
        raise ConfigError(f"Invalid configuration: {exc}") from exc


def save_config(config_data: dict[str, Any] | None = None) -> bool:
    global config
    with _config_lock:
        if config_data is not None:
            config.update(config_data)

        temp_file = ""
        bak_file = CONFIG_FILE + ".bak"
        try:
            parent_dir = os.path.dirname(CONFIG_FILE)
            if parent_dir:
                os.makedirs(parent_dir, exist_ok=True)

            with FileLock(CONFIG_FILE + ".lock", timeout=5):
                baseline = _loaded_snapshots.get(
                    CONFIG_FILE, PinakSettings.model_construct().model_dump()
                )
                changes = {k: v for k, v in config.items() if baseline.get(k) != v}
                if config_data:
                    changes.update(config_data)
                disk: dict[str, Any] = {}
                if os.path.exists(CONFIG_FILE):
                    try:
                        with open(CONFIG_FILE, encoding="utf-8") as existing:
                            raw = json.load(existing)
                    except (ValueError, OSError):
                        with open(bak_file, encoding="utf-8") as backup:
                            raw = json.load(backup)
                    if not isinstance(raw, dict):
                        raise ConfigError("Configuration must be a JSON object")
                    disk = _migrate_legacy_keys(raw)
                valid_settings = validate_settings({**disk, **changes})
                serialized = valid_settings.model_dump_json(indent=4)
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    dir=parent_dir or ".",
                    prefix=".pinak-config-",
                    suffix=".tmp",
                    delete=False,
                ) as f:
                    temp_file = f.name
                    f.write(serialized)
                    f.flush()
                    os.fsync(f.fileno())
                if os.path.exists(CONFIG_FILE):
                    try:
                        with open(CONFIG_FILE, encoding="utf-8") as primary:
                            validate_settings(json.load(primary))
                    except (ValueError, OSError, ConfigError):
                        pass  # Retain the valid backup when repairing a damaged primary.
                    else:
                        shutil.copy2(CONFIG_FILE, bak_file)
                os.replace(temp_file, CONFIG_FILE)
                # Preserve invocation-only environment overrides in memory.
                merged_runtime = PinakSettings(
                    **{
                        k: v
                        for k, v in valid_settings.model_dump().items()
                        if "PINAK_" + k.upper() not in os.environ or k in changes
                    }
                )
                config.update(merged_runtime.model_dump())
                _loaded_snapshots[CONFIG_FILE] = config.copy()
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
        finally:
            if os.path.exists(temp_file):
                with contextlib.suppress(Exception):
                    os.remove(temp_file)
