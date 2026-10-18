"""Durable, single-runner download jobs stored beside local history."""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import sqlite3
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from functools import partial

from filelock import FileLock, Timeout

from . import history
from .downloader import parse_download_text
from .engine import DownloadEvent, DownloadRequest, DownloadResult, run_download

STATES = frozenset({"queued", "running", "succeeded", "skipped", "failed"})


@dataclass(frozen=True)
class QueueJob:
    id: int
    request: DownloadRequest
    status: str
    attempts: int
    created_at: float
    updated_at: float
    last_error: str | None
    files: tuple[str, ...]


@dataclass(frozen=True)
class QueueSummary:
    succeeded: int = 0
    skipped: int = 0
    failed: int = 0
    interrupted: bool = False


def _connect() -> sqlite3.Connection:
    conn = history.get_db_connection()
    try:
        history._create_schema(conn)
        version = int(conn.execute("PRAGMA user_version").fetchone()[0])
        if version > 1:
            raise RuntimeError(f"Queue database schema {version} is newer than this Pinak version")
        if version < 1:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("""CREATE TABLE IF NOT EXISTS queue_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_json TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    started_at REAL,
                    finished_at REAL,
                    last_error TEXT,
                    files_json TEXT NOT NULL DEFAULT '[]'
                )""")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_queue_jobs_status_id ON queue_jobs(status, id)"
            )
            conn.execute("PRAGMA user_version = 1")
            conn.commit()
        return conn
    except BaseException:
        conn.close()
        raise


def init_queue() -> None:
    with contextlib.closing(_connect()):
        pass


def _fingerprint(request: DownloadRequest) -> tuple[str, str]:
    payload = json.dumps(request.to_dict(), sort_keys=True, separators=(",", ":"))
    return payload, hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _insert(conn: sqlite3.Connection, request: DownloadRequest) -> tuple[int, bool]:
    payload, fingerprint = _fingerprint(request)
    if not request.force:
        existing = conn.execute(
            "SELECT id FROM queue_jobs WHERE fingerprint = ? AND status IN ('queued', 'running') "
            "ORDER BY id LIMIT 1",
            (fingerprint,),
        ).fetchone()
        if existing:
            return int(existing["id"]), False
    now = time.time()
    cursor = conn.execute(
        "INSERT INTO queue_jobs (request_json, fingerprint, status, created_at, updated_at) "
        "VALUES (?, ?, 'queued', ?, ?)",
        (payload, fingerprint, now, now),
    )
    assert cursor.lastrowid is not None
    return int(cursor.lastrowid), True


