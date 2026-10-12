"""Unit tests for pinak.config — Pydantic validation & migration."""

import pytest
from pydantic import ValidationError

from pinak.config import PinakSettings, _migrate_legacy_keys, validate_settings
from pinak.exceptions import ConfigError


def test_defaults_are_sane():
    s = PinakSettings()
    assert s.quality == "best"
    assert s.video_format == "mp4"
    assert s.audio_format == "mp3"
    assert s.retry_count == 3
    assert s.connect_timeout >= 1.0
    assert s.read_timeout >= 5.0


def test_quality_validator_accepts_resolutions():
    assert PinakSettings(quality="720p").quality == "720p"
    assert PinakSettings(quality="1080").quality == "1080p"
    assert PinakSettings(quality="best").quality == "best"


def test_quality_validator_rejects_garbage():
    with pytest.raises(ValidationError):
        PinakSettings(quality="super-hd")


def test_video_format_validator():
    assert PinakSettings(video_format="MKV").video_format == "mkv"
    with pytest.raises(ValidationError):
        PinakSettings(video_format="exe")


def test_audio_format_validator():
    assert PinakSettings(audio_format="M4A").audio_format == "m4a"
    with pytest.raises(ValidationError):
        PinakSettings(audio_format="exe")


def test_audio_quality_validator():
    assert PinakSettings(audio_quality="320").audio_quality == "320"
    with pytest.raises(ValidationError):
        PinakSettings(audio_quality="999")


def test_retry_count_bounds():
    with pytest.raises(ValidationError):
        PinakSettings(retry_count=0)
    with pytest.raises(ValidationError):
        PinakSettings(retry_count=99)


def test_duplicate_action_validator():
    assert PinakSettings(duplicate_action="SKIP").duplicate_action == "skip"
    with pytest.raises(ValidationError):
        PinakSettings(duplicate_action="explode")


def test_migrate_legacy_keys():
    migrated = _migrate_legacy_keys({"retries": 5, "timeout": 60, "bogus": 1})
    assert migrated == {"retry_count": 5, "read_timeout": 60}


def test_validate_settings_success():
    settings = validate_settings({"quality": "720p", "retries": 4})
    assert settings.quality == "720p"
    assert settings.retry_count == 4


def test_validate_settings_raises_config_error():
    with pytest.raises(ConfigError) as exc_info:
        validate_settings({"quality": "invalid_quality_mode"})
    assert "Invalid configuration" in str(exc_info.value)
    assert exc_info.value.hint != ""
