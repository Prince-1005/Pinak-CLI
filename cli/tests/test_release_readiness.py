"""Tests for release-readiness features: notify, ffmpeg install, offline/update
notices, config-path visibility, and the doctor PATH check (all I/O mocked)."""

import json
from types import SimpleNamespace

from typer.testing import CliRunner

import pinak.cli as cli_mod
import pinak.commands.run as run_mod
import pinak.doctor as doctor_mod
import pinak.ffmpeg_setup as ff_mod
import pinak.notify as notify_mod
from pinak.cli import app
from pinak.commands.info import show_config

runner = CliRunner()


def _no_toast(monkeypatch):
    import shutil

    monkeypatch.setattr(notify_mod, "_toast", None)
    monkeypatch.setattr(shutil, "which", lambda cmd: None)


def _sync_threads(monkeypatch):
    class _SyncThread:
        def __init__(self, target=None, daemon=None):
            self._target = target

        def start(self):
            self._target()

    monkeypatch.setattr(notify_mod.threading, "Thread", _SyncThread)


def test_notify_falls_back_to_panel(monkeypatch, capsys):
    _no_toast(monkeypatch)
    notify_mod.notify("Hello", "world")
    out = capsys.readouterr().out
    assert "Hello" in out and "world" in out


def test_notify_uses_toast_when_available(monkeypatch):
    calls = []
    monkeypatch.setattr(notify_mod, "_toast", lambda *a, **k: calls.append(a))
    _sync_threads(monkeypatch)
    notify_mod.notify("T", "M")
    assert calls and calls[0][:2] == ("T", "M")


def test_notify_uses_macos_osascript(monkeypatch):
    import shutil
    import subprocess
    import sys

    _no_toast(monkeypatch)
    _sync_threads(monkeypatch)
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(
        shutil, "which", lambda cmd: "/usr/bin/osascript" if cmd == "osascript" else None
    )

    runs = []
    monkeypatch.setattr(subprocess, "run", lambda cmd, **k: runs.append(cmd))
    notify_mod.notify("Mac Title", "Mac Message")
    assert runs and runs[0][0] == "osascript"
    assert "display notification" in runs[0][2]


def test_notify_uses_linux_notifysend(monkeypatch):
    import shutil
    import subprocess
    import sys

    _no_toast(monkeypatch)
    _sync_threads(monkeypatch)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(
        shutil, "which", lambda cmd: "/usr/bin/notify-send" if cmd == "notify-send" else None
    )

    runs = []
    monkeypatch.setattr(subprocess, "run", lambda cmd, **k: runs.append(cmd))
    notify_mod.notify("Linux Title", "Linux Message")
    assert runs and runs[0] == ["notify-send", "Linux Title", "Linux Message"]


def test_notify_silences_toast_callbacks_and_output(monkeypatch, capsys):
    toast_kwargs = {}

    def _mock_toast(*a, **kwargs):
        toast_kwargs.update(kwargs)
        print("ToastDismissalReason.TIMED_OUT")
        if callable(kwargs.get("on_dismissed")):
            kwargs["on_dismissed"]("reason")

    monkeypatch.setattr(notify_mod, "_toast", _mock_toast)
    _sync_threads(monkeypatch)
    notify_mod.notify("Title", "Message")

    out = capsys.readouterr().out
    assert "ToastDismissalReason.TIMED_OUT" not in out
    assert callable(toast_kwargs.get("on_dismissed"))
    assert callable(toast_kwargs.get("on_click"))
    assert callable(toast_kwargs.get("on_failed"))


def test_offline_notice_panel(monkeypatch, capsys):
    _no_toast(monkeypatch)
    monkeypatch.setattr(notify_mod, "notify", lambda *a, **k: None)
    notify_mod.print_offline_notice()
    assert "offline" in capsys.readouterr().out.lower()


def test_instagram_notice_panel(monkeypatch, capsys):
    _no_toast(monkeypatch)
    monkeypatch.setattr(notify_mod, "notify", lambda *a, **k: None)
    notify_mod.print_instagram_notice("429 too many")
    out = capsys.readouterr().out
    assert "Instagram" in out and "429" in out


def test_update_notice_panel(monkeypatch, capsys):
    _no_toast(monkeypatch)
    monkeypatch.setattr(notify_mod, "notify", lambda *a, **k: None)
    notify_mod.print_update_notice("yt-dlp", "9999.0.0")
    out = capsys.readouterr().out
    assert "9999.0.0" in out and "/update" in out


def test_install_ffmpeg_skips_when_present(monkeypatch):
    monkeypatch.setattr(ff_mod, "ensure_ffmpeg", lambda: "/bin/ffmpeg")
    monkeypatch.setattr(ff_mod, "_is_executable", lambda p: True)
    assert ff_mod.install_ffmpeg_extra() == "/bin/ffmpeg"


