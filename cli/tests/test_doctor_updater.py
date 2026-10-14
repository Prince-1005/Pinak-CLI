"""Unit tests for pinak.doctor and pinak.updater (all I/O mocked)."""

import json
import urllib.request

import pinak.doctor as doctor_mod
import pinak.updater as updater_mod


def _ok_version_binary(*args, **kwargs):
    class _R:
        returncode = 0
        stdout = ""
        stderr = ""

    return _R()


def test_doctor_all_ok(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(doctor_mod, "ensure_ffmpeg", lambda: "ffmpeg.exe")
    monkeypatch.setattr(doctor_mod, "ensure_ffprobe", lambda: "ffprobe.exe")
    monkeypatch.setattr(doctor_mod.shutil, "which", lambda name: "pinak")

    def _ok(*args, **kwargs):
        class _R:
            returncode = 0
            stdout = "ffmpeg version 7.0"
            stderr = ""

        return _R()

    monkeypatch.setattr(doctor_mod, "run_cmd", _ok)
    config_path = tmp_path / "config.json"
    monkeypatch.setitem(doctor_mod.config, "output_dir", str(tmp_path / "out"))
    monkeypatch.setattr(doctor_mod, "CONFIG_FILE", str(config_path))
    config_path.write_text("{}", encoding="utf-8")

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def close(self):
            pass

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _Resp())
    out_dir = str(tmp_path / "out")

    def _exists(p):
        p_str = str(p)
        return p_str in (
            "ffmpeg.exe",
            "ffprobe.exe",
            out_dir,
            str(config_path),
        ) or p_str.startswith(out_dir)

    monkeypatch.setattr("os.path.exists", _exists)
    assert doctor_mod.run_doctor() is True
    out = capsys.readouterr().out
    assert "All checks passed" in out


def test_doctor_reports_failures(monkeypatch, tmp_path, capsys):
    def _missing(path):
        return False, f"{path} (not found)"

    monkeypatch.setattr(doctor_mod, "_check_ffmpeg_executable", _missing)
    monkeypatch.setitem(doctor_mod.config, "output_dir", str(tmp_path / "out"))

    def _boom(*a, **k):
        raise OSError("offline")

    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    assert doctor_mod.run_doctor() is False
    out = capsys.readouterr().out
    assert "Some checks failed" in out


def test_check_ffmpeg_executable_empty():
    ok, detail = doctor_mod._check_ffmpeg_executable("")
    assert ok is False
    assert detail == "not configured"


def test_updater_detects_new_version(monkeypatch):
    import importlib.metadata

    payload = json.dumps({"info": {"version": "9999.0.0"}}).encode()

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return payload

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _Resp())
    monkeypatch.setattr(importlib.metadata, "version", lambda name: "2000.0.0")
    monkeypatch.setitem(updater_mod.config, "last_update_check", 0.0)
    updater_mod.UPDATE_AVAILABLE = None
    updater_mod._check_update_thread()
    assert updater_mod.UPDATE_AVAILABLE == "9999.0.0"
    updater_mod.UPDATE_AVAILABLE = None  # reset globals so other tests stay isolated
    updater_mod.PINAK_UPDATE_AVAILABLE = None


def test_updater_skips_recent_check(monkeypatch):
    import time

    monkeypatch.setitem(updater_mod.config, "last_update_check", time.time())
    updater_mod.UPDATE_AVAILABLE = None
    updater_mod._check_update_thread()  # must return early, no network
    assert updater_mod.UPDATE_AVAILABLE is None


def test_updater_silent_on_network_error(monkeypatch):
    def _boom(*a, **k):
        raise OSError("offline")

    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    monkeypatch.setitem(updater_mod.config, "last_update_check", 0.0)
    updater_mod.UPDATE_AVAILABLE = None
    updater_mod._check_update_thread()  # must not raise
    assert updater_mod.UPDATE_AVAILABLE is None


def test_doctor_internet_socket_fallback(monkeypatch, tmp_path):
    import socket

    monkeypatch.setattr(doctor_mod, "ensure_ffmpeg", lambda: "ffmpeg.exe")
    monkeypatch.setattr(doctor_mod, "ensure_ffprobe", lambda: "ffprobe.exe")
    monkeypatch.setattr(doctor_mod.shutil, "which", lambda name: "pinak")

    class _R:
        returncode = 0
        stdout = "ffmpeg version 7.0"
        stderr = ""

    monkeypatch.setattr(doctor_mod, "run_cmd", lambda *a, **k: _R())
    config_path = tmp_path / "config.json"
    monkeypatch.setitem(doctor_mod.config, "output_dir", str(tmp_path / "out"))
    monkeypatch.setattr(doctor_mod, "CONFIG_FILE", str(config_path))
    config_path.write_text("{}", encoding="utf-8")

    # Simulate HTTPS failing completely
    def _boom(*a, **k):
        raise OSError("https blocked")

    monkeypatch.setattr(urllib.request, "urlopen", _boom)

    # Simulate socket succeeding
    class _MockSock:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: _MockSock())

    out_dir = str(tmp_path / "out")

    def _exists(p):
        p_str = str(p)
        return p_str in (
            "ffmpeg.exe",
            "ffprobe.exe",
            out_dir,
            str(config_path),
        ) or p_str.startswith(out_dir)

    monkeypatch.setattr("os.path.exists", _exists)
    assert doctor_mod.run_doctor() is True
