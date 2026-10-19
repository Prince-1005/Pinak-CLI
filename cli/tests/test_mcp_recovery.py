"""Fault injection around storage, replay retention and owned worker startup."""

import contextlib
import logging
import logging.handlers
import sqlite3
import subprocess
import time
from pathlib import Path

import pytest

from pinak import queue as core
from pinak.mcp_server.models import Policy
from pinak.mcp_server.setup import RedactFilter
from pinak.mcp_server.tools import Tools


def test_corruption_is_preserved_and_disclosed(isolated_history_db, tmp_path):
    Path(isolated_history_db).write_bytes(b"confirmed not a sqlite database")
    tools = Tools(Policy(default_output_dir=tmp_path))
    try:
        result = tools.call("server_info", {})
        assert result["ok"] and "corruption" in result["warnings"][0]
        backups = list(tmp_path.glob("history_test.db.corrupt.*"))
        assert len(backups) == 1 and backups[0].read_bytes().startswith(b"confirmed")
        assert tools.call("queue_list", {})["data"]["items"] == []
    finally:
        tools.close()


def test_logs_remain_bounded_redacted_and_survive_broken_stderr(tmp_path, monkeypatch):
    import sys

    logger = logging.Logger("pinak-mcp-stress", level=logging.WARNING)
    destination = tmp_path / "pinak-mcp.log"
    file_handler = logging.handlers.RotatingFileHandler(
        destination, maxBytes=524288, backupCount=2, encoding="utf-8"
    )
    file_handler.addFilter(RedactFilter())
    logger.addHandler(file_handler)

    class BrokenStream:
        def write(self, _value):
            raise BrokenPipeError("closed host stderr")

        def flush(self):
            pass

    broken = BrokenStream()
    stderr_handler = logging.StreamHandler(broken)
    stderr_handler.addFilter(RedactFilter())
    try:
        for _ in range(2500):
            logger.warning("https://user:private@example.com/media?token=private %s", "x" * 1000)
        logger.addHandler(stderr_handler)
        with monkeypatch.context() as context:
            context.setattr(sys, "stderr", broken)
            logger.warning("operation still completes with a closed host pipe")
    finally:
        file_handler.close()
        stderr_handler.close()
    files = list(tmp_path.glob("pinak-mcp.log*"))
    assert len(files) == 3
    assert sum(path.stat().st_size for path in files) <= 3 * 524288
    assert all("private" not in path.read_text(encoding="utf-8") for path in files)
    assert "operation still completes" in destination.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "message,busy",
    [
        ("database is locked", True),
        ("database or disk is full", False),
        ("attempt to write a readonly database", False),
    ],
)
def test_storage_failures_are_not_all_retryable(
    isolated_history_db, tmp_path, monkeypatch, message, busy
):
    tools = Tools(Policy(default_output_dir=tmp_path))
    try:
        monkeypatch.setattr(
            tools, "server_info", lambda _: (_ for _ in ()).throw(sqlite3.OperationalError(message))
        )
        error = tools.call("server_info", {})["error"]
        assert error["retryable"] is busy
        assert error["code"] == ("DATABASE_BUSY" if busy else "DATABASE_ERROR")
    finally:
        tools.close()


def test_receipt_expiry_is_explicit_not_exactly_once(isolated_history_db, tmp_path):
    tools = Tools(Policy(default_output_dir=tmp_path))
    try:
        arguments = {
            "url": "https://example.com/video",
            "options": {"force": True},
            "request_key": "key",
        }
        first = tools.call("queue_add", arguments)
        assert tools.call("queue_add", arguments) == first
        with tools.store.connect() as conn, conn:
            conn.execute("UPDATE mcp_receipts SET created_at=?", (time.time() - 86400 * 8,))
        assert tools.call("queue_add", arguments)["data"]["job_id"] != first["data"]["job_id"]
        assert len(core.list_jobs()) == 2
    finally:
        tools.close()


@pytest.mark.parametrize("fault", ["full", "readonly"])
def test_real_sqlite_storage_refusal_rolls_back_without_quarantine(
    isolated_history_db, tmp_path, monkeypatch, fault
):
    tools = Tools(Policy(default_output_dir=tmp_path))
    baseline = tools.call(
        "queue_add", {"url": "https://example.com/keep", "request_key": "baseline"}
    )
    assert baseline["ok"]
    connect = tools.store.connect

    @contextlib.contextmanager
    def constrained():
        if fault == "readonly":
            with contextlib.closing(
                sqlite3.connect(Path(isolated_history_db).as_uri() + "?mode=ro", uri=True)
            ) as connection:
                connection.row_factory = sqlite3.Row
                yield connection
        else:
            with connect() as connection:
                pages = connection.execute("PRAGMA page_count").fetchone()[0]
                connection.execute(f"PRAGMA max_page_count={int(pages)}")
                yield connection

    try:
        monkeypatch.setattr(tools.store, "connect", constrained)
        result = tools.call(
            "queue_add", {"url": "https://example.com/" + "x" * 7800, "request_key": "cannot-write"}
        )
        assert result["error"]["code"] == "DATABASE_ERROR"
        assert not result["error"]["retryable"]
        assert [job.id for job in core.list_jobs()] == [baseline["data"]["job_id"]]
        with sqlite3.connect(isolated_history_db) as connection:
            assert connection.execute("SELECT COUNT(*) FROM mcp_receipts").fetchone()[0] == 1
            assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert not list(tmp_path.glob("*.corrupt.*"))
    finally:
        tools.close()


def test_failed_launch_record_write_reaps_spawned_child(isolated_history_db, tmp_path, monkeypatch):
    pytest.importorskip("mcp")
    from pinak.mcp_server import worker_controller

    tools = Tools(Policy(default_output_dir=tmp_path))
    processes = []
    launch = subprocess.Popen
    update = tools.store.update_run

    def spawn(*args, **kwargs):
        process = launch(*args, **kwargs)
        processes.append(process)
        return process

    def fail_pid_write(run_id, **kwargs):
        if "pid" in kwargs:
            raise sqlite3.OperationalError("injected disk full after spawn")
        return update(run_id, **kwargs)

    try:
        tools.call("queue_add", {"url": "https://example.com/video", "request_key": "add"})
        monkeypatch.setattr(worker_controller.subprocess, "Popen", spawn)
        monkeypatch.setattr(tools.store, "update_run", fail_pid_write)
        result = tools.call("queue_start", {"request_key": "run"})
        assert result["error"]["code"] == "WORKER_START_FAILED"
        assert len(processes) == 1 and processes[0].poll() is not None
        assert not tools.controller._children
        assert core.list_jobs()[0].attempts == 0
    finally:
        tools.close()
