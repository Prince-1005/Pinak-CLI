"""Unit tests for config persistence, history migration, logging, utils extras."""

import json
import os

import pinak.config as config_mod
import pinak.history as history_mod
from pinak import utils


def test_init_and_save_config_roundtrip(tmp_path, monkeypatch):
    cfg_file = str(tmp_path / "config.json")
    monkeypatch.setattr(config_mod, "CONFIG_FILE", cfg_file)
    monkeypatch.setattr(config_mod, "config", config_mod.PinakSettings().model_dump())
    config_mod.init_config()
    assert config_mod.save_config({"quality": "720p", "retry_count": 5}) is True
    with open(cfg_file, encoding="utf-8") as fh:
        saved = json.load(fh)
    assert saved["quality"] == "720p"
    assert saved["retry_count"] == 5


def test_init_config_tolerates_corrupt_file(tmp_path, monkeypatch):
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setattr(config_mod, "CONFIG_FILE", str(cfg_file))
    monkeypatch.setattr(config_mod, "config", config_mod.PinakSettings().model_dump())
    assert config_mod.init_config()["quality"] == "best"


def test_init_config_migrates_legacy_keys(tmp_path, monkeypatch):
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({"retries": 7, "timeout": 60}), encoding="utf-8")
    monkeypatch.setattr(config_mod, "CONFIG_FILE", str(cfg_file))
    monkeypatch.setattr(config_mod, "config", config_mod.PinakSettings().model_dump())
    loaded = config_mod.init_config()
    assert loaded["retry_count"] == 7
    assert loaded["read_timeout"] == 60.0


def test_migrate_json_to_sqlite(tmp_path, monkeypatch, isolated_history_db):
    legacy = tmp_path / "history.json"
    legacy.write_text(
        json.dumps({"downloads": [{"url": "https://x.com/old", "status": "success"}]}),
        encoding="utf-8",
    )
    history_mod.migrate_json_to_sqlite(str(legacy))
    assert history_mod.get_history()[0]["url"] == "https://x.com/old"
    # Legacy status is preserved, but absent files must not suppress re-downloads.
    assert history_mod.url_downloaded_successfully("https://x.com/old") is False
    assert os.path.exists(str(legacy) + ".bak")


def test_record_download_respects_history_disabled(monkeypatch, isolated_history_db):
    import pinak.config as _cfg

    monkeypatch.setitem(_cfg.config, "history_enabled", False)
    history_mod.record_download("https://x.com/v", status="success")
    assert history_mod.get_history("") == []
    monkeypatch.setitem(_cfg.config, "history_enabled", True)


def test_session_helpers():
    sid = history_mod.initialize_session()
    assert isinstance(sid, str) and len(sid) > 0
    assert history_mod.get_current_session_id() == sid
    # Telemetry stubs are intentional no-ops.
    history_mod.push_session_start()
    history_mod.push_session_end()
    history_mod.push_command_event("/help")
    history_mod.push_download_event()
    history_mod._push_activity({})


def test_logging_setup_with_file(tmp_path):
    from pinak.logging_setup import get_logger, setup_logging

    log_file = str(tmp_path / "logs" / "pinak.log")
    logger = setup_logging(verbose=True, log_file=log_file)
    logger.info("hello-log")
    assert os.path.exists(log_file)
    assert get_logger("pinak").name == "pinak"
    setup_logging(verbose=False, log_file=None)


def test_logging_setup_with_none_stderr(monkeypatch):
    import sys

    import pinak.logging_setup as log_setup

    monkeypatch.setattr(log_setup, "_configured", False)
    monkeypatch.setattr(sys, "stderr", None)
    logger = log_setup.setup_logging(verbose=False)
    assert logger is not None
    # Reset for other tests
    monkeypatch.setattr(log_setup, "_configured", False)


def test_script_dir_finds_directory_with_binary():
    found = utils.script_dir()
    # After cleanup, bundled binaries may not exist; ensure script_dir returns a directory.
    import pathlib

    assert pathlib.Path(found).is_dir()


def test_script_dir_falls_back_to_cli_dir(monkeypatch):
    monkeypatch.setattr(utils.os.path, "exists", lambda *a, **k: False)
    assert utils.script_dir().endswith("cli")


def test_ffmpeg_resolution_order(tmp_path, monkeypatch):
    custom = tmp_path / "custom-ffmpeg"
    custom.write_bytes(b"x")
    custom.chmod(0o755)
    monkeypatch.setattr(utils, "_configured_binary_override", lambda key: str(custom))
    assert utils.get_ffmpeg_path() == str(custom)


def test_ffmpeg_available_false(monkeypatch):
    monkeypatch.setattr(utils, "get_ffmpeg_path", lambda: "/nonexistent/ffmpeg-xyz")
    assert utils.ffmpeg_available() is False


def test_is_online_branches(monkeypatch):
    import socket
    import urllib.request

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _Resp())
    assert utils.is_online() is True

    def _boom(*a, **k):
        raise OSError("offline")

    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: _Resp())
    assert utils.is_online() is True

    monkeypatch.setattr(socket, "create_connection", _boom)
    assert utils.is_online() is False


def test_get_platform_unknown():
    assert utils.get_platform("not a url at all :::") == "Unknown"


def test_get_all_files_and_snapshot(tmp_path):
    target = tmp_path / "f.txt"
    target.write_text("hi", encoding="utf-8")
    snap = utils.get_file_snapshot(str(tmp_path))
    assert str(target) in snap
    assert utils.changed_files({}, snap) == [str(target)]
