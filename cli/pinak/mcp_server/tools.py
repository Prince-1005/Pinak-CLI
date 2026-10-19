"""Shared typed tool services; no SDK, terminal UI, or shell execution."""

from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .. import __version__, history
from .. import queue as core
from ..engine import DownloadRequest
from . import CONTRACT_VERSION, SERVER_NAME, models
from .policy import ToolFailure, clean, output_path, permitted, read_path
from .store import Store

DEFINITIONS: dict[str, tuple[type[models.StrictModel], str, bool]] = {
    "server_info": (models.StrictModel, "Read Pinak-MCP versions and capabilities.", True),
    "queue_add": (models.Add, "Save a download job. Does not start a download.", False),
    "queue_list": (models.JobList, "List saved jobs with stable ID pagination.", True),
    "queue_show": (
        models.Show,
        "Inspect saved options, files, and errors; cursor pages file indices.",
        True,
    ),
    "queue_retry": (models.Retry, "Requeue failed jobs. Supply job_ids or all_failed.", False),
    "queue_cancel": (
        models.IDs,
        "Cancel waiting jobs only; active downloads require queue_stop.",
        False,
    ),
    "queue_remove": (
        models.IDs,
        "Atomically delete inactive job records; keep media and history.",
        False,
    ),
    "queue_clean_completed": (
        models.Mutation,
        "Delete succeeded/skipped records, keeping files and history.",
        False,
    ),
    "queue_start": (
        models.Start,
        "Start a bounded local run; accepted does not mean downloads succeeded.",
        False,
    ),
    "queue_run_status": (models.Run, "Inspect run state and timestamped progress.", True),
    "queue_stop": (
        models.Stop,
        "Request stop of this session's run; keep partial files and saved jobs.",
        False,
    ),
    "history_list": (
        models.History,
        "Read paginated download history for approved file roots.",
        True,
    ),
    "media_info": (
        models.MediaInfo,
        "Read approved local media metadata, without opening playback.",
        True,
    ),
    "diagnostics": (
        models.StrictModel,
        "Inspect local readiness without installing or repairing anything.",
        True,
    ),
}


