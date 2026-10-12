"""Shared pytest fixtures: isolate config/history DB into tmp dirs."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture()
def isolated_history_db(tmp_path, monkeypatch):
    """Point history.DB_FILE at a temp SQLite file."""
    import pinak.history as history_mod

    db_file = str(tmp_path / "history_test.db")
    monkeypatch.setattr(history_mod, "DB_FILE", db_file)
    history_mod.init_db()
    return db_file


@pytest.fixture()
def tmp_output_dir(tmp_path):
    out = tmp_path / "downloads"
    out.mkdir(exist_ok=True)
    return str(out)


@pytest.fixture(autouse=True)
def _silence_desktop_toasts(monkeypatch):
    """Ensure automated tests never spawn real desktop toasts or background COM threads."""
    import pinak.notify as notify_mod

    if notify_mod._toast is not None:
        monkeypatch.setattr(notify_mod, "_toast", lambda *a, **k: None)
