"""Update snapshots preserve shared data and refuse running workers."""

import json
import sqlite3
from pathlib import Path

import pytest
from filelock import FileLock

from pinak import history
from pinak import queue as core
from pinak.engine import DownloadRequest
from pinak.mcp_server import setup, updates
from pinak.mcp_server.models import Policy
from pinak.mcp_server.policy import ToolFailure
from pinak.mcp_server.store import Store


def test_snapshot_preserves_jobs_history_and_settings(isolated_history_db, tmp_path, monkeypatch):
    root = tmp_path / "日本語 downloads"
    job_id, _ = core.add_job(
        DownloadRequest.capture("https://example.com/video", output_dir=str(root))
    )
    history.record_download("https://example.com/past")
    Store(Policy(default_output_dir=root))
    policy = tmp_path / "mcp.json"
    policy.write_text(json.dumps({"default_output_dir": str(root)}))
    monkeypatch.setenv("PINAK_MCP_CONFIG", str(policy))
    monkeypatch.setattr(updates, "CONFIG_FILE", str(tmp_path / "no-core-config.json"))
    result = updates.prepare_update()
    assert Path(result["settings_backups"][0]).read_bytes() == policy.read_bytes()
    with sqlite3.connect(result["database_backup"]) as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("SELECT COUNT(*) FROM downloads").fetchone()[0] == 1
        assert (
            conn.execute("SELECT status FROM queue_jobs WHERE id=?", (job_id,)).fetchone()[0]
            == "queued"
        )
    assert core.get_job(job_id).attempts == 0


def test_live_runner_refuses_update_without_backup(isolated_history_db, tmp_path):
    Store(Policy(default_output_dir=tmp_path))
    with (
        FileLock(isolated_history_db + ".queue-run.lock"),
        pytest.raises(ToolFailure, match="Stop queue runners"),
    ):
        updates.prepare_update()
    assert not list(tmp_path.glob("*.update-*.bak"))


def test_generic_connection_is_explicit_and_read_only(tmp_path, monkeypatch, capsys):
    from pinak.mcp_server.__main__ import main

    monkeypatch.setenv("PINAK_MCP_CONFIG", str(tmp_path / "not-created.json"))
    assert main(["configure"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["launch"] == setup.connection_profile()
    assert Path(result["launch"]["command"]).is_absolute()
    assert result["launch"]["transport"] == "stdio"
    assert not list(tmp_path.iterdir())
    assert main(["configure", "--apply"]) == 2


def test_failed_backup_keeps_original(isolated_history_db, tmp_path, monkeypatch):
    Store(Policy(default_output_dir=tmp_path))
    monkeypatch.setattr(
        updates.os, "chmod", lambda *args: (_ for _ in ()).throw(OSError("disk failure"))
    )
    with pytest.raises(OSError):
        updates.prepare_update()
    assert not list(tmp_path.glob("*.update-*.bak"))
    with sqlite3.connect(isolated_history_db) as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
