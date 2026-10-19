"""Explicit local backup preflight; never install packages or resume jobs."""

from __future__ import annotations

import contextlib
import os
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from filelock import FileLock, Timeout

from .. import __version__, history
from ..config import CONFIG_FILE
from .backup import backup_database
from .models import config_path
from .policy import ToolFailure


def prepare_update() -> dict[str, Any]:
    """Take a consistent snapshot after refusing an active queue runner."""
    db = Path(history.DB_FILE)
    if not db.is_file():
        return {
            "package_version": __version__,
            "database_backup": None,
            "notice": "No database exists. Close MCP hosts before changing the installation.",
        }
    backup = Path(str(db) + f".update-{uuid.uuid4().hex}.bak")
    settings: list[str] = []
    try:
        with (
            FileLock(str(db) + ".mcp-start.lock", timeout=0),
            FileLock(str(db) + ".queue-run.lock", timeout=0),
        ):
            with contextlib.closing(
                sqlite3.connect(db.as_uri() + "?mode=ro", uri=True, timeout=1)
            ) as source:
                version = source.execute("PRAGMA user_version").fetchone()[0]
                if version > 1:
                    raise ToolFailure(
                        "SCHEMA_INCOMPATIBLE", "Use a newer Pinak version to back up this database."
                    )
                tables = {
                    row[0]
                    for row in source.execute("SELECT name FROM sqlite_master WHERE type='table'")
                }
                if "mcp_runs" in tables:
                    active = source.execute(
                        "SELECT COUNT(*) FROM mcp_runs WHERE state IN ('starting','running','stopping')"
                    ).fetchone()[0]
                    if active:
                        raise ToolFailure(
                            "RUNNER_BUSY",
                            "A run is active or needs reconciliation. Stop it and inspect its status before updating.",
                        )
                backup_database(source, backup)
            for path in (config_path(), Path(CONFIG_FILE)):
                if path.is_file():
                    if path.stat().st_size > 65536:
                        raise ValueError(
                            "Settings exceed 64 KiB; preserve them manually before updating"
                        )
                    target_path = Path(str(path) + f".update-{uuid.uuid4().hex}.bak")
                    with target_path.open("xb") as stream:
                        os.chmod(target_path, 0o600)
                        stream.write(path.read_bytes())
                    settings.append(str(target_path))
    except Timeout as exc:
        raise ToolFailure("RUNNER_BUSY", "Stop queue runners before preparing an update.") from exc
    except Exception:
        # A partial backup must never be mistaken for a usable recovery point.
        with contextlib.suppress(OSError):
            backup.unlink()
        raise
    return {
        "package_version": __version__,
        "database_backup": str(backup),
        "settings_backups": settings,
        "notice": "Point-in-time backup only. Close all MCP hosts and CLI writers before upgrading; no package was changed and no jobs were resumed.",
    }
