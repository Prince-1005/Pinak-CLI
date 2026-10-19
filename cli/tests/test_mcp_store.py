"""Real SQLite migration, mutation, replay, and core interoperability tests."""

import sqlite3
from pathlib import Path

import pytest

from pinak import history
from pinak import queue as core
from pinak.engine import DownloadRequest
from pinak.mcp_server.models import Policy
from pinak.mcp_server.policy import ToolFailure
from pinak.mcp_server.store import Store
from pinak.mcp_server.tools import Tools


@pytest.fixture
def tools(isolated_history_db, tmp_path):
    service = Tools(Policy(default_output_dir=tmp_path))
    yield service
    service.close()


def add(tools, key="add", **options):
    return tools.call(
        "queue_add", {"url": "https://example.com/video", "options": options, "request_key": key}
    )


def test_force_add_and_remove_replay_are_atomic(tools):
    first = add(tools, force=True)
    assert first["ok"]
    assert add(tools, force=True) == first
    assert len(core.list_jobs()) == 1
    conflict = add(tools, key="add", quality="720p")
    assert conflict["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    ids = [first["data"]["job_id"]]
    arguments = {"job_ids": ids, "request_key": "remove"}
    removed = tools.call("queue_remove", arguments)
    assert removed["ok"] and core.list_jobs() == []
    assert tools.call("queue_remove", arguments) == removed
    assert core.list_jobs() == []


def test_bad_bulk_id_cannot_partly_mutate(tools):
    job_id = add(tools)["data"]["job_id"]
    for name in ("queue_remove", "queue_cancel", "queue_retry"):
        result = tools.call(name, {"job_ids": [job_id, 999], "request_key": name})
        assert not result["ok"]
        assert core.get_job(job_id).status == "queued"


def test_schema_is_additive_and_preserves_old_queue(isolated_history_db, tmp_path):
    job_id, _ = core.add_job(
        DownloadRequest.capture("https://example.com/old", output_dir=str(tmp_path))
    )
    history.record_download("https://example.com/history")
    Store(Policy(default_output_dir=tmp_path))
    assert core.get_job(job_id).request.url == "https://example.com/old"
    assert len(history.get_history()) == 1
    assert Path(isolated_history_db + ".pre-mcp-1.bak").is_file()
    with sqlite3.connect(isolated_history_db) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
        conn.execute("UPDATE pinak_extensions SET version=99 WHERE name='mcp'")
    with pytest.raises(ToolFailure, match="different Pinak"):
        Store(Policy(default_output_dir=tmp_path))
    assert core.get_job(job_id).status == "queued"


def test_pagination_and_history_preserve_files(tools, tmp_path):
    ids = [add(tools, key=f"add-{i}", force=True)["data"]["job_id"] for i in range(3)]
    first = tools.call("queue_list", {"limit": 2})["data"]
    assert [item["id"] for item in first["items"]] == ids[:0:-1]
    second = tools.call("queue_list", {"limit": 2, "cursor": first["next_cursor"]})["data"]
    assert [item["id"] for item in second["items"]] == ids[:1]
    path = tmp_path / "keep.mp4"
    path.write_bytes(b"keep")
    history.record_download("https://example.com/history?token=secret", files=[str(path)])
    result = tools.call("history_list", {})
    assert result["ok"] and "secret" not in str(result)
    assert result["data"]["items"][0]["files"] == [str(path)]
    tools.call("queue_remove", {"job_ids": ids, "request_key": "remove"})
    assert path.read_bytes() == b"keep" and len(history.get_history()) == 1


def test_oversized_mutation_rolls_back(isolated_history_db, tmp_path):
    tools = Tools(Policy(default_output_dir=tmp_path, max_response_bytes=4096))
    try:
        result = tools.call(
            "queue_add", {"url": "https://example.com/" + "a" * 5000, "request_key": "big"}
        )
        assert result["error"]["code"] == "RESPONSE_TOO_LARGE"
        assert core.list_jobs() == []
    finally:
        tools.close()
