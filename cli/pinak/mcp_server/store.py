"""Additive MCP records and atomic mutation receipts in Pinak's existing database."""

from __future__ import annotations

import contextlib
import hashlib
import json
import sqlite3
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from filelock import FileLock, Timeout

from .. import history
from .. import queue as queue_core
from .models import Policy
from .policy import ToolFailure

ACTIVE_RUNS = ("starting", "running", "stopping")


class Store:
    def __init__(self, policy: Policy) -> None:
        self.policy = policy
        db = Path(history.DB_FILE)
        before = set(db.parent.glob(db.name + ".corrupt.*"))
        self.warnings: list[str] = []
        with contextlib.closing(queue_core._connect()) as conn:
            if set(db.parent.glob(db.name + ".corrupt.*")) - before:
                self.warnings.append(
                    "Confirmed database corruption was quarantined by core recovery. A new database is in use; preserve the .corrupt file and inspect local logs before restoring history or jobs."
                )
            exists = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='pinak_extensions'"
            ).fetchone()
            if exists:
                row = conn.execute(
                    "SELECT version FROM pinak_extensions WHERE name='mcp'"
                ).fetchone()
                if row and row[0] != 1:
                    raise ToolFailure(
                        "SCHEMA_INCOMPATIBLE",
                        "MCP database extension requires a different Pinak version.",
                    )
                if row:
                    return
            try:
                with FileLock(history.DB_FILE + ".queue-run.lock", timeout=0):
                    # SQLite backup API includes WAL state; never copy a live .db alone.
                    backup = Path(history.DB_FILE + ".pre-mcp-1.bak")
                    if not backup.exists():
                        with contextlib.closing(sqlite3.connect(backup)) as target:
                            conn.backup(target)
                    with conn:
                        conn.execute("BEGIN IMMEDIATE")
                        conn.execute(
                            "CREATE TABLE IF NOT EXISTS pinak_extensions (name TEXT PRIMARY KEY, version INTEGER NOT NULL)"
                        )
                        conn.execute(
                            "CREATE TABLE IF NOT EXISTS mcp_receipts (tool TEXT NOT NULL, request_key TEXT NOT NULL, arguments_hash TEXT NOT NULL, result_json TEXT NOT NULL, created_at REAL NOT NULL, PRIMARY KEY(tool, request_key))"
                        )
                        conn.execute("""CREATE TABLE IF NOT EXISTS mcp_runs (
                            run_id TEXT PRIMARY KEY, owner TEXT NOT NULL, targets_json TEXT NOT NULL,
                            state TEXT NOT NULL, pid INTEGER, process_started REAL,
                            created_at REAL NOT NULL, updated_at REAL NOT NULL,
                            heartbeat REAL, stop_requested INTEGER NOT NULL DEFAULT 0,
                            progress_json TEXT NOT NULL DEFAULT '{}', summary_json TEXT,
                            last_error TEXT)""")
                        conn.execute("INSERT OR IGNORE INTO pinak_extensions VALUES ('mcp', 1)")
            except Timeout as exc:
                raise ToolFailure(
                    "RUNNER_BUSY",
                    "Stop the current queue run before the first MCP schema setup.",
                    retryable=True,
                ) from exc

    @contextlib.contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        with contextlib.closing(history.get_db_connection()) as conn:
            yield conn

    def mutate(
        self,
        tool: str,
        key: str,
        arguments: dict[str, Any],
        action: Callable[[sqlite3.Connection], dict[str, Any]],
    ) -> dict[str, Any]:
        payload = json.dumps(arguments, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(payload.encode()).hexdigest()
        with self.connect() as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "DELETE FROM mcp_receipts WHERE created_at < ?",
                (time.time() - 86400 * self.policy.mutation_receipt_retention_days,),
            )
            conn.execute(
                "DELETE FROM mcp_runs WHERE state IN ('completed','failed','interrupted') AND updated_at < ?",
                (time.time() - 86400 * self.policy.mutation_receipt_retention_days,),
            )
            row = conn.execute(
                "SELECT * FROM mcp_receipts WHERE tool=? AND request_key=?", (tool, key)
            ).fetchone()
            if row:
                if row["arguments_hash"] != digest:
                    raise ToolFailure(
                        "IDEMPOTENCY_CONFLICT",
                        "This request_key was already used with different arguments.",
                        "Use a new request_key for an intentional different operation.",
                    )
                return json.loads(row["result_json"])
            data = action(conn)
            if (
                len(json.dumps(data, ensure_ascii=False).encode())
                > self.policy.max_response_bytes - 512
            ):
                raise ToolFailure(
                    "RESPONSE_TOO_LARGE",
                    "Mutation result exceeds the configured response limit; no changes committed.",
                    "Reduce the request size or increase the local response limit.",
                )
            conn.execute(
                "INSERT INTO mcp_receipts VALUES (?, ?, ?, ?, ?)",
                (tool, key, digest, json.dumps(data), time.time()),
            )
            return data

    def run(self, run_id: str) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM mcp_runs WHERE run_id=?", (run_id,)).fetchone()
        if row is None:
            raise ToolFailure("RUN_NOT_FOUND", "Run ID was not found.")
        return dict(row)

    def update_run(self, run_id: str, **values: Any) -> None:
        allowed = {
            "state",
            "pid",
            "process_started",
            "heartbeat",
            "stop_requested",
            "progress_json",
            "summary_json",
            "last_error",
        }
        if not values or not set(values).issubset(allowed):
            raise ValueError("Invalid run update fields")
        values["updated_at"] = time.time()
        assignments = ", ".join(f"{name}=?" for name in values)
        with self.connect() as conn, conn:
            conn.execute(
                f"UPDATE mcp_runs SET {assignments} WHERE run_id=?",  # nosec B608
                (*values.values(), run_id),
            )