def utc(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat()


class Tools:
    def __init__(self, policy: models.Policy) -> None:
        self.policy = policy
        self.store = Store(policy)
        from .worker_controller import WorkerController

        self.controller = WorkerController(self.store, policy)

    def close(self) -> None:
        self.controller.close()

    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            if name not in DEFINITIONS:
                raise ToolFailure("UNKNOWN_TOOL", "Tool is not available.")
            model = DEFINITIONS[name][0].model_validate(arguments)
            count = len(getattr(model, "job_ids", None) or [])
            if count > self.policy.max_mutation_items:
                raise ToolFailure("LIMIT_EXCEEDED", "Too many IDs in one operation.")
            if getattr(model, "limit", 0) > self.policy.max_page_size:
                raise ToolFailure("LIMIT_EXCEEDED", "Requested page exceeds configured limit.")
            data = getattr(self, name)(model)
            result = clean(
                {
                    "ok": True,
                    "data": data,
                    "warnings": self.store.warnings,
                    **({"request_key": model.request_key} if hasattr(model, "request_key") else {}),
                }
            )
            if (
                len(json.dumps(result, ensure_ascii=False).encode())
                > self.policy.max_response_bytes
            ):
                raise ToolFailure(
                    "RESPONSE_TOO_LARGE",
                    "Result exceeds configured response limit.",
                    "Request a smaller page or inspect a narrower record.",
                )
            return result
        except ValidationError as exc:
            return self.failure(
                "INVALID_ARGUMENT",
                "; ".join(
                    f"{'.'.join(map(str, e['loc']))}: {e['msg']}"
                    for e in exc.errors(include_input=False, include_context=False)
                ),
            )
        except ToolFailure as exc:
            return self.failure(exc.code, str(exc), exc.recovery, exc.retryable)
        except sqlite3.OperationalError as exc:
            # Extended result codes retain the primary code in the low byte.
            # Python 3.10 does not expose sqlite_errorcode, so retain a narrow
            # message fallback rather than treating every storage failure as busy.
            code = getattr(exc, "sqlite_errorcode", 0) & 255
            busy = code in (5, 6) or "locked" in str(exc).lower()
            return self.failure(
                "DATABASE_BUSY" if busy else "DATABASE_ERROR",
                "Database is locked." if busy else "Database storage operation failed.",
                (
                    "Retry after other writers finish."
                    if busy
                    else "Check disk space, permissions, and local diagnostics; preserve the database before repair."
                ),
                busy,
            )
        except sqlite3.DatabaseError:
            return self.failure(
                "DATABASE_ERROR",
                "Database could not be read safely.",
                "Run local diagnostics and preserve the database before repair.",
            )
        except (ValueError, OSError, RuntimeError) as exc:
            return self.failure("OPERATION_FAILED", str(exc))

    @staticmethod
    def failure(
        code: str,
        message: str,
        recovery: str = "Inspect the request and local diagnostics.",
        retryable: bool = False,
    ) -> dict[str, Any]:
        return clean(
            {
                "ok": False,
                "error": {
                    "code": code,
                    "message": message[:2000],
                    "retryable": retryable,
                    "recovery": recovery,
                    "details": {},
                },
            }
        )

    def server_info(self, model: models.StrictModel) -> dict[str, Any]:
        return {
            "name": SERVER_NAME,
            "package_version": __version__,
            "contract_version": CONTRACT_VERSION,
            "transport": "stdio",
            "tools": list(DEFINITIONS),
            "receipt_retention_days": self.policy.mutation_receipt_retention_days,
            "progress": "poll queue_run_status",
            "history_enabled": history.history_enabled(),
        }

    def queue_add(self, model: models.Add) -> dict[str, Any]:
        destination = output_path(model.options.output_dir, self.policy)
        request = DownloadRequest.capture(
            model.url,
            output_dir=str(destination),
            quality=model.options.quality,
            extract_audio=model.options.audio,
            force=model.options.force,
            trim_range=model.options.trim,
        )

        def add(conn: sqlite3.Connection) -> dict[str, Any]:
            job_id, created = core._insert(conn, request)
            return {
                "job_id": job_id,
                "created": created,
                "status": "queued",
                "options": request.to_dict(),
            }

        return self.store.mutate("queue_add", model.request_key, model.model_dump(mode="json"), add)

    def queue_list(self, model: models.JobList) -> dict[str, Any]:
        with self.store.connect() as conn:
            rows = conn.execute(
                "SELECT id,status,attempts,created_at,request_json FROM queue_jobs WHERE id < ? AND (? IS NULL OR status=?) ORDER BY id DESC LIMIT ?",
                (model.cursor or 9223372036854775807, model.status, model.status, model.limit + 1),
            ).fetchall()
        items = []
        for row in rows[: model.limit]:
            request = DownloadRequest.from_dict(json.loads(row["request_json"]))
            if permitted(Path(request.output_dir), self.policy.output_roots or []):
                items.append(
                    {
                        "id": row["id"],
                        "status": row["status"],
                        "attempts": row["attempts"],
                        "added": utc(row["created_at"]),
                        "url": request.url,
                    }
                )
        return {
            "items": items,
            "next_cursor": rows[model.limit - 1]["id"] if len(rows) > model.limit else None,
            "has_more": len(rows) > model.limit,
        }

    def queue_show(self, model: models.Show) -> dict[str, Any]:
        with self.store.connect() as conn:
            job = core._row_job(core._find_job(conn, model.job_id))
        output_path(job.request.output_dir, self.policy)
        start = (model.cursor or 1) - 1
        files = [
            str(read_path(path, self.policy)) for path in job.files[start : start + model.limit]
        ]
        end = start + len(files)
        error = job.last_error or ""
        return {
            "id": job.id,
            "status": job.status,
            "attempts": job.attempts,
            "created_at": utc(job.created_at),
            "updated_at": utc(job.updated_at),
            "options": job.request.to_dict(),
            "files": files,
            "files_total": len(job.files),
            "next_cursor": end + 1 if end < len(job.files) else None,
            "last_error": error[:8000],
            "error_truncated": len(error) > 8000,
        }

    def _ids(self, conn: sqlite3.Connection, ids: list[int]) -> list[sqlite3.Row]:
        return [core._find_job(conn, job_id) for job_id in dict.fromkeys(ids)]

    def queue_remove(self, model: models.IDs) -> dict[str, Any]:
        def remove(conn: sqlite3.Connection) -> dict[str, Any]:
            rows = self._ids(conn, model.job_ids)
            if any(row["status"] == "running" for row in rows):
                raise ToolFailure(
                    "JOB_RUNNING", "A running job cannot be removed.", "Stop its runner first."
                )
            conn.executemany("DELETE FROM queue_jobs WHERE id=?", ((row["id"],) for row in rows))
            return {
                "removed": [row["id"] for row in rows],
                "files_kept": True,
                "history_kept": True,
            }

        return self.store.mutate("queue_remove", model.request_key, model.model_dump(), remove)

    def queue_cancel(self, model: models.IDs) -> dict[str, Any]:
        def cancel(conn: sqlite3.Connection) -> dict[str, Any]:
            rows = self._ids(conn, model.job_ids)
            if any(row["status"] not in {"queued", "cancelled"} for row in rows):
                raise ToolFailure(
                    "JOB_NOT_QUEUED",
                    "Only waiting jobs can be cancelled.",
                    "Use queue_stop for an owned active run.",
                )
            changed = [row["id"] for row in rows if row["status"] == "queued"]
            conn.executemany(
                "UPDATE queue_jobs SET status='cancelled',updated_at=?,finished_at=? WHERE id=?",
                ((time.time(), time.time(), job_id) for job_id in changed),
            )
            return {
                "changed": changed,
                "unchanged": [row["id"] for row in rows if row["status"] == "cancelled"],
            }

        return self.store.mutate("queue_cancel", model.request_key, model.model_dump(), cancel)

    def queue_retry(self, model: models.Retry) -> dict[str, Any]:
        def retry(conn: sqlite3.Connection) -> dict[str, Any]:
            if model.all_failed:
                count = conn.execute(
                    "UPDATE queue_jobs SET status='queued',updated_at=?,finished_at=NULL WHERE status='failed'",
                    (time.time(),),
                ).rowcount
                return {"changed_count": count, "target": "all_failed"}
            rows = self._ids(conn, model.job_ids or [])
            changed = [row["id"] for row in rows if row["status"] == "failed"]
            conn.executemany(
                "UPDATE queue_jobs SET status='queued',updated_at=?,finished_at=NULL WHERE id=?",
                ((time.time(), job_id) for job_id in changed),
            )
            return {
                "changed": changed,
                "unchanged": [row["id"] for row in rows if row["status"] != "failed"],
            }

        return self.store.mutate("queue_retry", model.request_key, model.model_dump(), retry)

    def queue_clean_completed(self, model: models.Mutation) -> dict[str, Any]:
        def remove(conn: sqlite3.Connection) -> dict[str, Any]:
            return {
                "removed_count": conn.execute(
                    "DELETE FROM queue_jobs WHERE status IN ('succeeded','skipped')"
                ).rowcount,
                "files_kept": True,
                "history_kept": True,
            }

        return self.store.mutate(
            "queue_clean_completed", model.request_key, model.model_dump(), remove
        )

    def queue_start(self, model: models.Start) -> dict[str, Any]:
        return self.controller.start(model)

    def queue_run_status(self, model: models.Run) -> dict[str, Any]:
        result = self.controller.status(model.run_id)
        for key in ("updated_at", "heartbeat"):
            if result[key] is not None:
                result[key] = utc(result[key])
        if result["progress"].get("timestamp"):
            result["progress"]["timestamp"] = utc(result["progress"]["timestamp"])
        return result

    def queue_stop(self, model: models.Stop) -> dict[str, Any]:
        return self.controller.stop(model)

    def history_list(self, model: models.History) -> dict[str, Any]:
        with self.store.connect() as conn:
            rows = conn.execute(
                "SELECT id,time,url,status,mode,quality,files,duration,size FROM downloads WHERE id < ? AND (? IS NULL OR mode=? OR status=?) ORDER BY id DESC LIMIT ?",
                (
                    model.cursor or 9223372036854775807,
                    model.filter,
                    model.filter if model.filter in {"audio", "media"} else None,
                    model.filter if model.filter not in {"audio", "media"} else None,
                    model.limit + 1,
                ),
            ).fetchall()
        items = []
        for row in rows[: model.limit]:
            files = json.loads(row["files"] or "[]")
            if not files or all(
                permitted(Path(path), [*(self.policy.output_roots or []), *self.policy.read_roots])
                for path in files
            ):
                item = dict(row)
                item.update(
                    time=utc(row["time"]),
                    files=files[:10],
                    files_total=len(files),
                    files_truncated=len(files) > 10,
                )
                items.append(item)
        return {
            "items": items,
            "history_enabled": history.history_enabled(),
            "has_more": len(rows) > model.limit,
            "next_cursor": rows[model.limit - 1]["id"] if len(rows) > model.limit else None,
        }

    def media_info(self, model: models.MediaInfo) -> dict[str, Any]:
        from .media_info import inspect_media

        path = read_path(model.path, self.policy)
        return inspect_media(path)

    def diagnostics(self, model: models.StrictModel) -> dict[str, Any]:
        from .setup import diagnose

        return diagnose(self.policy)
