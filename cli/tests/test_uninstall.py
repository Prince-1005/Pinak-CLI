"""Tests for pinak.uninstall: detection, user data purging, process execution, and prompts."""

from __future__ import annotations

import types
from unittest.mock import MagicMock

import pinak.uninstall as uninst_mod


def test_detect_uninstall_cmd_uv(monkeypatch):
    monkeypatch.setattr(uninst_mod, "trusted_which", lambda cmd: "/bin/uv" if cmd == "uv" else None)

    def mock_run(cmd, *a, **k):
        if cmd == ["/bin/uv", "tool", "list"]:
            return types.SimpleNamespace(returncode=0, stdout="pinak-cli v1.1.1\n")
        return types.SimpleNamespace(returncode=1, stdout="")

    monkeypatch.setattr(uninst_mod.subprocess, "run", mock_run)
    assert uninst_mod.detect_uninstall_cmd() == ["/bin/uv", "tool", "uninstall", "pinak-cli"]


def test_detect_uninstall_cmd_pipx(monkeypatch):
    monkeypatch.setattr(
        uninst_mod, "trusted_which", lambda cmd: "/bin/pipx" if cmd == "pipx" else None
    )

    def mock_run(cmd, *a, **k):
        if cmd == ["/bin/pipx", "list", "--short"]:
            return types.SimpleNamespace(returncode=0, stdout="pinak-cli 1.1.1\n")
        return types.SimpleNamespace(returncode=1, stdout="")

    monkeypatch.setattr(uninst_mod.subprocess, "run", mock_run)
    assert uninst_mod.detect_uninstall_cmd() == ["/bin/pipx", "uninstall", "pinak-cli"]


def test_detect_uninstall_cmd_fallback_pip(monkeypatch):
    monkeypatch.setattr(uninst_mod, "trusted_which", lambda cmd: None)
    cmd = uninst_mod.detect_uninstall_cmd()
    assert cmd[-3:] == ["pip", "uninstall", "-y"] or cmd[-1] == "pinak-cli"


def test_purge_user_data(tmp_path, monkeypatch):
    cfg_dir = tmp_path / "cfg"
    cfg_dir.mkdir()
    (cfg_dir / "config.json").write_text("{}", encoding="utf-8")

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "history.db").write_bytes(b"dummy")

    legacy_db = tmp_path / "legacy_history.db"
    legacy_db.write_bytes(b"old")

    monkeypatch.setattr(uninst_mod, "config_dir", str(cfg_dir))
    monkeypatch.setattr(uninst_mod, "data_dir", str(data_dir))
    monkeypatch.setattr(uninst_mod, "legacy_db_file", str(legacy_db))
    monkeypatch.setattr(uninst_mod, "command_history_file", str(tmp_path / "commands.txt"))

    removed = uninst_mod.purge_user_data(include_cache=False)
    assert str(cfg_dir) in removed
    assert str(data_dir) in removed
    assert str(legacy_db) in removed
    assert not cfg_dir.exists()
    assert not data_dir.exists()
    assert not legacy_db.exists()


def test_custom_data_directory_keeps_unrelated_files(tmp_path, monkeypatch):
    custom = tmp_path / "shared"
    custom.mkdir()
    (custom / "history.db").write_bytes(b"pinak")
    unrelated = custom / "notes.txt"
    unrelated.write_text("keep", encoding="utf-8")
    monkeypatch.setattr(uninst_mod, "data_dir", str(custom))
    monkeypatch.setattr(uninst_mod, "config_dir", str(tmp_path / "missing-config"))
    monkeypatch.setattr(uninst_mod, "legacy_db_file", str(tmp_path / "missing-legacy"))
    monkeypatch.setattr(uninst_mod, "command_history_file", str(tmp_path / "missing-history"))
    removed = uninst_mod.purge_user_data(include_cache=False)
    assert str(custom / "history.db") in removed
    assert not (custom / "history.db").exists()
    assert unrelated.read_text(encoding="utf-8") == "keep"
    assert custom.is_dir()


