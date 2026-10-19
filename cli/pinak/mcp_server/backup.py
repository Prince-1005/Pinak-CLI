"""Bounded, consistent SQLite snapshots published only after validation."""

from __future__ import annotations

import contextlib
import os
import sqlite3
import time
import uuid
from pathlib import Path


def verify_backup(path: Path) -> None:
    if path.stat().st_size < 100:
        raise sqlite3.DatabaseError(
            "Existing backup is incomplete; preserve and inspect it before migration"
        )
    deadline = time.monotonic() + 10
    with contextlib.closing(
        sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=1)
    ) as connection:
        connection.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
        if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise sqlite3.DatabaseError("Backup integrity verification failed")


def backup_database(source: sqlite3.Connection, destination: Path) -> None:
    temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
    deadline = time.monotonic() + 10

    def progress(_status: int, _remaining: int, _total: int) -> None:
        if time.monotonic() > deadline:
            raise TimeoutError("Database backup exceeded ten seconds; original unchanged")

    try:
        # Keep a crash-interrupted partial snapshot distinct from usable backups.
        with temporary.open("xb"):
            os.chmod(temporary, 0o600)
        with contextlib.closing(sqlite3.connect(temporary)) as target:
            source.backup(target, pages=128, progress=progress, sleep=0.01)
            target.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
            if target.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise sqlite3.DatabaseError("Backup integrity verification failed")
        with temporary.open("r+b") as stream:
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        with contextlib.suppress(OSError):
            temporary.unlink()