def test_install_ffmpeg_pip_failure(monkeypatch):
    monkeypatch.setattr(ff_mod, "ensure_ffmpeg", lambda: "")
    monkeypatch.setattr(ff_mod, "_is_executable", lambda p: False)
    monkeypatch.setattr(
        "pinak.subproc.run_cmd",
        lambda *a, **k: SimpleNamespace(returncode=1, stderr="nope"),
    )
    assert ff_mod.install_ffmpeg_extra() == ""


def test_install_ffmpeg_pip_exception(monkeypatch):
    monkeypatch.setattr(ff_mod, "ensure_ffmpeg", lambda: "")
    monkeypatch.setattr(ff_mod, "_is_executable", lambda p: False)

    def _boom(*a, **k):
        raise OSError("offline")

    monkeypatch.setattr("pinak.subproc.run_cmd", _boom)
    assert ff_mod.install_ffmpeg_extra() == ""


def test_install_ffmpeg_success(monkeypatch):
    calls = {"n": 0}

    def _ensure():
        calls["n"] += 1
        return "" if calls["n"] == 1 else "/cache/ffmpeg"

    monkeypatch.setattr(ff_mod, "ensure_ffmpeg", _ensure)
    monkeypatch.setattr(ff_mod, "_is_executable", lambda p: p == "/cache/ffmpeg")
    monkeypatch.setattr(ff_mod, "_try_static_ffmpeg", lambda: True)
    monkeypatch.setattr(
        "pinak.subproc.run_cmd",
        lambda *a, **k: SimpleNamespace(returncode=0, stderr=""),
    )
    assert ff_mod.install_ffmpeg_extra() == "/cache/ffmpeg"


def test_maybe_print_offline_notice_online(monkeypatch, capsys):
    monkeypatch.setattr("pinak.utils.is_online", lambda *a, **k: True)
    assert cli_mod.maybe_print_offline_notice() is True
    assert capsys.readouterr().out == ""


def test_maybe_print_offline_notice_offline(monkeypatch, capsys):
    monkeypatch.setattr("pinak.utils.is_online", lambda *a, **k: False)
    monkeypatch.setattr(cli_mod, "print_offline_notice", lambda: print("OFFLINE-MARKER"))
    assert cli_mod.maybe_print_offline_notice() is False
    assert "OFFLINE-MARKER" in capsys.readouterr().out


def test_config_path_flag():
    result = runner.invoke(app, ["--config-path"])
    assert result.exit_code == 0, result.output
    assert "config.json" in result.output


def test_install_ffmpeg_flag_success(monkeypatch):
    monkeypatch.setattr("pinak.ffmpeg_setup.install_ffmpeg_extra", lambda *a, **k: "/cache/ffmpeg")
    result = runner.invoke(app, ["--install-ffmpeg"])
    assert result.exit_code == 0, result.output
    assert "/cache/ffmpeg" in result.output


def test_install_ffmpeg_flag_failure(monkeypatch):
    monkeypatch.setattr("pinak.ffmpeg_setup.install_ffmpeg_extra", lambda *a, **k: "")
    result = runner.invoke(app, ["--install-ffmpeg"])
    assert result.exit_code == 1
    assert "ffmpeg.org" in result.output


def test_run_single_prints_update_notice(monkeypatch, capsys):
    monkeypatch.setattr(run_mod.updater, "UPDATE_AVAILABLE", "9999.0.0")
    monkeypatch.setattr(run_mod.updater, "UPDATE_PACKAGE", "yt-dlp")
    monkeypatch.setattr(run_mod, "handle_download", lambda *a, **k: {"success": True, "files": []})
    monkeypatch.setattr(run_mod, "print_update_notice", lambda *a, **k: print("UPDATE-MARKER"))
    code = run_mod.run_single(
        "https://example.com/v", None, False, False, None, False, False, False, False
    )
    assert code == 0
    assert "UPDATE-MARKER" in capsys.readouterr().out


def test_run_single_json_has_no_notice(monkeypatch, capsys):
    monkeypatch.setattr(run_mod.updater, "UPDATE_AVAILABLE", "9999.0.0")
    monkeypatch.setattr(
        run_mod,
        "handle_download",
        lambda *a, **k: {"success": True, "url": "https://example.com/v", "files": []},
    )
    code = run_mod.run_single(
        "https://example.com/v", None, False, False, None, False, False, False, True
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["success"] is True


def test_doctor_cli_on_path_ok(monkeypatch):
    monkeypatch.setattr(doctor_mod.shutil, "which", lambda name: "C:/tools/pinak.exe")
    ok, detail, hint = doctor_mod._check_cli_on_path()
    assert ok is True and detail == "C:/tools/pinak.exe" and hint == ""


def test_doctor_cli_on_path_missing(monkeypatch):
    monkeypatch.setattr(doctor_mod.shutil, "which", lambda name: None)
    ok, detail, hint = doctor_mod._check_cli_on_path()
    assert ok is False and "PATH" in detail and "python -m pinak" in hint


def test_show_config_prints_path(capsys):
    show_config()
    assert "config.json" in capsys.readouterr().out
