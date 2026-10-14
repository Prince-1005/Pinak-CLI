"""Tests for pinak self-update: PyPI check for pinak-cli itself and /update
behavior (all network/subprocess I/O mocked)."""

import json
from types import SimpleNamespace

import pinak.commands.run as run_mod
import pinak.updater as updater_mod


def _pypi_response(version):
    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({"info": {"version": version}}).encode()

    return _Resp()


def _routed_urlopen(monkeypatch, versions):
    def _fake(req, *a, **k):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        for package, version in versions.items():
            if f"/pypi/{package}/json" in url:
                return _pypi_response(version)
        raise AssertionError(f"unexpected URL: {url}")

    import urllib.request

    monkeypatch.setattr(urllib.request, "urlopen", _fake)


def _fresh_check(monkeypatch):
    import time

    monkeypatch.setitem(updater_mod.config, "last_update_check", 0.0)
    updater_mod.UPDATE_AVAILABLE = None
    updater_mod.PINAK_UPDATE_AVAILABLE = None
    monkeypatch.setattr(time, "time", lambda: 10**10)


def test_check_detects_pinak_update(monkeypatch):
    _fresh_check(monkeypatch)
    _routed_urlopen(monkeypatch, {"yt-dlp": "2026.1.1", "pinak-cli": "9.9.9"})
    monkeypatch.setattr(
        updater_mod, "_installed_version", lambda pkg: "2020.0.0" if pkg == "yt-dlp" else None
    )
    monkeypatch.setattr(updater_mod, "_current_pinak_version", lambda: "1.0.0")
    monkeypatch.setattr(updater_mod, "save_config", lambda: None)
    updater_mod._check_update_thread()
    assert updater_mod.UPDATE_AVAILABLE == "2026.1.1"
    assert updater_mod.PINAK_UPDATE_AVAILABLE == "9.9.9"
    updater_mod.UPDATE_AVAILABLE = None
    updater_mod.PINAK_UPDATE_AVAILABLE = None


def test_check_quiet_when_current(monkeypatch):
    _fresh_check(monkeypatch)
    _routed_urlopen(monkeypatch, {"yt-dlp": "2026.1.1", "pinak-cli": "1.0.0"})
    monkeypatch.setattr(updater_mod, "_installed_version", lambda pkg: "2026.1.1")
    monkeypatch.setattr(updater_mod, "_current_pinak_version", lambda: "1.0.0")
    monkeypatch.setattr(updater_mod, "save_config", lambda: None)
    updater_mod._check_update_thread()
    assert updater_mod.UPDATE_AVAILABLE is None
    assert updater_mod.PINAK_UPDATE_AVAILABLE is None


def test_perform_update_reports_bump_and_latest(monkeypatch):
    seen = {
        "yt-dlp": ["2020.0.0", "2026.1.1"],
        "pinak-cli": ["1.0.0", "1.0.0"],
    }

    def _version(pkg):
        return seen[pkg].pop(0)

    monkeypatch.setattr(updater_mod, "_package_version", _version)
    monkeypatch.setattr(
        "pinak.subproc.run_cmd",
        lambda *a, **k: SimpleNamespace(returncode=0, stderr=""),
    )
    updater_mod.UPDATE_AVAILABLE = "2026.1.1"
    updater_mod.PINAK_UPDATE_AVAILABLE = "9.9.9"
    results = updater_mod.perform_update()
    assert results["yt-dlp"] == "Updated yt-dlp 2020.0.0 → 2026.1.1."
    assert "already the latest" in results["pinak-cli"]
    assert updater_mod.UPDATE_AVAILABLE is None
    assert updater_mod.PINAK_UPDATE_AVAILABLE is None


def test_perform_update_pip_failure_keeps_flag(monkeypatch):
    monkeypatch.setattr(updater_mod, "_package_version", lambda pkg: "1.0.0")
    monkeypatch.setattr(
        "pinak.subproc.run_cmd",
        lambda *a, **k: SimpleNamespace(returncode=1, stderr="boom"),
    )
    updater_mod.PINAK_UPDATE_AVAILABLE = "9.9.9"
    results = updater_mod.perform_update()
    assert "Update failed" in results["pinak-cli"]
    assert updater_mod.PINAK_UPDATE_AVAILABLE == "9.9.9"
    updater_mod.PINAK_UPDATE_AVAILABLE = None


