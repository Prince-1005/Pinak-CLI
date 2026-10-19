"""Crash-safe backups, migration rollback, and a real isolated restore drill."""

import sqlite3
from pathlib import Path

import pytest

from pinak import history
from pinak import queue as core
from pinak.engine import DownloadRequest
from pinak.mcp_server import backup, setup, updates
from pinak.mcp_server.models import Policy
from pinak.mcp_server.store import Store


def test_interrupted_snapshot_never_publishes_partial_backup(isolated_history_db, tmp_path):
    class FailedBackup(sqlite3.Connection):
        def backup(self, target, **kwargs):
            target.execute("CREATE TABLE partial(data)")
            target.commit()
            raise OSError("injected storage failure mid-snapshot")

    destination = tmp_path / "snapshot.bak"
    with FailedBackup(isolated_history_db) as source, pytest.raises(OSError, match="mid-snapshot"):
        backup.backup_database(source, destination)
    assert not destination.exists()
    assert not list(tmp_path.glob(".snapshot*.tmp"))
    with sqlite3.connect(isolated_history_db) as source:
        assert source.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_failed_migration_rolls_back_additive_tables(isolated_history_db, tmp_path, monkeypatch):
    job_id, _ = core.add_job(
        DownloadRequest.capture("https://example.com/video", output_dir=str(tmp_path))
    )

    class FailedMigration(sqlite3.Connection):
        def execute(self, statement, *args):
            if "CREATE TABLE IF NOT EXISTS mcp_runs" in statement:
                raise sqlite3.OperationalError("injected migration write failure")
            return super().execute(statement, *args)

    def connect():
        connection = FailedMigration(isolated_history_db)
        connection.row_factory = sqlite3.Row
        return connection

    monkeypatch.setattr(core, "_connect", connect)
    with pytest.raises(sqlite3.OperationalError, match="migration write failure"):
        Store(Policy(default_output_dir=tmp_path))
    with sqlite3.connect(isolated_history_db) as source:
        tables = {
            row[0] for row in source.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert "pinak_extensions" not in tables and "mcp_receipts" not in tables
        assert (
            source.execute("SELECT status FROM queue_jobs WHERE id=?", (job_id,)).fetchone()[0]
            == "queued"
        )
    backup.verify_backup(Path(isolated_history_db + ".pre-mcp-1.bak"))


def test_existing_incomplete_backup_blocks_migration(isolated_history_db, tmp_path):
    core.list_jobs()
    snapshot = Path(isolated_history_db + ".pre-mcp-1.bak")
    snapshot.write_bytes(b"interrupted old backup")
    with pytest.raises(sqlite3.DatabaseError, match="incomplete"):
        Store(Policy(default_output_dir=tmp_path))
    assert snapshot.read_bytes() == b"interrupted old backup"
    diagnosis = setup.diagnose(Policy(default_output_dir=tmp_path))
    assert not diagnosis["ready"]
    assert any("backup" in error for error in diagnosis["errors"])
    with sqlite3.connect(isolated_history_db) as source:
        assert (
            source.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE name='mcp_receipts'"
            ).fetchone()[0]
            == 0
        )


def test_restore_drill_preserves_snapshot_and_explains_later_data_loss(
    isolated_history_db, tmp_path, monkeypatch
):
    root = tmp_path / "日本語 output"
    saved, _ = core.add_job(
        DownloadRequest.capture(
            "https://example.com/original", output_dir=str(root), quality="720p"
        )
    )
    history.record_download("https://example.com/history")
    Store(Policy(default_output_dir=root))
    monkeypatch.setenv("PINAK_MCP_CONFIG", str(tmp_path / "missing-policy.json"))
    monkeypatch.setattr(updates, "CONFIG_FILE", str(tmp_path / "missing-core.json"))
    prepared = updates.prepare_update()
    later, _ = core.add_job(
        DownloadRequest.capture("https://example.com/later", output_dir=str(root))
    )
    archive = tmp_path / "current-state-archive.bak"
    with sqlite3.connect(isolated_history_db) as source:
        backup.backup_database(source, archive)
    restored = tmp_path / "restored.db"
    with sqlite3.connect(prepared["database_backup"]) as source:
        backup.backup_database(source, restored)
    monkeypatch.setattr(history, "DB_FILE", str(restored))
    assert core.get_job(saved).request.quality == "720p"
    assert core.get_job(saved).attempts == 0
    assert [job.id for job in core.list_jobs()] == [saved]
    assert len(history.get_history()) == 1
    with sqlite3.connect(archive) as connection:
        assert (
            connection.execute("SELECT id FROM queue_jobs WHERE id=?", (later,)).fetchone()[0]
            == later
        )
    assert Path(prepared["database_backup"]).is_file()
