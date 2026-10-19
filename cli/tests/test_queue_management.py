"""Queue management preserves media and coordinates with the active worker."""

from __future__ import annotations

import sqlite3
import threading
from io import StringIO

import pytest
from rich.console import Console

from pinak import history
from pinak import queue as queue_mod
from pinak.commands import queue as command
from pinak.config import config
from pinak.engine import DownloadRequest, DownloadResult


def request(tmp_path, suffix="one"):
    return DownloadRequest.capture(
        f"https://example.com/{suffix}", output_dir=str(tmp_path / "media"), quality="720p"
    )


def test_show_roundtrips_saved_options_files_and_error(isolated_history_db, tmp_path, monkeypatch):
    job_id, _ = queue_mod.add_job(request(tmp_path))
    media = tmp_path / "clip ünicode.mp4"
    media.write_bytes(b"keep this media")
    error = "Failed final processing [not markup]"
    monkeypatch.setattr(
        queue_mod,
        "run_download",
        lambda req, on_event=None: DownloadResult("failed", req.url, (str(media),), (error,)),
    )
    queue_mod.run_queue()
    monkeypatch.setitem(config, "quality", "worst")
    job = queue_mod.get_job(job_id)
    assert job.request.quality == "720p"
    assert job.files == (str(media),) and job.last_error == error and job.attempts == 1
    output = StringIO()
    monkeypatch.setattr(command, "console", Console(file=output, width=240, color_system=None))
    assert command.main(["show", str(job_id)]) == 0
    shown = output.getvalue()
    for value in ("Saved options", "720p", str(media), error, "failed", "Attempts"):
        assert value in shown
    for key in job.request.to_dict():
        assert key in shown


def test_cancel_persists_skips_worker_and_allows_explicit_readd(
    isolated_history_db, tmp_path, monkeypatch
):
    saved = request(tmp_path)
    job_id, _ = queue_mod.add_job(saved)
    assert queue_mod.cancel_job(job_id)
    assert not queue_mod.cancel_job(job_id)
    assert queue_mod.get_job(job_id).status == "cancelled"
    assert queue_mod.list_jobs("cancelled")[0].id == job_id
    monkeypatch.setattr(
        queue_mod, "run_download", lambda *a, **kw: pytest.fail("Cancelled job ran")
    )
    assert queue_mod.run_queue().succeeded == 0
    assert queue_mod.retry_failed(job_id) == 0
    assert queue_mod.get_job(job_id).attempts == 0
    new_id, created = queue_mod.add_job(saved)
    assert created and new_id != job_id


@pytest.mark.parametrize("action", [queue_mod.get_job, queue_mod.remove_job, queue_mod.cancel_job])
@pytest.mark.parametrize("job_id", [-1, 0, 999])
def test_invalid_or_unknown_id_has_no_effect(isolated_history_db, tmp_path, action, job_id):
    saved_id, _ = queue_mod.add_job(request(tmp_path))
    with pytest.raises(ValueError, match="positive|not found"):
        action(job_id)
    assert queue_mod.get_job(saved_id).status == "queued"


def test_clean_keeps_media_history_and_unfinished_records(
    isolated_history_db, tmp_path, monkeypatch
):
    media = tmp_path / "keep.mp4"
    media.write_bytes(b"original bytes")
    history.record_download("https://example.com/history", files=[str(media)])
    old_history = history.get_history()
    ids = {
        name: queue_mod.add_job(request(tmp_path, name))[0]
        for name in ("succeeded", "skipped", "failed", "cancelled", "queued")
    }
    queue_mod.cancel_job(ids["cancelled"])
    monkeypatch.setattr(
        queue_mod,
        "run_download",
        lambda req, on_event=None: DownloadResult(
            req.url.rsplit("/", 1)[1], req.url, (str(media),), ("failed processing",)
        ),
    )
    queue_mod.run_queue([ids[name] for name in ("succeeded", "skipped", "failed")])
    assert queue_mod.clean_completed() == 2
    assert queue_mod.clean_completed() == 0
    assert {j.status for j in queue_mod.list_jobs()} == {"failed", "cancelled", "queued"}
    assert media.read_bytes() == b"original bytes"
    recorded = history.get_history()
    assert recorded[:1] == old_history
    assert [(row["url"].rsplit("/", 1)[1], row["status"]) for row in recorded[1:]] == [
        ("succeeded", "success"),
        ("skipped", "skipped"),
        ("failed", "failed"),
    ]
    queue_mod.remove_job(ids["failed"])
    queue_mod.remove_job(ids["queued"])
    queue_mod.remove_job(ids["cancelled"])
    assert queue_mod.list_jobs() == []
    assert media.read_bytes() == b"original bytes"
    assert history.get_history() == recorded