def test_execute_uninstallation_posix(monkeypatch):
    monkeypatch.setattr(uninst_mod.sys, "platform", "linux")

    def mock_run(cmd, *a, **k):
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(uninst_mod.subprocess, "run", mock_run)
    assert uninst_mod.execute_uninstallation(["pip", "uninstall", "pinak-cli"]) is True


def test_execute_uninstallation_windows(monkeypatch):
    monkeypatch.setattr(uninst_mod.sys, "platform", "win32")
    monkeypatch.setattr(uninst_mod, "_powershell_path", lambda: "C:/Windows/powershell.exe")
    monkeypatch.setattr(uninst_mod.subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
    monkeypatch.setattr(uninst_mod.subprocess, "DETACHED_PROCESS", 0x00000008, raising=False)
    popen_called = []

    def mock_popen(cmd, *a, **k):
        popen_called.append(cmd)
        return MagicMock()

    monkeypatch.setattr(uninst_mod.subprocess, "Popen", mock_popen)
    # Test path with spaces
    cmd_with_spaces = [
        r"C:\Program Files\Python311\python.exe",
        "-m",
        "pip",
        "uninstall",
        "-y",
        "pinak-cli",
    ]
    assert uninst_mod.execute_uninstallation(cmd_with_spaces) is True
    assert len(popen_called) == 1
    assert popen_called[0][0] == "C:/Windows/powershell.exe"
    script = popen_called[0][3]
    assert "& 'C:\\Program Files\\Python311\\python.exe'" in script


def test_execute_uninstallation_failure(monkeypatch):
    monkeypatch.setattr(uninst_mod.sys, "platform", "linux")

    def mock_run(cmd, *a, **k):
        raise OSError("failed to execute")

    monkeypatch.setattr(uninst_mod.subprocess, "run", mock_run)
    assert uninst_mod.execute_uninstallation(["pip", "uninstall", "pinak-cli"]) is False


def test_run_uninstall_cancelled(monkeypatch):
    monkeypatch.setattr(uninst_mod.Confirm, "ask", lambda *a, **k: False)
    exit_code = uninst_mod.run_uninstall(yes=False)
    assert exit_code == 0


def test_run_uninstall_confirmed(monkeypatch):
    monkeypatch.setattr(uninst_mod.Confirm, "ask", lambda *a, **k: True)
    monkeypatch.setattr(uninst_mod, "purge_user_data", lambda **k: ["/path/dummy"])
    monkeypatch.setattr(
        uninst_mod, "detect_uninstall_cmd", lambda: ["pip", "uninstall", "-y", "pinak-cli"]
    )
    monkeypatch.setattr(uninst_mod, "execute_uninstallation", lambda cmd, **k: True)

    exit_code = uninst_mod.run_uninstall(yes=False)
    assert exit_code == 0


def test_run_uninstall_yes_flag(monkeypatch):
    monkeypatch.setattr(uninst_mod, "purge_user_data", lambda **k: [])
    monkeypatch.setattr(
        uninst_mod, "detect_uninstall_cmd", lambda: ["pip", "uninstall", "-y", "pinak-cli"]
    )
    monkeypatch.setattr(uninst_mod, "execute_uninstallation", lambda cmd, **k: True)

    exit_code = uninst_mod.run_uninstall(yes=True)
    assert exit_code == 0


def test_run_uninstall_exec_failure(monkeypatch):
    monkeypatch.setattr(uninst_mod, "purge_user_data", lambda **k: [])
    monkeypatch.setattr(
        uninst_mod, "detect_uninstall_cmd", lambda: ["pip", "uninstall", "-y", "pinak-cli"]
    )
    monkeypatch.setattr(uninst_mod, "execute_uninstallation", lambda cmd, **k: False)

    exit_code = uninst_mod.run_uninstall(yes=True)
    assert exit_code == 1
