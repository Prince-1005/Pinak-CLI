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


def test_open_output_folder_failure_notice(tmp_path, monkeypatch, capsys):
    """Verifies that open_output_folder warns user on failure instead of false positive success (SILENT-02)."""
    import os as _os
    import shutil
    import webbrowser as _wb

    import pinak.commands.info as info_m

    monkeypatch.setitem(info_m.config, "output_dir", str(tmp_path / "dl_fail"))
    if hasattr(_os, "startfile"):
        monkeypatch.delattr(_os, "startfile")
    monkeypatch.setattr(shutil, "which", lambda cmd: None)
    monkeypatch.setattr(_wb, "open", lambda uri: False)

    info_m.open_output_folder()
    out = capsys.readouterr().out
    assert "[!] Could not automatically open folder" in out
    assert "[+] Opened:" not in out


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


def test_clear_legacy_windows_erases_full_buffer_before_header(monkeypatch):
    from io import StringIO
    from types import SimpleNamespace

    calls = []
    terminal = SimpleNamespace(
        is_terminal=True,
        is_dumb_terminal=False,
        legacy_windows=True,
        file=StringIO(),
        clear=lambda **kwargs: calls.append("viewport"),
    )
    monkeypatch.setattr(panels_mod, "console", terminal)
    monkeypatch.setenv("COMSPEC", r"C:\Windows\System32\cmd.exe")
    monkeypatch.setattr(panels_mod, "run_cmd", lambda args, **kwargs: calls.append(args))
    monkeypatch.setattr(panels_mod, "print_banner", lambda: calls.append("logo"))
    monkeypatch.setattr(panels_mod, "print_welcome_screen", lambda: calls.append("panel"))
    panels_mod.clear_screen()
    assert calls == [
        "viewport",
        [r"C:\Windows\System32\cmd.exe", "/d", "/c", "cls"],
        "logo",
        "panel",
    ]
    assert terminal.file.getvalue() == ""


def test_clear_redirected_output_has_no_terminal_controls(monkeypatch):
    from io import StringIO

    from rich.console import Console

    output = StringIO()
    monkeypatch.setattr(
        panels_mod, "console", Console(file=output, force_terminal=False, color_system=None)
    )
    panels_mod.clear_screen()
    rendered = output.getvalue()
    assert "\x1b" not in rendered
    assert "PINAK-CLI" in rendered and "PINAK CONTROL PANEL" in rendered


def test_banner_has_distinct_letter_colors(monkeypatch):
    from io import StringIO

    from rich.console import Console

    output = StringIO()
    monkeypatch.setattr(
        panels_mod,
        "console",
        Console(
            file=output, force_terminal=True, color_system="standard", no_color=False, width=100
        ),
    )
    panels_mod.print_banner()
    rendered = output.getvalue()
    assert "PINAK-CLI" in rendered
    for color in ("31m", "33m", "32m", "36m", "35m"):
        assert color in rendered
