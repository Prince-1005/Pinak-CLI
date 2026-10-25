"""Read-only, scoped accounting for files already in the Library catalog."""

from __future__ import annotations

import contextlib
import shutil
import stat
import time
from pathlib import Path
from typing import Any

from . import library


def report(
    *,
    refresh: bool = False,
    root: str | Path | None = None,
    collection_id: int | None = None,
    limit: int = 25,
    cursor: int = 0,
    root_cursor: int = 0,
    collection_cursor: int = 0,
    allowed_roots: list[Path] | None = None,
    include_capacity: bool = True,
) -> dict[str, Any]:
    """Account for catalog records without walking or modifying media folders.

    Cached lengths are the last catalog observations. A refresh stats only selected
    paths, and keeps its current measurements separate from cached lengths.
    """
    if root is not None and collection_id is not None:
        raise ValueError("Choose a root or collection, not both")
    if not 1 <= limit <= 100 or min(cursor, root_cursor, collection_cursor) < 0:
        raise ValueError("Limit must be 1–100 and cursors must be non-negative")
    chosen = Path(root).expanduser().resolve() if root is not None else None
    with contextlib.closing(library._connect()) as conn:
        registered = [Path(row[0]) for row in conn.execute("SELECT path FROM scan_roots")]
        if chosen is not None and not any(
            library._key(chosen) == library._key(saved) for saved in registered
        ):
            raise ValueError("Root must be a previously scanned Library folder")
        if collection_id is not None:
            library._collection(conn, collection_id)

    def media_rows(*, by_size: bool = False):
        with contextlib.closing(library._connect()) as conn:
            if collection_id is not None:
                if by_size:
                    yield from conn.execute(
                        "SELECT m.* FROM media m JOIN collection_items ci ON ci.media_id=m.id "
                        "WHERE ci.collection_id=? ORDER BY m.size_bytes DESC,m.id",
                        (collection_id,),
                    )
                else:
                    yield from conn.execute(
                        "SELECT m.* FROM media m JOIN collection_items ci ON ci.media_id=m.id "
                        "WHERE ci.collection_id=? ORDER BY m.id",
                        (collection_id,),
                    )
            else:
                if by_size:
                    yield from conn.execute(
                        "SELECT m.* FROM media m ORDER BY m.size_bytes DESC,m.id"
                    )
                else:
                    yield from conn.execute("SELECT m.* FROM media m ORDER BY m.id")

    def memberships():
        with contextlib.closing(library._connect()) as conn:
            sql = (
                "SELECT m.path,m.size_bytes,c.id,c.name FROM collection_items ci "
                "JOIN media m ON m.id=ci.media_id "
                "JOIN collections c ON c.id=ci.collection_id"
            )
            if collection_id is not None:
                sql += " WHERE m.id IN (SELECT media_id FROM collection_items WHERE collection_id=?)"
                rows = conn.execute(sql + " ORDER BY c.id", (collection_id,))
            else:
                rows = conn.execute(sql + " ORDER BY c.id")
            yield from rows

    approved = [path.resolve() for path in allowed_roots] if allowed_roots is not None else None

    def allowed(path: Path) -> bool:
        resolved = path.resolve()
        if chosen is not None and not resolved.is_relative_to(chosen):
            return False
        return approved is None or any(resolved.is_relative_to(base) for base in approved)

    items = 0
    physical: set[tuple[int, int]] = set()
    by_type: dict[str, dict[str, int]] = {}
    by_root: dict[str, dict[str, Any]] = {}
    owner_roots = [
        saved.resolve()
        for saved in registered
        if approved is None or any(saved.resolve().is_relative_to(base) for base in approved)
    ]
    if approved is not None:
        owner_roots.extend(approved)
    ordered_roots = sorted(set(owner_roots), key=lambda value: len(value.parts), reverse=True)
    missing = unreadable = not_regular = 0
    cached_bytes = current_bytes = 0
    observed_at = time.time() if refresh else None
    for row in media_rows():
        path = Path(row["path"])
        if not allowed(path):
            continue
        items += 1
        size = int(row["size_bytes"])
        kind = str(row["media_type"])
        bucket = by_type.setdefault(kind, {"items": 0, "catalog_logical_bytes": 0})
        bucket["items"] += 1
        bucket["catalog_logical_bytes"] += size
        owner = next(
            (saved for saved in ordered_roots if path.resolve().is_relative_to(saved)),
            None,
        )
        root_name = str(owner) if owner is not None else "outside_scan_roots"
        root_bucket = by_root.setdefault(
            root_name, {"root": root_name, "items": 0, "catalog_logical_bytes": 0}
        )
        root_bucket["items"] += 1
        root_bucket["catalog_logical_bytes"] += size
        cached_bytes += size
        entry: dict[str, Any] = {
            "id": int(row["id"]),
            "path": str(path),
            "media_type": kind,
            "catalog_bytes": size,
        }
        if refresh:
            try:
                details = path.lstat()
                if not stat.S_ISREG(details.st_mode):
                    entry["status"] = "not_regular_file"
                    not_regular += 1
                else:
                    resolved = path.resolve(strict=True)
                    if not allowed(resolved):
                        entry["status"] = "unreadable"
                        unreadable += 1
                    else:
                        identity = (details.st_dev, details.st_ino)
                        entry["status"] = "present"
                        entry["current_bytes"] = details.st_size
                        if details.st_ino and identity not in physical:
                            current_bytes += details.st_size
                            physical.add(identity)
                        elif not details.st_ino:
                            current_bytes += details.st_size
            except FileNotFoundError:
                entry["status"] = "missing"
                missing += 1
            except OSError:
                entry["status"] = "unreadable"
                unreadable += 1
        else:
            entry["status"] = "cached"

    collection_totals: dict[int, dict[str, Any]] = {}
    for member in memberships():
        if not allowed(Path(member[0])):
            continue
        cid, name = int(member[2]), str(member[3])
        group = collection_totals.setdefault(
            cid, {"id": cid, "name": name, "items": 0, "catalog_logical_bytes": 0}
        )
        group["items"] += 1
        group["catalog_logical_bytes"] += int(member[1])

    capacities: list[dict[str, Any]] = []
    capacity_next_cursor = None
    if include_capacity:
        roots = [chosen] if chosen is not None else registered
        capacity_roots = [
            base for base in roots if base is not None and (approved is None or allowed(base))
        ]
        for base in capacity_roots[root_cursor : root_cursor + limit]:
            capacity: dict[str, Any] = {"root": str(base)}
            try:
                usage = shutil.disk_usage(base)
                capacity.update(total_bytes=usage.total, free_bytes=usage.free)
            except OSError:
                capacity["status"] = "unavailable"
            capacities.append(capacity)
        if root_cursor + limit < len(capacity_roots):
            capacity_next_cursor = root_cursor + limit

    largest: list[dict[str, Any]] = []
    offset = 0
    for row in media_rows(by_size=True):
        path = Path(row["path"])
        if not allowed(path):
            continue
        if offset < cursor:
            offset += 1
            continue
        entry = {
            "id": int(row["id"]),
            "path": str(path),
            "media_type": str(row["media_type"]),
            "catalog_bytes": int(row["size_bytes"]),
        }
        if refresh:
            try:
                details = path.lstat()
                if not stat.S_ISREG(details.st_mode):
                    entry["status"] = "not_regular_file"
                elif not allowed(path.resolve(strict=True)):
                    entry["status"] = "unreadable"
                else:
                    entry["status"] = "present"
                    entry["current_bytes"] = details.st_size
            except FileNotFoundError:
                entry["status"] = "missing"
            except OSError:
                entry["status"] = "unreadable"
        else:
            entry["status"] = "cached"
        largest.append(entry)
        if len(largest) > limit:
            break

    root_groups = sorted(by_root.values(), key=lambda value: str(value["root"]))
    collection_groups = list(collection_totals.values())
    return {
        "measurement": "refreshed" if refresh else "cached_catalog",
        "observed_at": observed_at,
        "items": items,
        "catalog_logical_bytes": cached_bytes,
        "current_available_bytes": current_bytes if refresh else None,
        "current_counting": "unique device/inode where available" if refresh else None,
        "missing": missing if refresh else None,
        "unreadable": unreadable if refresh else None,
        "not_regular_file": not_regular if refresh else None,
        "by_type": by_type,
        "by_root": root_groups[root_cursor : root_cursor + limit],
        "root_next_cursor": (
            root_cursor + limit if root_cursor + limit < len(root_groups) else None
        ),
        "collections": collection_groups[collection_cursor : collection_cursor + limit],
        "collection_next_cursor": (
            collection_cursor + limit
            if collection_cursor + limit < len(collection_groups)
            else None
        ),
        "collections_overlap": True,
        "capacity": capacities,
        "capacity_next_cursor": capacity_next_cursor,
        "physical_allocated_bytes": None,
        "largest": largest[:limit],
        "next_cursor": cursor + limit if len(largest) > limit else None,
    }
