"""Queue persistence, recovery, and headless engine contracts."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import pytest
from filelock import FileLock

from pinak import history
from pinak import queue as queue_mod
from pinak.config import config
from pinak.engine import (
    DownloadEvent,
    DownloadRequest,
    DownloadResult,
    active_setting,
    run_download,
)


def _request(tmp_path, url="https://example.com/watch?v=1", **kwargs):
    return DownloadRequest.capture(url, output_dir=str(tmp_path / "media"), **kwargs)


def test_request_freezes_settings_and_headless_result(tmp_path, monkeypatch, capsys):
    import pinak.downloader as downloader

    monkeypatch.setitem(config, "audio_format", "flac")
    monkeypatch.setitem(config, "subtitle_languages", ["en", "fr"])
    request = _request(tmp_path, extract_audio=True)
    monkeypatch.setitem(config, "audio_format", "mp3")
    monkeypatch.setitem(config, "subtitle_languages", ["de"])
    assert request.audio_format == "flac"
    assert request.subtitle_languages == ("en", "fr")
    assert request.output_dir == str((tmp_path / "media").resolve())

    events = []

    def fake_download(url, **_kwargs):
        assert active_setting("audio_format") == "flac"
        assert active_setting("subtitle_languages") == ["en", "fr"]
        from pinak.engine import emit_message, emit_progress

        assert emit_message("[cyan]Starting[/]")
        assert emit_progress({"status": "downloading", "downloaded_bytes": 5, "total_bytes": 10})
        return {"success": True, "url": url, "files": [], "info": {"duration": 4}}

    monkeypatch.setattr(downloader, "handle_download", fake_download)
    result = run_download(request, events.append)
    assert result.status == "succeeded" and result.duration == 4
    assert [event.kind for event in events] == ["message", "progress", "result"]
    assert capsys.readouterr().out == ""
    assert active_setting("audio_format") == "mp3"


def test_saved_request_reads_pre_language_jobs(tmp_path):
    request = _request(tmp_path)
    old_payload = request.to_dict()
    del old_payload["subtitle_languages"]
    assert DownloadRequest.from_dict(old_payload).subtitle_languages == ("en",)


def test_saved_jobs_resolve_interactive_duplicate_choice(tmp_path, monkeypatch):
    monkeypatch.setitem(config, "duplicate_action", "ask")
    assert _request(tmp_path).duplicate_action == "skip"
    with pytest.raises(ValueError, match="Output directory"):
        DownloadRequest.capture("https://example.com/video", output_dir=" ")


@pytest.mark.parametrize("platform", ["YouTube", "Instagram"])
def test_headless_engine_uses_existing_download_paths_without_printing(
    tmp_path, monkeypatch, capsys, platform
):
    import pinak.downloader as downloader

    monkeypatch.setattr(downloader, "ffmpeg_available", lambda: True)
    monkeypatch.setattr(downloader, "get_platform", lambda _url: platform)
    monkeypatch.setattr(downloader, "handle_duplicate", lambda *_a, **_kw: "download")
    monkeypatch.setattr(downloader, "record_download", lambda *_a, **_kw: None)
    monkeypatch.setattr(
        downloader,
        "print_download_summary",
        lambda _result: pytest.fail("Headless downloads must not render a terminal summary"),
    )
    fake_result = {
        "success": True,
        "url": "https://example.com/media",
        "files": [],
        "errors": [],
        "info": {},
    }
    monkeypatch.setattr(downloader, "download_media_content", lambda *_a, **_kw: fake_result)
    monkeypatch.setattr(downloader, "download_instagram_media", lambda *_a, **_kw: fake_result)
    events = []
    result = run_download(_request(tmp_path, "https://example.com/media"), events.append)
    assert result.status == "succeeded"
    assert any(event.kind == "message" for event in events)
    assert capsys.readouterr().out == ""


def test_queue_migrates_existing_history_and_freezes_jobs(isolated_history_db, tmp_path):
    history.record_download("https://example.com/old", status="success")
    request = _request(tmp_path)
    first, created = queue_mod.add_job(request)
    same, added = queue_mod.add_job(request)
    forced, forced_created = queue_mod.add_job(_request(tmp_path, force=True))
    assert (same, added) == (first, False)
    assert forced_created and forced != first
    assert queue_mod.list_jobs("queued")[-1].request == request
    assert len(history.get_history("")) == 1
    with sqlite3.connect(isolated_history_db) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 1


def test_queue_persists_when_history_is_disabled(isolated_history_db, tmp_path, monkeypatch):
    monkeypatch.setitem(config, "history_enabled", False)
    job_id, _ = queue_mod.add_job(_request(tmp_path))
    assert queue_mod.list_jobs()[0].id == job_id


def test_import_validates_atomically_and_reports_line(isolated_history_db, tmp_path):
    batch = tmp_path / "links ünicode.txt"
    batch.write_text("# comment\nhttps://example.com/one\nnot-a-url\n", encoding="utf-8")
    with pytest.raises(ValueError, match=r":3:"):
        queue_mod.import_file(batch)
    assert queue_mod.list_jobs() == []
    batch.write_text("  # comment\nhttps://example.com/one\n/audio https://example.com/two\n")
    imported = queue_mod.import_file(batch)
    assert len(imported) == 2
    assert any(job.request.extract_audio for job in queue_mod.list_jobs())


def test_run_continues_past_failure_then_retries(isolated_history_db, tmp_path, monkeypatch):
    first, _ = queue_mod.add_job(_request(tmp_path, "https://example.com/one"))
    second, _ = queue_mod.add_job(_request(tmp_path, "https://example.com/two"))
    calls = []

    def fake_run(request, on_event=None):
        calls.append(request.url)
        if on_event:
            on_event(DownloadEvent("message", "starting"))
        return DownloadResult(
            "failed" if request.url.endswith("one") and len(calls) == 1 else "succeeded",
            request.url,
            (),
            ("source unavailable",) if len(calls) == 1 else (),
        )

    monkeypatch.setattr(queue_mod, "run_download", fake_run)
    observed = []
    summary = queue_mod.run_queue(on_event=lambda job, event: observed.append((job.id, event.kind)))
    assert (summary.failed, summary.succeeded) == (1, 1)
    assert [j.status for j in queue_mod.list_jobs()] == ["succeeded", "failed"]
    assert observed == [
        (first, "started"),
        (first, "message"),
        (first, "finished"),
        (second, "started"),
        (second, "message"),
        (second, "finished"),
    ]
    assert queue_mod.retry_failed(first) == 1
    assert queue_mod.run_queue().succeeded == 1
    assert queue_mod.retry_failed(first) == 0


def test_selected_batch_run_leaves_other_jobs_queued(isolated_history_db, tmp_path, monkeypatch):
    other, _ = queue_mod.add_job(_request(tmp_path, "https://example.com/other"))
    batch = tmp_path / "batch.txt"
    batch.write_text("https://example.com/one\nhttps://example.com/two\n")
    selected = [job_id for job_id, _ in queue_mod.import_file(batch)]
    monkeypatch.setattr(
        queue_mod,
        "run_download",
        lambda request, on_event=None: DownloadResult("succeeded", request.url, (), ()),
    )
    assert queue_mod.run_queue(selected).succeeded == 2
    assert {job.id: job.status for job in queue_mod.list_jobs()} == {
        other: "queued",
        selected[0]: "succeeded",
        selected[1]: "succeeded",
    }


def test_selected_batch_supports_more_than_sqlite_parameter_limit(
    isolated_history_db, tmp_path, monkeypatch
):
    batch = tmp_path / "large-batch.txt"
    batch.write_text("".join(f"https://example.com/{index}\n" for index in range(1100)))
    selected = [job_id for job_id, _ in queue_mod.import_file(batch)]
    monkeypatch.setattr(
        queue_mod,
        "run_download",
        lambda request, on_event=None: DownloadResult("succeeded", request.url, (), ()),
    )
    assert queue_mod.run_queue(selected, limit=1).succeeded == 1
    assert len(queue_mod.list_jobs("queued")) == 1099


def test_duplicate_history_is_skipped_without_prompt(isolated_history_db, tmp_path, monkeypatch):
    import pinak.downloader as downloader

    url = "https://example.com/already-downloaded"
    media = tmp_path / "existing.mp4"
    media.write_bytes(b"existing")
    history.record_download(url, files=[str(media)])
    monkeypatch.setitem(config, "duplicate_action", "ask")
    monkeypatch.setattr(downloader, "ffmpeg_available", lambda: True)
    monkeypatch.setattr(downloader, "get_platform", lambda _url: "YouTube")
    monkeypatch.setattr(
        downloader,
        "download_media_content",
        lambda *_args, **_kwargs: pytest.fail("Duplicate should be skipped"),
    )
    assert run_download(_request(tmp_path, url)).status == "skipped"


def test_interrupt_and_crash_recovery_keep_work(isolated_history_db, tmp_path, monkeypatch):
    first, _ = queue_mod.add_job(_request(tmp_path, "https://example.com/one"))
    second, _ = queue_mod.add_job(_request(tmp_path, "https://example.com/two"))

    def interrupt(_request, on_event=None):
        raise KeyboardInterrupt

    monkeypatch.setattr(queue_mod, "run_download", interrupt)
    assert queue_mod.run_queue().interrupted
    jobs = {job.id: job for job in queue_mod.list_jobs()}
    assert jobs[first].status == jobs[second].status == "queued"
    assert (jobs[first].attempts, jobs[second].attempts) == (1, 0)

    with sqlite3.connect(isolated_history_db) as conn:
        conn.execute("UPDATE queue_jobs SET status = 'running' WHERE id = ?", (first,))
    monkeypatch.setattr(
        queue_mod,
        "run_download",
        lambda request, on_event=None: DownloadResult("succeeded", request.url, (), ()),
    )
    assert queue_mod.run_queue().succeeded == 2
    assert {job.id: job.attempts for job in queue_mod.list_jobs()} == {first: 2, second: 1}


def test_crashed_retry_cannot_inherit_old_files_as_success(
    isolated_history_db, tmp_path, monkeypatch
):
    job_id, _ = queue_mod.add_job(_request(tmp_path))
    old_file = tmp_path / "old-partial.mp4"
    old_file.write_bytes(b"partial media")
    with sqlite3.connect(isolated_history_db) as conn:
        conn.execute(
            "UPDATE queue_jobs SET status = 'running', attempts = 1, files_json = ? WHERE id = ?",
            (json.dumps([str(old_file)]), job_id),
        )
    calls = []

    def fake_run(request, on_event=None):
        calls.append(request.url)
        return DownloadResult("succeeded", request.url, (str(old_file),), ())

    monkeypatch.setattr(queue_mod, "run_download", fake_run)
    assert queue_mod.run_queue().succeeded == 1
    assert calls == ["https://example.com/watch?v=1"]
    assert queue_mod.list_jobs()[0].attempts == 2


def test_second_runner_is_rejected(isolated_history_db, tmp_path):
    queue_mod.add_job(_request(tmp_path))
    lock = FileLock(history.DB_FILE + ".queue-run.lock", timeout=0)
    with lock, pytest.raises(RuntimeError, match="Another Pinak queue runner"):
        queue_mod.run_queue()


def test_separate_process_lock_releases_after_exit(isolated_history_db, tmp_path, monkeypatch):
    job_id, _ = queue_mod.add_job(_request(tmp_path))
    script = (
        "import sys,time; from filelock import FileLock; "
        "lock=FileLock(sys.argv[1], timeout=0); lock.acquire(); "
        "print('READY', flush=True); time.sleep(30)"
    )
    process = subprocess.Popen(
        [sys.executable, "-c", script, history.DB_FILE + ".queue-run.lock"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stdout is not None
        assert process.stdout.readline().strip() == "READY"
        with pytest.raises(RuntimeError, match="Another Pinak queue runner"):
            queue_mod.run_queue()
    finally:
        process.terminate()
        process.communicate(timeout=5)
    monkeypatch.setattr(
        queue_mod,
        "run_download",
        lambda request, on_event=None: DownloadResult("succeeded", request.url, (), ()),
    )
    assert queue_mod.run_queue().succeeded == 1
    assert queue_mod.list_jobs()[0].id == job_id


def test_skipped_result_has_own_state(isolated_history_db, tmp_path, monkeypatch):
    queue_mod.add_job(_request(tmp_path))
    monkeypatch.setattr(
        queue_mod,
        "run_download",
        lambda request, on_event=None: DownloadResult("skipped", request.url, (), ()),
    )
    assert queue_mod.run_queue().skipped == 1
    assert queue_mod.list_jobs()[0].status == "skipped"


def test_queue_cli_entry_routes_without_starting_repl(isolated_history_db, tmp_path, monkeypatch):
    import importlib

    cli = importlib.import_module("pinak.cli")
    monkeypatch.setattr(cli, "init_config", lambda: None)
    monkeypatch.setattr(cli, "setup_logging", lambda **_kwargs: None)
    monkeypatch.setattr(sys, "argv", ["pinak", "queue", "add", "https://example.com/one"])
    with pytest.raises(SystemExit) as exit_info:
        cli.run_cli()
    assert exit_info.value.code == 0
    assert queue_mod.list_jobs()[0].request.url == "https://example.com/one"


def test_queue_cli_import_list_retry_and_run(isolated_history_db, tmp_path, monkeypatch, capsys):
    from pinak.commands import queue as queue_command

    batch = tmp_path / "batch.txt"
    batch.write_text("https://example.com/one\n")
    assert queue_command.main(["import", str(batch)]) == 0
    assert queue_command.main(["list", "--status", "queued"]) == 0
    assert "example.com/one" in capsys.readouterr().out
    monkeypatch.setattr(
        queue_mod,
        "run_download",
        lambda request, on_event=None: DownloadResult("failed", request.url, (), ("offline",)),
    )
    assert queue_command.main(["run"]) == 1
    job = queue_mod.list_jobs()[0]
    assert job.status == "failed"
    assert queue_command.main(["retry", str(job.id)]) == 0
    assert queue_command.main(["retry", "--failed"]) == 1
    assert queue_mod.list_jobs()[0].status == "queued"


def test_repl_queue_routes_to_same_jobs_and_stays_open(isolated_history_db, tmp_path, monkeypatch):
    import pinak.cli as cli
    from pinak.commands import queue as queue_command

    monkeypatch.setitem(cli.config, "username", "tester")
    monkeypatch.setattr(cli, "PromptSession", None)
    monkeypatch.setattr(cli, "maybe_print_offline_notice", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        queue_mod,
        "run_download",
        lambda request, on_event=None: DownloadResult("failed", request.url, (), ("offline",)),
    )
    commands = iter(
        [
            "/queue help",
            "/queue add https://example.com/one --audio",
            "/queue list --status queued",
            "/queue run",
            "/queue retry --failed",
            "/exit",
        ]
    )
    monkeypatch.setattr("builtins.input", lambda *args: next(commands))
    cli.repl_loop()
    job = queue_mod.list_jobs()[0]
    assert job.request.extract_audio and job.status == "queued" and job.attempts == 1

    batch = tmp_path / "files with spaces.txt"
    batch.write_text("https://example.com/two\n")
    assert queue_command.run_repl(f'import "{batch}"') == 0
    assert len(queue_mod.list_jobs()) == 2


def test_local_http_download_runs_through_queue(isolated_history_db, tmp_path, monkeypatch, capsys):
    import pinak.downloader as downloader
    import pinak.ffmpeg_setup as ffmpeg_setup

    (tmp_path / "sample.mp4").write_bytes(b"local fixture media" * 100)

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(tmp_path), **kwargs)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        monkeypatch.setattr(downloader, "ffmpeg_available", lambda: False)
        monkeypatch.setattr(downloader, "get_ffmpeg_path", lambda: str(tmp_path / "ffmpeg-missing"))
        monkeypatch.setattr(ffmpeg_setup, "ensure_ffmpeg", lambda: "")
        request = _request(tmp_path, f"http://127.0.0.1:{server.server_port}/sample.mp4")
        job_id, _ = queue_mod.add_job(request)
        summary = queue_mod.run_queue()
        job = queue_mod.list_jobs()[0]
        assert summary.succeeded == 1, job.last_error
        assert job.id == job_id and job.status == "succeeded"
        assert job.files and all(path.endswith(".mp4") for path in job.files)
        assert capsys.readouterr().out == ""
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_queue_display_renders_transfer_and_processing(isolated_history_db, tmp_path, monkeypatch):
    from io import StringIO

    from rich.console import Console

    from pinak.commands import queue as command

    output = StringIO()
    terminal = Console(file=output, width=60, color_system=None)
    monkeypatch.setattr(command, "console", terminal)
    queue_mod.add_job(_request(tmp_path))
    job = queue_mod.list_jobs()[0]
    display = command.QueueDisplay(1)
    display.handle(job, DownloadEvent("started"))
    display.handle(job, DownloadEvent("progress", "demo.mp4", 512, 1024))
    terminal.print(display.render())
    display.handle(job, DownloadEvent("processing"))
    terminal.print(display.render())
    display.handle(job, DownloadEvent("finished", "succeeded", files=("demo.mp4",)))
    rendered = output.getvalue()
    for expected in (
        "PINAK DOWNLOAD QUEUE",
        "demo.mp4",
        "50%",
        "512.0 B",
        "ETA",
        "Processing / merging",
        "Succeeded",
        "Saved 1 file",
    ):
        assert expected in rendered


def test_queue_display_reports_worker_exception_and_interrupt(
    isolated_history_db, tmp_path, monkeypatch, capsys
):
    from pinak.commands import queue as command

    job_id, _ = queue_mod.add_job(_request(tmp_path))

    def fail(request, on_event=None):
        raise RuntimeError("source is offline")

    monkeypatch.setattr(queue_mod, "run_download", fail)
    assert command.main(["run"]) == 1
    assert "source is offline" in capsys.readouterr().out
    assert queue_mod.retry_failed(job_id) == 1

    def interrupt(request, on_event=None):
        raise KeyboardInterrupt

    monkeypatch.setattr(queue_mod, "run_download", interrupt)
    assert command.main(["run"]) == 130
    assert "Queue paused" in capsys.readouterr().out
    assert queue_mod.list_jobs()[0].status == "queued"


def test_clear_redraws_header_and_preserves_jobs_and_history(
    isolated_history_db, tmp_path, monkeypatch, capsys
):
    from io import StringIO

    from rich.console import Console

    import pinak.cli as cli
    from pinak.commands import panels

    output = StringIO()
    monkeypatch.setenv("TERM", "xterm-256color")
    monkeypatch.setattr(
        panels, "console", Console(file=output, width=80, force_terminal=True, legacy_windows=False)
    )
    monkeypatch.setitem(config, "username", "tester")
    monkeypatch.setattr(cli, "PromptSession", None)
    monkeypatch.setattr(cli.updater, "start_background_update_check", lambda: None)
    monkeypatch.setattr(cli, "maybe_print_offline_notice", lambda *a, **kw: True)
    history.record_download("https://example.com/history")
    old_history = history.get_history()
    job_id, _ = queue_mod.add_job(_request(tmp_path))
    old_config = dict(config)
    commands = iter(["/clear", "/batch missing.txt", "/queue list", "/exit"])
    monkeypatch.setattr("builtins.input", lambda *a: next(commands))
    cli.repl_loop()
    rendered = output.getvalue()
    assert "\x1b[2J" in rendered
    assert "\x1b[3J" in rendered
    after_clear = rendered.split("\x1b[3J", 1)[1]
    assert "PINAK-CLI" in after_clear and "PINAK CONTROL PANEL" in after_clear
    assert "Unknown command: /batch" in capsys.readouterr().out
    assert queue_mod.list_jobs()[0].id == job_id
    assert queue_mod.list_jobs()[0].status == "queued"
    assert history.get_history() == old_history
    assert config == old_config
