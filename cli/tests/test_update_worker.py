"""Deferred Windows update completion without touching the real installation."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from pinak import update_worker


def test_worker_waits_then_upgrades_and_verifies(monkeypatch, tmp_path):
    status = tmp_path / "result.json"
    waited = []
    commands = []
    monkeypatch.setattr(
        update_worker,
        "wait_for_process_exit",
        lambda pid: waited.append(pid) or True,
    )
    monkeypatch.setattr(
        update_worker, "_stage_rollback_wheel", lambda directory: directory / "previous.whl"
    )

    def fake_run(command, **kwargs):
        commands.append(command)
        if "pip" in command:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        return SimpleNamespace(returncode=0, stdout="9.9.9\n", stderr="")

    monkeypatch.setattr(update_worker.subprocess, "run", fake_run)
    update_worker.finish_update([11, 12], status)
    assert waited == [11, 12]
    assert commands[0][-2:] == ["--upgrade", "pinak-cli"]
    assert json.loads(status.read_text())["state"] == "succeeded"
    assert "9.9.9" in status.read_text()


def test_worker_failure_does_not_expose_pip_output(monkeypatch, tmp_path):
    status = tmp_path / "result.json"
    monkeypatch.setattr(update_worker, "wait_for_process_exit", lambda pid: True)
    monkeypatch.setattr(
        update_worker, "_stage_rollback_wheel", lambda directory: directory / "previous.whl"
    )
    restored = []
    monkeypatch.setattr(
        update_worker, "_restore_previous", lambda wheel: restored.append(wheel) or True
    )
    monkeypatch.setattr(
        update_worker.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=1, stderr="token=secret", stdout=""),
    )
    update_worker.finish_update([11], status)
    result = json.loads(status.read_text())
    assert result["state"] == "failed"
    assert "token=secret" not in result["message"]
    assert restored and "Previous release restored" in result["message"]


def test_worker_does_not_upgrade_without_rollback_wheel(monkeypatch, tmp_path):
    status = tmp_path / "result.json"
    monkeypatch.setattr(update_worker, "wait_for_process_exit", lambda pid: True)
    monkeypatch.setattr(update_worker, "_stage_rollback_wheel", lambda directory: None)
    monkeypatch.setattr(
        update_worker.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("upgrade must not start")),
    )
    update_worker.finish_update([11], status)
    assert json.loads(status.read_text())["state"] == "failed"


def test_worker_does_not_run_pip_while_launcher_is_open(monkeypatch, tmp_path):
    status = tmp_path / "result.json"
    monkeypatch.setattr(update_worker, "wait_for_process_exit", lambda pid: False)
    monkeypatch.setattr(
        update_worker.subprocess,
        "run",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("pip must not run")),
    )
    update_worker.finish_update([11], status)
    assert json.loads(status.read_text())["state"] == "failed"


@pytest.mark.skipif(not sys.platform.startswith("win"), reason="Windows process handles only")
def test_windows_handle_waits_for_real_process_exit():
    process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(0.2)"])
    try:
        assert update_worker.wait_for_process_exit(process.pid, timeout_seconds=5)
    finally:
        process.wait(timeout=5)


@pytest.mark.skipif(not sys.platform.startswith("win"), reason="Windows helper launch only")
def test_detached_helper_becomes_ready_without_running_pip(tmp_path):
    status = tmp_path / "result.json"
    parent = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    helper = None
    try:
        helper = subprocess.Popen(
            [sys.executable, "-m", "pinak.update_worker", str(parent.pid), str(status)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            creationflags=0x00000008 | 0x00000200,
        )
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not status.exists():
            time.sleep(0.05)
        assert json.loads(status.read_text())["state"] == "waiting"
        assert helper.poll() is None
    finally:
        if helper is not None and helper.poll() is None:
            helper.terminate()
            helper.wait(timeout=5)
        parent.terminate()
        parent.wait(timeout=5)
