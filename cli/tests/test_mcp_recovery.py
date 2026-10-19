"""Fault injection around storage, replay retention and owned worker startup."""

import sqlite3
import subprocess
import time
from pathlib import Path

import pytest

from pinak import queue as core
from pinak.mcp_server.models import Policy
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