def test_perform_update_exception_reported(monkeypatch):
    monkeypatch.setattr(updater_mod, "_package_version", lambda pkg: "1.0.0")

    def _boom(*a, **k):
        raise OSError("offline")

    monkeypatch.setattr("pinak.subproc.run_cmd", _boom)
    results = updater_mod.perform_update()
    assert "Update error" in results["yt-dlp"]
    assert "Update error" in results["pinak-cli"]


def test_perform_update_winerror32_actionable_message(monkeypatch):
    monkeypatch.setattr(updater_mod, "_package_version", lambda pkg: "1.0.0")
    monkeypatch.setattr(
        "pinak.subproc.run_cmd",
        lambda *a, **k: SimpleNamespace(
            returncode=1,
            stderr="ERROR: Could not install: [WinError 32] The process cannot access the file because it is being used by another process: pinak.exe",
            stdout="",
        ),
    )
    results = updater_mod.perform_update()
    assert "binary is currently in use on Windows" in results["pinak-cli"]
    assert "pip install --upgrade pinak-cli" in results["pinak-cli"]


def test_perform_update_renames_binary_on_windows(monkeypatch, tmp_path):
    fake_exe = tmp_path / "pinak.exe"
    fake_exe.write_text("dummy", encoding="utf-8")
    monkeypatch.setattr(updater_mod.sys, "platform", "win32")
    monkeypatch.setattr(updater_mod, "_find_pinak_binary", lambda: fake_exe)
    monkeypatch.setattr(updater_mod, "_package_version", lambda pkg: "1.0.0")

    seen_during_cmd = []

    def _mock_run(cmd, **kwargs):
        seen_during_cmd.append(fake_exe.exists())
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr("pinak.subproc.run_cmd", _mock_run)
    updater_mod.perform_update()
    # While running command for pinak-cli, fake_exe was temporarily renamed to .old
    assert False in seen_during_cmd
    # After success, .old target was cleaned up
    assert fake_exe.exists()
    assert not (tmp_path / "pinak.exe.old").exists()


def test_perform_update_renames_and_unlinks_when_new_binary_written(monkeypatch, tmp_path):
    fake_exe = tmp_path / "pinak.exe"
    fake_exe.write_text("old_content", encoding="utf-8")
    monkeypatch.setattr(updater_mod.sys, "platform", "win32")
    monkeypatch.setattr(updater_mod, "_find_pinak_binary", lambda: fake_exe)
    monkeypatch.setattr(updater_mod, "_package_version", lambda pkg: "1.0.0")

    def _mock_run(cmd, **kwargs):
        fake_exe.write_text("new_content", encoding="utf-8")
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr("pinak.subproc.run_cmd", _mock_run)
    updater_mod.perform_update()
    assert fake_exe.read_text(encoding="utf-8") == "new_content"
    assert not (tmp_path / "pinak.exe.old").exists()


def test_find_pinak_binary(monkeypatch, tmp_path):
    monkeypatch.setattr(updater_mod.shutil, "which", lambda name: str(tmp_path / name))
    (tmp_path / "pinak.exe").write_text("x", encoding="utf-8")
    found = updater_mod._find_pinak_binary()
    assert found is not None
    assert found.name == "pinak.exe"


def test_run_single_prints_pinak_notice(monkeypatch, capsys):
    monkeypatch.setattr(run_mod.updater, "UPDATE_AVAILABLE", None)
    monkeypatch.setattr(run_mod.updater, "PINAK_UPDATE_AVAILABLE", "9.9.9")
    monkeypatch.setattr(run_mod.updater, "PINAK_PACKAGE", "pinak-cli")
    monkeypatch.setattr(run_mod, "handle_download", lambda *a, **k: {"success": True, "files": []})
    monkeypatch.setattr(
        run_mod, "print_update_notice", lambda *a, **k: print(f"PINAK-MARKER-{a[1]}")
    )
    code = run_mod.run_single(
        "https://example.com/v", None, False, False, None, False, False, False, False
    )
    assert code == 0
    assert "PINAK-MARKER-9.9.9" in capsys.readouterr().out
    run_mod.updater.PINAK_UPDATE_AVAILABLE = None