def test_bulk_remove_is_atomic_and_keeps_files_and_history(isolated_history_db, tmp_path):
    ids = [queue_mod.add_job(request(tmp_path, str(index)))[0] for index in range(3)]
    media = tmp_path / "saved.mp4"
    media.write_bytes(b"saved media")
    history.record_download("https://example.com/kept", files=[str(media)])
    before = history.get_history()
    with pytest.raises(ValueError, match="not found"):
        queue_mod.remove_jobs([ids[0], 999, ids[1]])
    assert {job.id for job in queue_mod.list_jobs()} == set(ids)
    assert queue_mod.remove_jobs([ids[0], ids[1], ids[0]]) == 2
    assert [job.id for job in queue_mod.list_jobs()] == [ids[2]]
    assert media.read_bytes() == b"saved media"
    assert history.get_history() == before


def test_bulk_remove_cli_and_repl(isolated_history_db, tmp_path, capsys):
    ids = [queue_mod.add_job(request(tmp_path, str(index)))[0] for index in range(4)]
    assert command.main(["remove", str(ids[0]), str(ids[1])]) == 0
    assert command.run_repl(f"remove {ids[2]} {ids[3]}") == 0
    assert queue_mod.list_jobs() == []
    assert "Removed 2 job record(s)" in capsys.readouterr().out


def test_bulk_remove_refuses_running_job_without_partial_delete(isolated_history_db, tmp_path):
    ids = [queue_mod.add_job(request(tmp_path, str(index)))[0] for index in range(3)]
    with sqlite3.connect(isolated_history_db) as conn:
        conn.execute("UPDATE queue_jobs SET status = 'running' WHERE id = ?", (ids[1],))
    with pytest.raises(ValueError, match="running"):
        queue_mod.remove_jobs(ids)
    assert {job.id for job in queue_mod.list_jobs()} == set(ids)


def test_queue_records_failed_skipped_and_retry_attempts(
    isolated_history_db, tmp_path, monkeypatch
):
    ids = [queue_mod.add_job(request(tmp_path, str(index)))[0] for index in range(2)]
    attempts = 0

    def download(req, on_event=None):
        nonlocal attempts
        attempts += 1
        status = "failed" if attempts == 1 else "skipped" if attempts == 2 else "succeeded"
        return DownloadResult(status, req.url, (), ("network error",) if status == "failed" else ())

    monkeypatch.setattr(queue_mod, "run_download", download)
    queue_mod.run_queue()
    assert [(row["url"], row["status"]) for row in history.get_history()] == [
        (request(tmp_path, "0").url, "failed"),
        (request(tmp_path, "1").url, "skipped"),
    ]
    assert queue_mod.retry_failed(ids[0]) == 1
    queue_mod.run_queue()
    assert [row["status"] for row in history.get_history()] == ["failed", "skipped", "success"]


def test_queue_obeys_disabled_history_setting(isolated_history_db, tmp_path, monkeypatch):
    queue_mod.add_job(request(tmp_path))
    monkeypatch.setitem(config, "history_enabled", False)
    monkeypatch.setattr(
        queue_mod,
        "run_download",
        lambda req, on_event=None: DownloadResult("succeeded", req.url, (), ()),
    )
    assert queue_mod.run_queue().succeeded == 1
    assert history.get_history() == []


