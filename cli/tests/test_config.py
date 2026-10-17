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


def test_save_config_creates_backup_and_atomic_replace(tmp_path, monkeypatch):
    import pinak.config as cfg_mod

    cfg_file = tmp_path / "config.json"
    monkeypatch.setattr(cfg_mod, "CONFIG_FILE", str(cfg_file))
    monkeypatch.setattr(cfg_mod, "config", cfg_mod.PinakSettings().model_dump())

    # First save: creates config.json
    assert cfg_mod.save_config({"quality": "720p"}) is True
    assert cfg_file.exists()
    assert not (tmp_path / "config.json.bak").exists()

    # Second save: creates config.json.bak from previous config.json
    assert cfg_mod.save_config({"quality": "1080p"}) is True
    bak_file = tmp_path / "config.json.bak"
    assert bak_file.exists()
    assert "720p" in bak_file.read_text(encoding="utf-8")
    assert "1080p" in cfg_file.read_text(encoding="utf-8")


def test_init_config_recovers_from_backup_when_primary_corrupted(tmp_path, monkeypatch):
    import pinak.config as cfg_mod

    cfg_file = tmp_path / "config.json"
    bak_file = tmp_path / "config.json.bak"

    # Primary is corrupted
    cfg_file.write_text("CORRUPTED-NOT-JSON{{{{", encoding="utf-8")
    # Backup is valid with customized setting
    bak_file.write_text('{"quality": "720p", "retry_count": 5}', encoding="utf-8")

    monkeypatch.setattr(cfg_mod, "CONFIG_FILE", str(cfg_file))
    monkeypatch.setattr(cfg_mod, "config", cfg_mod.PinakSettings().model_dump())

    loaded = cfg_mod.init_config()
    assert loaded["quality"] == "720p"
    assert loaded["retry_count"] == 5
    # Primary config file should also be restored from .bak
    assert "720p" in cfg_file.read_text(encoding="utf-8")


def test_concurrent_save_and_init_config(tmp_path, monkeypatch):
    """Verifies that concurrent save_config and init_config calls across threads run safely without corruption (RACE-03)."""
    import threading

    import pinak.config as cfg_mod

    cfg_file = tmp_path / "config.json"
    monkeypatch.setattr(cfg_mod, "CONFIG_FILE", str(cfg_file))
    monkeypatch.setattr(cfg_mod, "config", cfg_mod.PinakSettings().model_dump())

    errors = []

    def writer(thread_id: int):
        try:
            for i in range(10):
                cfg_mod.save_config({"last_update_check": float(thread_id * 100 + i)})
        except Exception as e:
            errors.append(e)

    def reader():
        try:
            for _ in range(10):
                cfg_mod.init_config()
        except Exception as e:
            errors.append(e)

    threads = [
        threading.Thread(target=writer, args=(1,)),
        threading.Thread(target=writer, args=(2,)),
        threading.Thread(target=reader),
    ]

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert cfg_file.exists()
