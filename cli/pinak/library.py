"""Persistent, local catalog of media files. Never moves or deletes user media."""

from __future__ import annotations

import contextlib
import hashlib
import json
import math
import os
import sqlite3
import stat
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import history
from .media.picker.scanner import SUPPORTED_EXTENSIONS

DB_FILE = Path(history.data_dir) / "library.db"


@dataclass(frozen=True)
class LibraryItem:
    id: int
    path: str
    title: str
    media_type: str
    size_bytes: int
    available: bool
    position: float


class LibraryReceiptConflict(ValueError):
    """A request key was reused for a different Library edit."""


def _key(path: Path) -> str:
    return os.path.normcase(str(path.resolve()))


def _connect() -> sqlite3.Connection:
    DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_FILE, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 10000")
        version = int(conn.execute("PRAGMA user_version").fetchone()[0])
        if version > 2:
            raise RuntimeError(f"Library schema {version} is newer than this Pinak version")
        if version < 1:
            with conn:
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS media (
                        id INTEGER PRIMARY KEY, path TEXT NOT NULL,
                        path_key TEXT NOT NULL UNIQUE, title TEXT NOT NULL,
                        media_type TEXT NOT NULL, size_bytes INTEGER NOT NULL,
                        mtime_ns INTEGER NOT NULL, available INTEGER NOT NULL DEFAULT 1,
                        position REAL NOT NULL DEFAULT 0,
                        created_at REAL NOT NULL, updated_at REAL NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS scan_roots (
                        path_key TEXT PRIMARY KEY, path TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS tags (
                        id INTEGER PRIMARY KEY, name TEXT NOT NULL,
                        name_key TEXT NOT NULL UNIQUE
                    );
                    CREATE TABLE IF NOT EXISTS media_tags (
                        media_id INTEGER NOT NULL REFERENCES media(id) ON DELETE CASCADE,
                        tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
                        PRIMARY KEY(media_id, tag_id)
                    );
                    CREATE TABLE IF NOT EXISTS collections (
                        id INTEGER PRIMARY KEY, name TEXT NOT NULL,
                        name_key TEXT NOT NULL UNIQUE
                    );
                    CREATE TABLE IF NOT EXISTS collection_items (
                        collection_id INTEGER NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
                        media_id INTEGER NOT NULL REFERENCES media(id) ON DELETE CASCADE,
                        position INTEGER NOT NULL,
                        PRIMARY KEY(collection_id, media_id)
                    );
                    CREATE INDEX IF NOT EXISTS idx_collection_order
                        ON collection_items(collection_id, position);
                    CREATE TABLE IF NOT EXISTS bookmarks (
                        id INTEGER PRIMARY KEY,
                        media_id INTEGER NOT NULL REFERENCES media(id) ON DELETE CASCADE,
                        seconds REAL NOT NULL, note TEXT NOT NULL,
                        created_at REAL NOT NULL
                    );
                    PRAGMA user_version = 1;
                """)
        if version < 2:
            with conn:
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS mcp_receipts (
                        tool TEXT NOT NULL, request_key TEXT NOT NULL,
                        arguments_hash TEXT NOT NULL, result_json TEXT NOT NULL,
                        created_at REAL NOT NULL,
                        PRIMARY KEY(tool, request_key)
                    );
                    PRAGMA user_version = 2;
                """)
        try:
            # Search remains available through LIKE when SQLite lacks FTS5.
            exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='media_fts'"
            ).fetchone()
            triggers = conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='trigger' "
                "AND name IN ('media_fts_insert','media_fts_delete','media_fts_update')"
            ).fetchone()[0]
            with conn:
                conn.executescript("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS media_fts USING fts5(
                        title, path, content='media', content_rowid='id'
                    );
                    CREATE TRIGGER IF NOT EXISTS media_fts_insert AFTER INSERT ON media BEGIN
                        INSERT INTO media_fts(rowid, title, path)
                        VALUES (new.id, new.title, new.path);
                    END;
                    CREATE TRIGGER IF NOT EXISTS media_fts_delete AFTER DELETE ON media BEGIN
                        INSERT INTO media_fts(media_fts, rowid, title, path)
                        VALUES ('delete', old.id, old.title, old.path);
                    END;
                    CREATE TRIGGER IF NOT EXISTS media_fts_update AFTER UPDATE OF title, path ON media BEGIN
                        INSERT INTO media_fts(media_fts, rowid, title, path)
                        VALUES ('delete', old.id, old.title, old.path);
                        INSERT INTO media_fts(rowid, title, path)
                        VALUES (new.id, new.title, new.path);
                    END;
                """)
                # An existing database may have been created by a Python build
                # with FTS5 even when this interpreter does not support it.
                conn.execute("SELECT rowid FROM media_fts LIMIT 1")
                if not exists or triggers != 3:
                    conn.execute("INSERT INTO media_fts(media_fts) VALUES ('rebuild')")
        except sqlite3.OperationalError:
            # Disable FTS write triggers as well as falling back for reads.
            # Otherwise catalog inserts would fail on a build without FTS5.
            with conn:
                conn.executescript("""
                    DROP TRIGGER IF EXISTS media_fts_insert;
                    DROP TRIGGER IF EXISTS media_fts_delete;
                    DROP TRIGGER IF EXISTS media_fts_update;
                """)
        return conn
    except BaseException:
        conn.close()
        raise


def _row(row: sqlite3.Row) -> LibraryItem:
    return LibraryItem(
        id=int(row["id"]),
        path=str(row["path"]),
        title=str(row["title"]),
        media_type=str(row["media_type"]),
        size_bytes=int(row["size_bytes"]),
        available=bool(row["available"]),
        position=float(row["position"]),
    )


def mcp_mutate(
    tool: str,
    request_key: str,
    arguments: dict[str, Any],
    action: Callable[[sqlite3.Connection], dict[str, Any]],
    *,
    retention_days: int = 7,
) -> dict[str, Any]:
    """Commit a Library edit and its replay receipt in the same SQLite transaction."""
    payload = json.dumps(arguments, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(payload.encode()).hexdigest()
    with contextlib.closing(_connect()) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "DELETE FROM mcp_receipts WHERE created_at < ?",
            (time.time() - retention_days * 86400,),
        )
        row = conn.execute(
            "SELECT arguments_hash,result_json FROM mcp_receipts WHERE tool=? AND request_key=?",
            (tool, request_key),
        ).fetchone()
        if row is not None:
            if row["arguments_hash"] != digest:
                raise LibraryReceiptConflict(
                    "This request_key was used with different Library arguments"
                )
            return json.loads(row["result_json"])
        result = action(conn)
        conn.execute(
            "INSERT INTO mcp_receipts(tool,request_key,arguments_hash,result_json,created_at) "
            "VALUES (?,?,?,?,?)",
            (tool, request_key, digest, json.dumps(result, separators=(",", ":")), time.time()),
        )
        return result


def _name(value: str) -> tuple[str, str]:
    name = value.strip()
    if not name or len(name) > 100 or any(ord(c) < 32 for c in name):
        raise ValueError("Name must contain 1–100 printable characters")
    return name, name.casefold()


def _file(path: str | Path) -> tuple[Path, os.stat_result, str]:
    raw = Path(path).expanduser().absolute()
    if raw.is_symlink():
        raise ValueError("Library does not follow symbolic links")
    resolved = raw.resolve(strict=True)
    details = resolved.stat()
    if not stat.S_ISREG(details.st_mode):
        raise ValueError(f"Not a regular file: {path}")
    media_type = SUPPORTED_EXTENSIONS.get(resolved.suffix.lower())
    if media_type is None:
        raise ValueError(f"Unsupported media file: {path}")
    return resolved, details, media_type


def _upsert(conn: sqlite3.Connection, path: str | Path) -> int:
    file, details, media_type = _file(path)
    now = time.time()
    conn.execute(
        "INSERT INTO media(path, path_key, title, media_type, size_bytes, mtime_ns, "
        "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(path_key) DO UPDATE SET path=excluded.path, "
        "media_type=excluded.media_type, size_bytes=excluded.size_bytes, "
        "mtime_ns=excluded.mtime_ns, available=1, "
        "updated_at=excluded.updated_at",
        (
            str(file),
            _key(file),
            file.stem,
            media_type,
            details.st_size,
            details.st_mtime_ns,
            now,
            now,
        ),
    )
    found = conn.execute("SELECT id FROM media WHERE path_key=?", (_key(file),)).fetchone()
    assert found is not None
    return int(found["id"])


def add_files(paths: list[str] | tuple[str, ...]) -> tuple[int, int]:
    """Best-effort download integration: existing files are indexed; errors are counted."""
    added = failed = 0
    with contextlib.closing(_connect()) as conn:
        for path in paths:
            try:
                with conn:
                    _upsert(conn, path)
                added += 1
            except (OSError, ValueError, sqlite3.Error):
                failed += 1
    return added, failed


def scan(folder: str | Path) -> tuple[int, int, list[str]]:
    root = Path(folder).expanduser().absolute()
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Choose an existing, non-symlink folder")
    root = root.resolve(strict=True)
    found: set[str] = set()
    visited_dirs: set[str] = {_key(root)}
    errors: list[str] = []
    count = 0
    with contextlib.closing(_connect()) as conn:
        with conn:
            conn.execute(
                "INSERT INTO scan_roots(path_key, path) VALUES (?, ?) "
                "ON CONFLICT(path_key) DO UPDATE SET path=excluded.path",
                (_key(root), str(root)),
            )

        def failed(exc: OSError) -> None:
            errors.append(str(exc))

        for current, dirs, files in os.walk(root, followlinks=False, onerror=failed):
            kept: list[str] = []
            for name in dirs:
                directory = Path(current) / name
                try:
                    resolved = directory.resolve(strict=True)
                    key = _key(resolved)
                    if (
                        not directory.is_symlink()
                        and resolved.is_relative_to(root)
                        and key not in visited_dirs
                    ):
                        visited_dirs.add(key)
                        kept.append(name)
                except OSError as exc:
                    errors.append(f"{directory}: {exc}")
            dirs[:] = kept
            for name in files:
                path = Path(current) / name
                if path.suffix.lower() not in SUPPORTED_EXTENSIONS or path.is_symlink():
                    continue
                try:
                    if not path.resolve(strict=True).is_relative_to(root):
                        continue
                    with conn:
                        _upsert(conn, path)
                    found.add(_key(path))
                    count += 1
                except (OSError, ValueError, sqlite3.Error) as exc:
                    errors.append(f"{path}: {exc}")
        # Partial scans must not mark entries absent based on incomplete evidence.
        if not errors:
            with conn:
                rows = conn.execute(
                    "SELECT id, path, path_key FROM media WHERE available=1"
                ).fetchall()
                for row in rows:
                    path = Path(row["path"])
                    if (
                        path.is_relative_to(root)
                        and row["path_key"] not in found
                        and not path.is_file()
                    ):
                        conn.execute("UPDATE media SET available=0 WHERE id=?", (row["id"],))
    return count, len(errors), errors[:10]


def scan_all() -> tuple[int, int, list[str]]:
    with contextlib.closing(_connect()) as conn:
        roots = [row[0] for row in conn.execute("SELECT path FROM scan_roots ORDER BY path")]
    count = failures = 0
    errors: list[str] = []
    for root in roots:
        try:
            found, bad, details = scan(root)
            count += found
            failures += bad
            errors.extend(details)
        except (OSError, ValueError, sqlite3.Error) as exc:
            failures += 1
            errors.append(f"{root}: {exc}")
    return count, failures, errors[:10]


def get(media_id: int) -> LibraryItem:
    if media_id < 1:
        raise ValueError("Media ID must be positive")
    with contextlib.closing(_connect()) as conn:
        row = conn.execute("SELECT * FROM media WHERE id=?", (media_id,)).fetchone()
    if row is None:
        raise ValueError(f"Library item #{media_id} was not found")
    return _row(row)


def get_by_path(path: str | Path) -> LibraryItem | None:
    with contextlib.closing(_connect()) as conn:
        row = conn.execute("SELECT * FROM media WHERE path_key=?", (_key(Path(path)),)).fetchone()
    return _row(row) if row else None


def list_items(
    limit: int = 100, *, media_type: str | None = None, before_id: int | None = None
) -> list[LibraryItem]:
    if not 1 <= limit <= 500:
        raise ValueError("Limit must be between 1 and 500")
    if media_type and media_type not in {"audio", "video", "picture"}:
        raise ValueError("Type must be audio, video, or picture")
    if before_id is not None and before_id < 1:
        raise ValueError("Cursor must be positive")
    with contextlib.closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT * FROM media WHERE (? IS NULL OR media_type=?) "
            "AND id < ? ORDER BY id DESC LIMIT ?",
            (media_type, media_type, before_id or 9223372036854775807, limit),
        ).fetchall()
    return [_row(row) for row in rows]


def search(
    query: str, *, tag: str | None = None, limit: int = 100, before_id: int | None = None
) -> list[LibraryItem]:
    if not query.strip() and not tag:
        raise ValueError("Give a search term or tag")
    if not 1 <= limit <= 500:
        raise ValueError("Limit must be between 1 and 500")
    if before_id is not None and before_id < 1:
        raise ValueError("Cursor must be positive")
    with contextlib.closing(_connect()) as conn:
        tag_key = tag.strip().casefold() if tag else None
        if not query.strip():
            rows = conn.execute(
                "SELECT m.* FROM media m WHERE (? IS NULL OR EXISTS "
                "(SELECT 1 FROM media_tags mt JOIN tags t ON t.id=mt.tag_id "
                "WHERE mt.media_id=m.id AND t.name_key=?)) "
                "AND m.id < ? ORDER BY m.id DESC LIMIT ?",
                (tag_key, tag_key, before_id or 9223372036854775807, limit),
            ).fetchall()
        else:
            phrase = '"' + query.strip().replace('"', '""') + '"'
            try:
                rows = conn.execute(
                    "SELECT m.* FROM media m WHERE (m.id IN "
                    "(SELECT rowid FROM media_fts WHERE media_fts MATCH ?) OR "
                    "EXISTS (SELECT 1 FROM media_tags mt JOIN tags t ON t.id=mt.tag_id "
                    "WHERE mt.media_id=m.id AND t.name LIKE ? ESCAPE '\\')) "
                    "AND (? IS NULL OR EXISTS (SELECT 1 FROM media_tags mt "
                    "JOIN tags t ON t.id=mt.tag_id WHERE mt.media_id=m.id AND t.name_key=?)) "
                    "AND m.id < ? ORDER BY m.id DESC LIMIT ?",
                    (
                        phrase,
                        _like(query),
                        tag_key,
                        tag_key,
                        before_id or 9223372036854775807,
                        limit,
                    ),
                ).fetchall()
            except sqlite3.OperationalError:
                # The catalog remains searchable on SQLite builds without FTS5.
                rows = conn.execute(
                    "SELECT m.* FROM media m WHERE (m.title LIKE ? ESCAPE '\\' "
                    "OR m.path LIKE ? ESCAPE '\\' OR EXISTS "
                    "(SELECT 1 FROM media_tags mt JOIN tags t ON t.id=mt.tag_id "
                    "WHERE mt.media_id=m.id AND t.name LIKE ? ESCAPE '\\')) "
                    "AND (? IS NULL OR EXISTS (SELECT 1 FROM media_tags mt "
                    "JOIN tags t ON t.id=mt.tag_id WHERE mt.media_id=m.id AND t.name_key=?)) "
                    "AND m.id < ? ORDER BY m.id DESC LIMIT ?",
                    (
                        _like(query),
                        _like(query),
                        _like(query),
                        tag_key,
                        tag_key,
                        before_id or 9223372036854775807,
                        limit,
                    ),
                ).fetchall()
    return [_row(row) for row in rows]


def _like(value: str) -> str:
    return "%" + value.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _media(conn: sqlite3.Connection, media_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM media WHERE id=?", (media_id,)).fetchone()
    if media_id < 1 or row is None:
        raise ValueError(f"Library item #{media_id} was not found")
    return row


def relink(media_id: int, path: str | Path) -> None:
    file, details, media_type = _file(path)
    with contextlib.closing(_connect()) as conn, conn:
        row = _media(conn, media_id)
        if media_type != row["media_type"]:
            raise ValueError("Replacement must have the same media type")
        occupied = conn.execute("SELECT id FROM media WHERE path_key=?", (_key(file),)).fetchone()
        if occupied is not None and int(occupied[0]) != media_id:
            raise ValueError(
                f"That path already belongs to library item #{occupied[0]}; "
                "forget the duplicate item before relinking"
            )
        conn.execute(
            "UPDATE media SET path=?, path_key=?, size_bytes=?, mtime_ns=?, "
            "available=1, updated_at=? WHERE id=?",
            (str(file), _key(file), details.st_size, details.st_mtime_ns, time.time(), media_id),
        )


def forget(media_id: int) -> None:
    with contextlib.closing(_connect()) as conn, conn:
        _media(conn, media_id)
        conn.execute("DELETE FROM media WHERE id=?", (media_id,))


def tags(media_id: int) -> list[str]:
    get(media_id)
    with contextlib.closing(_connect()) as conn:
        return [
            row[0]
            for row in conn.execute(
                "SELECT t.name FROM tags t JOIN media_tags mt ON mt.tag_id=t.id "
                "WHERE mt.media_id=? ORDER BY t.name_key",
                (media_id,),
            )
        ]


def tag_add(media_id: int, name: str) -> None:
    label, key = _name(name)
    with contextlib.closing(_connect()) as conn, conn:
        _media(conn, media_id)
        conn.execute("INSERT OR IGNORE INTO tags(name, name_key) VALUES (?, ?)", (label, key))
        conn.execute(
            "INSERT OR IGNORE INTO media_tags(media_id,tag_id) "
            "SELECT ?,id FROM tags WHERE name_key=?",
            (media_id, key),
        )


def tag_remove(media_id: int, name: str) -> None:
    _, key = _name(name)
    with contextlib.closing(_connect()) as conn, conn:
        _media(conn, media_id)
        conn.execute(
            "DELETE FROM media_tags WHERE media_id=? AND tag_id IN "
            "(SELECT id FROM tags WHERE name_key=?)",
            (media_id, key),
        )


def collection_create(name: str) -> int:
    label, key = _name(name)
    with contextlib.closing(_connect()) as conn, conn:
        cursor = conn.execute("INSERT INTO collections(name,name_key) VALUES (?,?)", (label, key))
        assert cursor.lastrowid is not None
        return int(cursor.lastrowid)


def collection_list() -> list[tuple[int, str, int]]:
    with contextlib.closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT c.id,c.name,COUNT(ci.media_id) AS count FROM collections c "
            "LEFT JOIN collection_items ci ON ci.collection_id=c.id "
            "GROUP BY c.id ORDER BY c.name_key"
        )
        return [(int(r[0]), str(r[1]), int(r[2])) for r in rows]


def _collection(conn: sqlite3.Connection, collection_id: int) -> None:
    if (
        collection_id < 1
        or not conn.execute("SELECT 1 FROM collections WHERE id=?", (collection_id,)).fetchone()
    ):
        raise ValueError(f"Collection #{collection_id} was not found")


def collection_items(collection_id: int) -> list[LibraryItem]:
    with contextlib.closing(_connect()) as conn:
        _collection(conn, collection_id)
        return [
            _row(row)
            for row in conn.execute(
                "SELECT m.* FROM collection_items ci JOIN media m ON m.id=ci.media_id "
                "WHERE ci.collection_id=? ORDER BY ci.position,ci.media_id",
                (collection_id,),
            )
        ]


def collection_add(collection_id: int, media_id: int) -> None:
    with contextlib.closing(_connect()) as conn, conn:
        _collection(conn, collection_id)
        _media(conn, media_id)
        conn.execute(
            "INSERT OR IGNORE INTO collection_items(collection_id,media_id,position) "
            "VALUES (?,?,COALESCE((SELECT MAX(position)+1 FROM collection_items "
            "WHERE collection_id=?),0))",
            (collection_id, media_id, collection_id),
        )


def collection_remove(collection_id: int, media_id: int) -> None:
    with contextlib.closing(_connect()) as conn, conn:
        _collection(conn, collection_id)
        if not conn.execute(
            "DELETE FROM collection_items WHERE collection_id=? AND media_id=?",
            (collection_id, media_id),
        ).rowcount:
            raise ValueError(f"Item #{media_id} is not in collection #{collection_id}")


def collection_move(collection_id: int, media_id: int, before_id: int) -> None:
    with contextlib.closing(_connect()) as conn, conn:
        _collection(conn, collection_id)
        ids = [
            int(row[0])
            for row in conn.execute(
                "SELECT media_id FROM collection_items WHERE collection_id=? "
                "ORDER BY position, media_id",
                (collection_id,),
            )
        ]
        if media_id not in ids or before_id not in ids:
            raise ValueError("Both items must be in the collection")
        if media_id == before_id:
            return
        ids.remove(media_id)
        ids.insert(ids.index(before_id), media_id)
        conn.executemany(
            "UPDATE collection_items SET position=? WHERE collection_id=? AND media_id=?",
            ((index, collection_id, item) for index, item in enumerate(ids)),
        )


def bookmark_add(media_id: int, seconds: float, note: str) -> int:
    if not math.isfinite(seconds) or seconds < 0:
        raise ValueError("Bookmark time must be non-negative and finite")
    if len(note) > 500 or any(ord(c) < 32 for c in note):
        raise ValueError("Bookmark note must be at most 500 printable characters")
    with contextlib.closing(_connect()) as conn, conn:
        row = _media(conn, media_id)
        if row["media_type"] == "picture":
            raise ValueError("Pictures do not have timestamped bookmarks")
        cursor = conn.execute(
            "INSERT INTO bookmarks(media_id,seconds,note,created_at) VALUES (?,?,?,?)",
            (media_id, seconds, note.strip(), time.time()),
        )
        assert cursor.lastrowid is not None
        return int(cursor.lastrowid)


def bookmark_list(media_id: int) -> list[tuple[int, float, str]]:
    get(media_id)
    with contextlib.closing(_connect()) as conn:
        return [
            (int(r[0]), float(r[1]), str(r[2]))
            for r in conn.execute(
                "SELECT id,seconds,note FROM bookmarks WHERE media_id=? ORDER BY seconds,id",
                (media_id,),
            )
        ]


def bookmark_get(bookmark_id: int) -> tuple[LibraryItem, float, str]:
    with contextlib.closing(_connect()) as conn:
        row = conn.execute(
            "SELECT m.*,b.seconds,b.note FROM bookmarks b JOIN media m ON m.id=b.media_id "
            "WHERE b.id=?",
            (bookmark_id,),
        ).fetchone()
    if row is None or bookmark_id < 1:
        raise ValueError(f"Bookmark #{bookmark_id} was not found")
    return _row(row), float(row["seconds"]), str(row["note"])


def bookmark_remove(bookmark_id: int) -> None:
    with contextlib.closing(_connect()) as conn, conn:
        if not conn.execute("DELETE FROM bookmarks WHERE id=?", (bookmark_id,)).rowcount:
            raise ValueError(f"Bookmark #{bookmark_id} was not found")


def save_position(path: str | Path, seconds: float, duration: float) -> None:
    if not math.isfinite(seconds) or seconds < 0:
        return
    if not math.isfinite(duration) or duration < 0:
        duration = 0
    position = (
        0.0
        if duration > 0 and (seconds >= duration * 0.95 or duration - seconds <= 30)
        else seconds
    )
    with contextlib.closing(_connect()) as conn, conn:
        conn.execute(
            "UPDATE media SET position=?,updated_at=? WHERE path_key=? "
            "AND media_type IN ('audio','video')",
            (position, time.time(), _key(Path(path))),
        )