def test_management_coordinates_with_running_worker(isolated_history_db, tmp_path, monkeypatch):
    active, _ = queue_mod.add_job(request(tmp_path, "active"))
    waiting, _ = queue_mod.add_job(request(tmp_path, "waiting"))
    unwanted, _ = queue_mod.add_job(request(tmp_path, "unwanted"))
    entered = threading.Event()
    release = threading.Event()
    results = []
    failures = []

    def download(req, on_event=None):
        entered.set()
        assert release.wait(10)
        return DownloadResult("succeeded", req.url, (), ())

    def worker():
        try:
            results.append(queue_mod.run_queue())
        except BaseException as exc:
            failures.append(exc)

    monkeypatch.setattr(queue_mod, "run_download", download)
    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    try:
        assert entered.wait(10)
        assert queue_mod.get_job(active).status == "running"
        for action in (queue_mod.cancel_job, queue_mod.remove_job):
            with pytest.raises(ValueError, match="running"):
                action(active)
        assert queue_mod.clean_completed() == 0
        assert queue_mod.cancel_job(waiting)
        queue_mod.remove_job(unwanted)
    finally:
        release.set()
        thread.join(timeout=10)
    assert not thread.is_alive() and failures == []
    assert results[0].succeeded == 1
    assert queue_mod.get_job(waiting).status == "cancelled"
    assert queue_mod.get_job(waiting).attempts == 0
    with pytest.raises(ValueError, match="not found"):
        queue_mod.get_job(unwanted)
    with pytest.raises(ValueError, match="succeeded"):
        queue_mod.cancel_job(active)
    queue_mod.remove_job(active)
    assert queue_mod.get_job(waiting).status == "cancelled"


def test_cli_and_slash_management_share_records(isolated_history_db, tmp_path, monkeypatch, capsys):
    import pinak.cli as cli

    job_id, _ = queue_mod.add_job(request(tmp_path))
    assert command.main(["show", str(job_id)]) == 0
    assert command.main(["clean"]) == 2
    assert queue_mod.get_job(job_id).status == "queued"
    monkeypatch.setitem(config, "username", "tester")
    monkeypatch.setattr(cli, "PromptSession", None)
    monkeypatch.setattr(cli, "maybe_print_offline_notice", lambda *a, **kw: True)
    inputs = iter(
        [
            f"/queue cancel {job_id}",
            f"/queue show {job_id}",
            "/queue list --status cancelled",
            f"/queue remove {job_id}",
            "/queue clean --completed",
            "/exit",
        ]
    )
    monkeypatch.setattr("builtins.input", lambda *a: next(inputs))
    cli.repl_loop()
    assert queue_mod.list_jobs() == []
    output = capsys.readouterr().out
    assert "cancelled" in output and "Downloaded files were kept" in output
    assert command.main(["show", str(job_id)]) == 2
    assert "not found" in capsys.readouterr().out


@pytest.mark.parametrize("state", ["failed", "skipped"])
def test_cancel_refuses_other_terminal_states(isolated_history_db, tmp_path, monkeypatch, state):
    job_id, _ = queue_mod.add_job(request(tmp_path))
    monkeypatch.setattr(
        queue_mod,
        "run_download",
        lambda req, on_event=None: DownloadResult(state, req.url, (), ()),
    )
    queue_mod.run_queue()
    with pytest.raises(ValueError, match=state):
        queue_mod.cancel_job(job_id)
    assert queue_mod.get_job(job_id).status == state


def test_cli_reports_database_lock_without_traceback(monkeypatch, capsys):
    def locked(job_id):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(command, "get_job", locked)
    assert command.main(["show", "1"]) == 2
    assert "Queue error: database is locked" in capsys.readouterr().out
