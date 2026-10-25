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
    monkeypatch.setattr(updater_mod.sys, "platform", "linux")
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
    monkeypatch.setattr(updater_mod.sys, "platform", "linux")
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
    monkeypatch.setattr(updater_mod.sys, "platform", "linux")
    monkeypatch.setattr(updater_mod, "_package_version", lambda pkg: "1.0.0")

    def _boom(*a, **k):
        raise OSError("offline")

    monkeypatch.setattr("pinak.subproc.run_cmd", _boom)
    results = updater_mod.perform_update()
    assert "Update error" in results["yt-dlp"]
    assert "Update error" in results["pinak-cli"]


def test_perform_update_defers_pinak_on_windows(monkeypatch):
    monkeypatch.setattr(updater_mod.sys, "platform", "win32")
    monkeypatch.setattr(updater_mod, "_package_version", lambda pkg: "1.0.0")
    monkeypatch.setattr(updater_mod, "_fetch_latest_version", lambda pkg: "9.9.9")
    monkeypatch.setattr(
        updater_mod, "_schedule_windows_pinak_update", lambda: "Pinak update is queued."
    )
    calls = []

    def _run(cmd, **kwargs):
        calls.append(cmd)
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(
        "pinak.subproc.run_cmd",
        _run,
    )
    results = updater_mod.perform_update()
    assert results["pinak-cli"] == "Pinak update is queued."
    assert len(calls) == 1 and calls[0][-1] == "yt-dlp"


def test_perform_update_skips_current_pinak_on_windows(monkeypatch):
    monkeypatch.setattr(updater_mod.sys, "platform", "win32")
    monkeypatch.setattr(updater_mod, "_package_version", lambda pkg: "2.3.0")
    monkeypatch.setattr(updater_mod, "_fetch_latest_version", lambda pkg: "2.3.0")
    monkeypatch.setattr(
        updater_mod,
        "_schedule_windows_pinak_update",
        lambda: (_ for _ in ()).throw(AssertionError("should not queue")),
    )
    monkeypatch.setattr(
        "pinak.subproc.run_cmd",
        lambda *a, **k: SimpleNamespace(returncode=0, stderr="", stdout=""),
    )
    assert "already the latest" in updater_mod.perform_update()["pinak-cli"]


def test_windows_schedule_and_update_result(monkeypatch, tmp_path):
    from pinak.update_worker import write_status

    status = tmp_path / "update-result.json"
    monkeypatch.setattr(updater_mod, "CONFIG_FILE", str(tmp_path / "config.json"))
    monkeypatch.setattr(
        updater_mod.psutil,
        "Process",
        lambda pid: SimpleNamespace(parent=lambda: None, create_time=lambda: 1000.0),
    )
    launched = []

    def fake_popen(cmd, **kwargs):
        launched.append((cmd, kwargs))
        write_status(status, "waiting", "Ready")
        return SimpleNamespace(poll=lambda: None)

    monkeypatch.setattr(
        updater_mod.subprocess,
        "Popen",
        fake_popen,
    )
    message = updater_mod._schedule_windows_pinak_update()
    assert "queued" in message and len(launched) == 1
    assert launched[0][0][1:3] == ["-m", "pinak.update_worker"]
    assert json.loads(status.read_text())["state"] == "waiting"
    assert updater_mod.take_update_result() is None and status.exists()
    assert "already queued" in updater_mod._schedule_windows_pinak_update()
    assert len(launched) == 1
    write_status(status, "succeeded", "Installed version: 9.9.9.")
    assert updater_mod.take_update_result() == {
        "state": "succeeded",
        "message": "Installed version: 9.9.9.",
    }
    assert not status.exists()


def test_stale_deferred_update_status_does_not_block_retry(monkeypatch):
    monkeypatch.setattr(updater_mod.time, "time", lambda: 100.0)
    assert not updater_mod._status_worker_live({"state": "pending", "time": 1.0})
    monkeypatch.setattr(
        updater_mod.psutil,
        "Process",
        lambda pid: (_ for _ in ()).throw(updater_mod.psutil.NoSuchProcess(pid)),
    )
    assert not updater_mod._status_worker_live(
        {"state": "waiting", "pid": 999999, "process_started": 1.0}
    )


def test_windows_schedule_falls_back_when_helper_cannot_start(monkeypatch, tmp_path):
    status = tmp_path / "update-result.json"
    monkeypatch.setattr(updater_mod, "CONFIG_FILE", str(tmp_path / "config.json"))
    monkeypatch.setattr(
        updater_mod.psutil,
        "Process",
        lambda pid: SimpleNamespace(parent=lambda: None, create_time=lambda: 1000.0),
    )

    def fail(*args, **kwargs):
        raise OSError("launcher blocked")

    monkeypatch.setattr(updater_mod.subprocess, "Popen", fail)
    message = updater_mod._schedule_windows_pinak_update()
    assert "Could not start" in message
    assert "-m pip install --upgrade pinak-cli" in message
    assert json.loads(status.read_text())["state"] == "failed"


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
