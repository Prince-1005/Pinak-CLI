"""Shared typed tool services; no SDK, terminal UI, or shell execution."""

from __future__ import annotations

import contextlib
import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .. import __version__, history, library, library_storage
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
    "history_show": (
        models.HistoryShow,
        "Inspect one download-history record and page through its saved files.",
        True,
    ),
    "library_scan": (
        models.LibraryScan,
        "Index an explicitly chosen folder inside approved roots; no background scan.",
        False,
    ),
    "library_list": (models.LibraryList, "Page through local Library items.", True),
    "library_search": (models.LibrarySearch, "Search Library titles, paths and tags.", True),
    "library_show": (models.LibraryRef, "Inspect a Library item, tags and bookmarks.", True),
    "library_storage_report": (
        models.LibraryStorage,
        "Report cached logical sizes for approved Library items; collection totals overlap.",
        True,
    ),
    "library_tag_add": (models.LibraryTag, "Tag one Library item.", False),
    "library_tag_remove": (models.LibraryTag, "Remove a tag from one item.", False),
    "library_collection_create": (models.CollectionCreate, "Create an ordered collection.", False),
    "library_collection_list": (models.CollectionPage, "Page through Library collections.", True),
    "library_collection_show": (models.CollectionShow, "Page through an ordered collection.", True),
    "library_collection_add": (models.CollectionEdit, "Add an item to a collection.", False),
    "library_collection_remove": (
        models.CollectionEdit,
        "Remove an item from a collection; keep its file.",
        False,
    ),
    "library_collection_move": (
        models.CollectionMove,
        "Move an item before another in a collection.",
        False,
    ),
    "library_bookmark_add": (models.BookmarkAdd, "Save a timestamped audio/video bookmark.", False),
    "library_bookmark_list": (models.BookmarkPage, "Page through bookmarks for one item.", True),
    "library_bookmark_show": (
        models.BookmarkRef,
        "Show a bookmark path and start time; does not start playback.",
        True,
    ),
    "library_bookmark_remove": (models.BookmarkRemove, "Remove a bookmark; keep its file.", False),
    "library_relink": (
        models.LibraryRelink,
        "Point an item at a moved file of the same type.",
        False,
    ),
    "library_forget": (models.LibraryEdit, "Remove a Library record; keep its file.", False),
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
        except library.LibraryReceiptConflict as exc:
            return self.failure(
                "IDEMPOTENCY_CONFLICT",
                str(exc),
                "Use the original arguments or choose a new request_key.",
            )
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

    def history_show(self, model: models.HistoryShow) -> dict[str, Any]:
        with self.store.connect() as conn:
            row = conn.execute("SELECT * FROM downloads WHERE id=?", (model.history_id,)).fetchone()
        if row is None:
            raise ToolFailure("HISTORY_NOT_FOUND", "History record was not found.")
        files = json.loads(row["files"] or "[]")
        if not isinstance(files, list) or not all(isinstance(path, str) for path in files):
            raise ToolFailure("DATABASE_ERROR", "History file list is invalid.")
        roots = [*(self.policy.output_roots or []), *self.policy.read_roots]
        if any(not permitted(Path(path), roots) for path in files):
            raise ToolFailure(
                "PATH_DENIED", "History record includes a file outside approved roots."
            )
        return {
            "id": row["id"],
            "time": utc(row["time"]),
            "url": row["url"],
            "status": row["status"],
            "mode": row["mode"],
            "quality": row["quality"],
            "duration": row["duration"],
            "size": row["size"],
            "is_forced": bool(row["is_forced"]),
            "files": files[(model.cursor or 1) - 1 : (model.cursor or 1) - 1 + model.limit],
            "files_total": len(files),
            "next_cursor": (
                (model.cursor or 1) + model.limit
                if (model.cursor or 1) - 1 + model.limit < len(files)
                else None
            ),
            "history_enabled": history.history_enabled(),
        }

    def _library_item(self, media_id: int) -> library.LibraryItem:
        item = library.get(media_id)
        read_path(item.path, self.policy)
        return item

    def _authorized_media(self, conn: sqlite3.Connection, media_id: int) -> sqlite3.Row:
        row = library._media(conn, media_id)
        read_path(str(row["path"]), self.policy)
        return row

    def _library_data(self, item: library.LibraryItem) -> dict[str, Any]:
        path = read_path(item.path, self.policy)
        return {
            "id": item.id,
            "path": str(path),
            "title": item.title,
            "media_type": item.media_type,
            "size_bytes": item.size_bytes,
            "available": item.available and path.is_file(),
            "position_seconds": item.position,
        }

    def _library_page(self, rows: list[library.LibraryItem], limit: int) -> dict[str, Any]:
        roots = [*(self.policy.output_roots or []), *self.policy.read_roots]
        items = [
            self._library_data(item) for item in rows[:limit] if permitted(Path(item.path), roots)
        ]
        return {
            "items": items,
            "has_more": len(rows) > limit,
            "next_cursor": rows[limit - 1].id if len(rows) > limit else None,
        }

    def _library_edit(
        self,
        name: str,
        model: (
            models.LibraryEdit
            | models.CollectionCreate
            | models.CollectionEdit
            | models.BookmarkRemove
        ),
        action: Any,
    ) -> dict[str, Any]:
        return library.mcp_mutate(
            name,
            model.request_key,
            model.model_dump(mode="json"),
            action,
            retention_days=self.policy.mutation_receipt_retention_days,
        )

    def library_scan(self, model: models.LibraryScan) -> dict[str, Any]:
        if Path(model.folder).expanduser().is_symlink():
            raise ToolFailure("INVALID_PATH", "Choose a non-symlink folder to scan.")
        folder = read_path(model.folder, self.policy)
        found, failures, errors = library.scan(folder)
        return {
            "indexed": found,
            "scan_errors": failures,
            "errors": errors,
            "partial": failures > 0,
        }

    def library_list(self, model: models.LibraryList) -> dict[str, Any]:
        return self._library_page(
            library.list_items(
                model.limit + 1, media_type=model.media_type, before_id=model.cursor
            ),
            model.limit,
        )

    def library_search(self, model: models.LibrarySearch) -> dict[str, Any]:
        return self._library_page(
            library.search(
                model.query, tag=model.tag, limit=model.limit + 1, before_id=model.cursor
            ),
            model.limit,
        )

    def library_show(self, model: models.LibraryRef) -> dict[str, Any]:
        item = self._library_item(model.media_id)
        with contextlib.closing(library._connect()) as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM bookmarks WHERE media_id=?", (item.id,)
            ).fetchone()[0]
        return {**self._library_data(item), "tags": library.tags(item.id), "bookmarks_count": count}

    def library_storage_report(self, model: models.LibraryStorage) -> dict[str, Any]:
        roots = [*(self.policy.output_roots or []), *self.policy.read_roots]
        if model.root is not None:
            read_path(model.root, self.policy)
        return library_storage.report(
            root=model.root,
            collection_id=model.collection_id,
            cursor=model.cursor or 0,
            root_cursor=model.root_cursor,
            collection_cursor=model.collection_cursor,
            limit=model.limit,
            allowed_roots=roots,
            include_capacity=False,
        )

    def library_tag_add(self, model: models.LibraryTag) -> dict[str, Any]:
        label, key = library._name(model.name)

        def action(conn: sqlite3.Connection) -> dict[str, Any]:
            self._authorized_media(conn, model.media_id)
            conn.execute("INSERT OR IGNORE INTO tags(name,name_key) VALUES (?,?)", (label, key))
            conn.execute(
                "INSERT OR IGNORE INTO media_tags(media_id,tag_id) "
                "SELECT ?,id FROM tags WHERE name_key=?",
                (model.media_id, key),
            )
            return {"media_id": model.media_id, "tag": label}

        return self._library_edit("library_tag_add", model, action)

    def library_tag_remove(self, model: models.LibraryTag) -> dict[str, Any]:
        _, key = library._name(model.name)

        def action(conn: sqlite3.Connection) -> dict[str, Any]:
            self._authorized_media(conn, model.media_id)
            count = conn.execute(
                "DELETE FROM media_tags WHERE media_id=? AND tag_id IN "
                "(SELECT id FROM tags WHERE name_key=?)",
                (model.media_id, key),
            ).rowcount
            return {"media_id": model.media_id, "removed": bool(count)}

        return self._library_edit("library_tag_remove", model, action)

    def library_collection_create(self, model: models.CollectionCreate) -> dict[str, Any]:
        label, key = library._name(model.name)

        def action(conn: sqlite3.Connection) -> dict[str, Any]:
            if conn.execute("SELECT 1 FROM collections WHERE name_key=?", (key,)).fetchone():
                raise ToolFailure(
                    "COLLECTION_EXISTS", "A collection with that name already exists."
                )
            cursor = conn.execute(
                "INSERT INTO collections(name,name_key) VALUES (?,?)",
                (label, key),
            )
            return {"collection_id": cursor.lastrowid, "name": label}

        return self._library_edit("library_collection_create", model, action)

    def library_collection_list(self, model: models.CollectionPage) -> dict[str, Any]:
        roots = [*(self.policy.output_roots or []), *self.policy.read_roots]
        visible: list[dict[str, Any]] = []
        next_id = model.cursor or 9223372036854775807
        with contextlib.closing(library._connect()) as conn:
            while len(visible) <= model.limit:
                rows = conn.execute(
                    "SELECT id,name FROM collections WHERE id < ? ORDER BY id DESC LIMIT 100",
                    (next_id,),
                ).fetchall()
                if not rows:
                    break
                for row in rows:
                    next_id = int(row["id"])
                    items = conn.execute(
                        "SELECT m.path FROM collection_items ci "
                        "JOIN media m ON m.id=ci.media_id WHERE ci.collection_id=?",
                        (next_id,),
                    ).fetchall()
                    total_items = len(items)
                    permitted_count = sum(permitted(Path(item[0]), roots) for item in items)
                    if total_items == 0 or permitted_count > 0:
                        visible.append(
                            {"id": next_id, "name": row["name"], "item_count": permitted_count}
                        )
                    if len(visible) > model.limit:
                        break
        return {
            "items": visible[: model.limit],
            "has_more": len(visible) > model.limit,
            "next_cursor": visible[model.limit - 1]["id"] if len(visible) > model.limit else None,
        }

    def library_collection_show(self, model: models.CollectionShow) -> dict[str, Any]:
        with contextlib.closing(library._connect()) as conn:
            library._collection(conn, model.collection_id)
            rows = conn.execute(
                "SELECT m.*,ci.position FROM collection_items ci "
                "JOIN media m ON m.id=ci.media_id WHERE ci.collection_id=? "
                "AND ci.position >= ? ORDER BY ci.position,ci.media_id LIMIT ?",
                (model.collection_id, model.cursor or 0, model.limit + 1),
            ).fetchall()
        roots = [*(self.policy.output_roots or []), *self.policy.read_roots]
        return {
            "collection_id": model.collection_id,
            "items": [
                {**self._library_data(library._row(row)), "position": row["position"]}
                for row in rows[: model.limit]
                if permitted(Path(row["path"]), roots)
            ],
            "has_more": len(rows) > model.limit,
            "next_cursor": (
                rows[model.limit - 1]["position"] + 1 if len(rows) > model.limit else None
            ),
        }

    def library_collection_add(self, model: models.CollectionEdit) -> dict[str, Any]:
        def action(conn: sqlite3.Connection) -> dict[str, Any]:
            library._collection(conn, model.collection_id)
            self._authorized_media(conn, model.media_id)
            count = conn.execute(
                "INSERT OR IGNORE INTO collection_items(collection_id,media_id,position) "
                "VALUES (?,?,COALESCE((SELECT MAX(position)+1 FROM collection_items "
                "WHERE collection_id=?),0))",
                (model.collection_id, model.media_id, model.collection_id),
            ).rowcount
            return {
                "collection_id": model.collection_id,
                "media_id": model.media_id,
                "added": bool(count),
            }

        return self._library_edit("library_collection_add", model, action)

    def library_collection_remove(self, model: models.CollectionEdit) -> dict[str, Any]:
        def action(conn: sqlite3.Connection) -> dict[str, Any]:
            library._collection(conn, model.collection_id)
            self._authorized_media(conn, model.media_id)
            count = conn.execute(
                "DELETE FROM collection_items WHERE collection_id=? AND media_id=?",
                (model.collection_id, model.media_id),
            ).rowcount
            return {
                "collection_id": model.collection_id,
                "media_id": model.media_id,
                "removed": bool(count),
                "file_kept": True,
            }

        return self._library_edit("library_collection_remove", model, action)

    def library_collection_move(self, model: models.CollectionMove) -> dict[str, Any]:
        def action(conn: sqlite3.Connection) -> dict[str, Any]:
            library._collection(conn, model.collection_id)
            self._authorized_media(conn, model.media_id)
            self._authorized_media(conn, model.before_id)
            ids = [
                int(row[0])
                for row in conn.execute(
                    "SELECT media_id FROM collection_items WHERE collection_id=? "
                    "ORDER BY position,media_id",
                    (model.collection_id,),
                )
            ]
            if model.media_id not in ids or model.before_id not in ids:
                raise ToolFailure("ITEM_NOT_IN_COLLECTION", "Both items must be in the collection.")
            if model.media_id != model.before_id:
                ids.remove(model.media_id)
                ids.insert(ids.index(model.before_id), model.media_id)
                conn.executemany(
                    "UPDATE collection_items SET position=? WHERE collection_id=? AND media_id=?",
                    ((index, model.collection_id, item) for index, item in enumerate(ids)),
                )
            return {
                "collection_id": model.collection_id,
                "media_id": model.media_id,
                "before_id": model.before_id,
                "moved": True,
            }

        return self._library_edit("library_collection_move", model, action)

    def library_bookmark_add(self, model: models.BookmarkAdd) -> dict[str, Any]:
        if any(ord(char) < 32 for char in model.note):
            raise ToolFailure("INVALID_ARGUMENT", "Bookmark note must be printable.")

        def action(conn: sqlite3.Connection) -> dict[str, Any]:
            item = self._authorized_media(conn, model.media_id)
            if item["media_type"] == "picture":
                raise ToolFailure("INVALID_ARGUMENT", "Pictures cannot have timestamp bookmarks.")
            cursor = conn.execute(
                "INSERT INTO bookmarks(media_id,seconds,note,created_at) VALUES (?,?,?,?)",
                (model.media_id, model.seconds, model.note.strip(), time.time()),
            )
            return {
                "bookmark_id": cursor.lastrowid,
                "media_id": model.media_id,
                "seconds": model.seconds,
                "note": model.note.strip(),
            }

        return self._library_edit("library_bookmark_add", model, action)

    def library_bookmark_list(self, model: models.BookmarkPage) -> dict[str, Any]:
        self._library_item(model.media_id)
        with contextlib.closing(library._connect()) as conn:
            rows = conn.execute(
                "SELECT id,seconds,note FROM bookmarks WHERE media_id=? AND id>? "
                "ORDER BY id LIMIT ?",
                (model.media_id, model.cursor or 0, model.limit + 1),
            ).fetchall()
        return {
            "items": [dict(row) for row in rows[: model.limit]],
            "has_more": len(rows) > model.limit,
            "next_cursor": rows[model.limit - 1]["id"] if len(rows) > model.limit else None,
        }

    def library_bookmark_show(self, model: models.BookmarkRef) -> dict[str, Any]:
        item, seconds, note = library.bookmark_get(model.bookmark_id)
        self._library_item(item.id)
        return {
            "bookmark_id": model.bookmark_id,
            "item": self._library_data(item),
            "seconds": seconds,
            "note": note,
            "playback_started": False,
        }

    def library_bookmark_remove(self, model: models.BookmarkRemove) -> dict[str, Any]:
        def action(conn: sqlite3.Connection) -> dict[str, Any]:
            owner = conn.execute(
                "SELECT media_id FROM bookmarks WHERE id=?", (model.bookmark_id,)
            ).fetchone()
            if owner is None:
                raise ToolFailure("BOOKMARK_NOT_FOUND", "Bookmark was not found.")
            self._authorized_media(conn, int(owner[0]))
            count = conn.execute("DELETE FROM bookmarks WHERE id=?", (model.bookmark_id,)).rowcount
            if not count:
                raise ToolFailure("BOOKMARK_NOT_FOUND", "Bookmark was not found.")
            return {"bookmark_id": model.bookmark_id, "removed": True, "file_kept": True}

        return self._library_edit("library_bookmark_remove", model, action)

    def library_relink(self, model: models.LibraryRelink) -> dict[str, Any]:
        def action(conn: sqlite3.Connection) -> dict[str, Any]:
            row = self._authorized_media(conn, model.media_id)
            destination = read_path(model.path, self.policy)
            file, details, media_type = library._file(destination)
            if media_type != row["media_type"]:
                raise ToolFailure("TYPE_MISMATCH", "Replacement has a different media type.")
            occupied = conn.execute(
                "SELECT id FROM media WHERE path_key=?", (library._key(file),)
            ).fetchone()
            if occupied is not None and occupied[0] != model.media_id:
                raise ToolFailure("PATH_IN_USE", "The replacement path belongs to another item.")
            conn.execute(
                "UPDATE media SET path=?,path_key=?,size_bytes=?,mtime_ns=?,"
                "available=1,updated_at=? WHERE id=?",
                (
                    str(file),
                    library._key(file),
                    details.st_size,
                    details.st_mtime_ns,
                    time.time(),
                    model.media_id,
                ),
            )
            return {"media_id": model.media_id, "path": str(file), "relinked": True}

        return self._library_edit("library_relink", model, action)

    def library_forget(self, model: models.LibraryEdit) -> dict[str, Any]:
        def action(conn: sqlite3.Connection) -> dict[str, Any]:
            self._authorized_media(conn, model.media_id)
            conn.execute("DELETE FROM media WHERE id=?", (model.media_id,))
            return {"media_id": model.media_id, "forgotten": True, "file_kept": True}

        return self._library_edit("library_forget", model, action)

    def media_info(self, model: models.MediaInfo) -> dict[str, Any]:
        from .media_info import inspect_media

        path = read_path(model.path, self.policy)
        return inspect_media(path)

    def diagnostics(self, model: models.StrictModel) -> dict[str, Any]:
        from .setup import diagnose

        return diagnose(self.policy)