def add_job(request: DownloadRequest) -> tuple[int, bool]:
    with contextlib.closing(_connect()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            answer = _insert(conn, request)
            conn.commit()
            return answer
        except BaseException:
            conn.rollback()
            raise


def import_file(path: str | os.PathLike[str]) -> list[tuple[int, bool]]:
    """Validate every line first; then commit all additions in one transaction."""
    requests: list[DownloadRequest] = []
    with open(path, encoding="utf-8-sig") as source:
        for line_no, line in enumerate(source, start=1):
            raw = line.strip()
            if not raw or raw.startswith("#"):
                continue
            url, audio, force, quality = parse_download_text(raw)
            any_command = raw.lower().startswith(("/any ", "any "))
            try:
                requests.append(
                    DownloadRequest.capture(
                        url,
                        extract_audio=audio,
                        force=force,
                        quality=quality,
                        is_any_command=any_command,
                    )
                )
            except ValueError as exc:
                raise ValueError(f"{path}:{line_no}: {exc}") from exc
    with contextlib.closing(_connect()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            imported = [_insert(conn, request) for request in requests]
            conn.commit()
            return imported
        except BaseException:
            conn.rollback()
            raise


def _row_job(row: sqlite3.Row) -> QueueJob:
    return QueueJob(
        id=int(row["id"]),
        request=DownloadRequest.from_dict(json.loads(row["request_json"])),
        status=str(row["status"]),
        attempts=int(row["attempts"]),
        created_at=float(row["created_at"]),
        updated_at=float(row["updated_at"]),
        last_error=row["last_error"],
        files=tuple(json.loads(row["files_json"])),
    )


def list_jobs(status: str | None = None) -> list[QueueJob]:
    if status is not None and status not in STATES:
        raise ValueError(f"Invalid status: {status}")
    with contextlib.closing(_connect()) as conn:
        if status is None:
            rows = conn.execute("SELECT * FROM queue_jobs ORDER BY id DESC").fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM queue_jobs WHERE status = ? ORDER BY id DESC", (status,)
            ).fetchall()
    return [_row_job(row) for row in rows]


def retry_failed(job_id: int | None = None) -> int:
    if job_id is not None and job_id < 1:
        raise ValueError("Job ID must be positive")
    with contextlib.closing(_connect()) as conn, conn:
        if job_id is None:
            changed = conn.execute(
                "UPDATE queue_jobs SET status = 'queued', updated_at = ?, finished_at = NULL "
                "WHERE status = 'failed'",
                (time.time(),),
            ).rowcount
        else:
            changed = conn.execute(
                "UPDATE queue_jobs SET status = 'queued', updated_at = ?, finished_at = NULL "
                "WHERE id = ? AND status = 'failed'",
                (time.time(), job_id),
            ).rowcount
    return changed


def _recover_running(conn: sqlite3.Connection) -> None:
    """A new runner owns the exclusive lock, so all old running rows are stale."""
    conn.execute(
        "UPDATE queue_jobs SET status = 'queued', updated_at = ?, started_at = NULL, "
        "last_error = 'Interrupted before result was recorded' WHERE status = 'running'",
        (time.time(),),
    )


def _claim_next(conn: sqlite3.Connection, selected: set[int] | None) -> QueueJob | None:
    conn.execute("BEGIN IMMEDIATE")
    try:
        if selected is None:
            row = conn.execute(
                "SELECT * FROM queue_jobs WHERE status = 'queued' ORDER BY id LIMIT 1"
            ).fetchone()
        elif selected:
            row = conn.execute(
                "SELECT jobs.* FROM queue_jobs AS jobs "
                "JOIN queue_selected AS selected ON selected.id = jobs.id "
                "WHERE jobs.status = 'queued' ORDER BY jobs.id LIMIT 1"
            ).fetchone()
        else:
            row = None
        if row is None:
            conn.commit()
            return None
        now = time.time()
        conn.execute(
            "UPDATE queue_jobs SET status = 'running', attempts = attempts + 1, "
            "started_at = ?, updated_at = ?, last_error = NULL, files_json = '[]' WHERE id = ?",
            (now, now, row["id"]),
        )
        conn.commit()
        updated = dict(row)
        updated.update(status="running", attempts=int(row["attempts"]) + 1, updated_at=now)
        return _row_job(updated)  # type: ignore[arg-type]
    except BaseException:
        conn.rollback()
        raise


def _finish(conn: sqlite3.Connection, job_id: int, result: DownloadResult) -> None:
    status = "queued" if result.status == "interrupted" else result.status
    now = time.time()
    with conn:
        conn.execute(
            "UPDATE queue_jobs SET status = ?, updated_at = ?, finished_at = ?, "
            "last_error = ?, files_json = ? WHERE id = ? AND status = 'running'",
            (
                status,
                now,
                None if status == "queued" else now,
                "; ".join(result.errors) or ("Interrupted" if status == "queued" else None),
                json.dumps(result.files),
                job_id,
            ),
        )


def run_queue(
    job_ids: Iterable[int] | None = None,
    *,
    on_event: Callable[[QueueJob, DownloadEvent], None] | None = None,
    limit: int | None = None,
) -> QueueSummary:
    if limit is not None and limit < 1:
        raise ValueError("Limit must be positive")
    selected = set(job_ids) if job_ids is not None else None
    init_queue()
    lock = FileLock(history.DB_FILE + ".queue-run.lock", timeout=0)
    try:
        lock.acquire()
    except Timeout as exc:
        raise RuntimeError("Another Pinak queue runner is active") from exc
    succeeded = skipped = failed = processed = 0
    interrupted = False

    def publish(job: QueueJob, event: DownloadEvent) -> None:
        if on_event:
            try:
                on_event(job, event)
            except Exception:
                logging.getLogger("pinak.queue").exception("Queue display listener failed")

    try:
        with contextlib.closing(_connect()) as conn:
            if selected is not None:
                conn.execute("CREATE TEMP TABLE queue_selected (id INTEGER PRIMARY KEY)")
                conn.executemany(
                    "INSERT INTO queue_selected (id) VALUES (?)", ((job_id,) for job_id in selected)
                )
                conn.commit()
            with conn:
                _recover_running(conn)
            while limit is None or processed < limit:
                job = _claim_next(conn, selected)
                if job is None:
                    break
                processed += 1
                try:
                    publish(job, DownloadEvent("started"))
                    result = run_download(
                        job.request,
                        on_event=partial(publish, job),
                    )
                except KeyboardInterrupt:
                    result = DownloadResult("interrupted", job.request.url, (), ("Interrupted",))
                except Exception as exc:
                    result = DownloadResult("failed", job.request.url, (), (str(exc),))
                _finish(conn, job.id, result)
                publish(
                    job,
                    DownloadEvent(
                        "finished", result.status, files=result.files, errors=result.errors
                    ),
                )
                if result.status == "interrupted":
                    interrupted = True
                    break
                if result.status == "succeeded":
                    succeeded += 1
                elif result.status == "skipped":
                    skipped += 1
                else:
                    failed += 1
    finally:
        lock.release()
    return QueueSummary(succeeded, skipped, failed, interrupted)
