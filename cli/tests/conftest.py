"""Shared pytest fixtures: isolate config/history DB into tmp dirs."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Prevent Windows OS ValueError (max 32767 chars per env var) when mock.patch.dict restores os.environ
for _k, _v in list(os.environ.items()):
    if len(_v) > 30000:
        os.environ.pop(_k, None)


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
        monkeypatch.setattr(notify_mod, "_toast", None)


@pytest.fixture(autouse=True)
def _prevent_background_update_requests(monkeypatch):
    """REPL tests must not leave real network workers racing with patched config paths."""
    import pinak.updater as updater_mod

    monkeypatch.setattr(updater_mod, "start_background_update_check", lambda: None)


@pytest.fixture(autouse=True)
def _finish_audio_workers(monkeypatch):
    """Always stop output workers before pytest closes temporary files/capture."""
    from pinak.media.decoders.audio_backend import AudioPlayerBackend

    original = AudioPlayerBackend.__init__
    instances = []

    def initialize(instance, *args, **kwargs):
        original(instance, *args, **kwargs)
        instances.append(instance)

    monkeypatch.setattr(AudioPlayerBackend, "__init__", initialize)
    yield
    for instance in instances:
        instance.stop()
