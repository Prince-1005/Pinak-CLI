"""Smoke tests for display helpers (no user input required)."""

import pinak.commands.info as info_mod
import pinak.commands.panels as panels_mod


def test_panels_render_without_input(capsys, monkeypatch):
    import shutil

    panels_mod.print_separator()
    # Exercise the narrow-terminal fallback branch.
    monkeypatch.setattr(
        shutil,
        "get_terminal_size",
        lambda *a, **k: (_ for _ in ()).throw(OSError("no tty")),
    )
    panels_mod.print_separator()
    panels_mod.print_banner()
    panels_mod.print_welcome_screen()
    panels_mod.print_exit_screen(interrupted=False)
    panels_mod.print_exit_screen(interrupted=True)
    assert isinstance(panels_mod.get_greeting_message(), str)


def test_show_config_and_help(capsys):
    info_mod.show_config()
    info_mod.print_help()
    out = capsys.readouterr().out
    assert out != ""


def test_show_stats_empty_and_filled(capsys, isolated_history_db):
    from pinak import history as history_mod

    info_mod.show_stats()  # empty DB -> friendly message
    assert "No stats" in capsys.readouterr().out
    history_mod.record_download("https://x.com/v", status="success")
    info_mod.show_stats()
    assert "Success Rate" in capsys.readouterr().out


def test_show_platforms_search(capsys):
    info_mod.show_platforms("tube")
    out = capsys.readouterr().out
    assert "Platform" in out


def test_open_output_folder_tmp(tmp_path, monkeypatch):
    import pinak.commands.info as info_m

    monkeypatch.setitem(info_m.config, "output_dir", str(tmp_path / "dl"))
    opened = {}
    import os as _os
    import subprocess as _sub
    import webbrowser as _wb

    monkeypatch.setattr(_os, "startfile", lambda p: opened.setdefault("path", p), raising=False)
    monkeypatch.setattr(_sub, "run", lambda cmd, **k: opened.setdefault("cmd", cmd))
    monkeypatch.setattr(_wb, "open", lambda uri: opened.setdefault("uri", uri))
    info_m.open_output_folder()
    assert (tmp_path / "dl").exists()
    assert opened  # opened via startfile (win), subprocess (linux xdg-open), or browser fallback


def test_open_output_folder_macos_and_linux(tmp_path, monkeypatch):
    import shutil
    import subprocess
    import sys

    import pinak.commands.info as info_m

    monkeypatch.setitem(info_m.config, "output_dir", str(tmp_path / "dl2"))

    # Test macOS
    runs = []
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(shutil, "which", lambda cmd: "/usr/bin/open" if cmd == "open" else None)
    monkeypatch.setattr(subprocess, "run", lambda cmd, **k: runs.append(cmd))
    info_m.open_output_folder()
    assert runs and runs[-1][0] == "open"

    # Test Linux xdg-open
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(
        shutil, "which", lambda cmd: "/usr/bin/xdg-open" if cmd == "xdg-open" else None
    )
    info_m.open_output_folder()
    assert runs and runs[-1][0] == "xdg-open"


def test_show_history_fallback(monkeypatch, capsys, isolated_history_db):
    from pinak import history as history_mod

    history_mod.record_download("https://x.com/v1", status="success")
    # Force the non-interactive fallback by breaking the TUI Application.
    import prompt_toolkit.application

    def _boom(*a, **k):
        raise RuntimeError("no tty")

    monkeypatch.setattr(prompt_toolkit.application, "Application", _boom)
    info_mod.show_history_rendered("")
    assert "v1" in capsys.readouterr().out


def test_show_history_empty(capsys, isolated_history_db):
    info_mod.show_history_rendered("")
    assert "No history" in capsys.readouterr().out
