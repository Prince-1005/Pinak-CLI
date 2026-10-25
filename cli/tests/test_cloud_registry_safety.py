"""Cloud capability identity checks that do not need the optional MCP SDK."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from pinak.mcp_cloud.registry import Registry, digest
from pinak.mcp_cloud.settings import Settings


def _settings(root: Path) -> Settings:
    return Settings(
        data_dir=root,
        public_url="http://127.0.0.1:8000",
        allow_insecure_loopback=True,
    )


def test_open_link_binds_to_original_file_identity(tmp_path: Path) -> None:
    registry = Registry(_settings(tmp_path))
    registry.create("alice")
    downloads = registry.root("alice") / "downloads"
    downloads.mkdir(parents=True)
    original = downloads / "clip.mp3"
    original.write_bytes(b"first")
    token = str(registry.issue_link("alice", original)["url"]).rsplit("/", 1)[1]
    opened = registry.open_link(token)
    assert opened is not None
    handle, size, name = opened
    try:
        assert (handle.read(), size, name) == (b"first", 5, "clip.mp3")
    finally:
        handle.close()

    stamp = original.stat().st_mtime_ns
    replacement = downloads / "replacement.mp3"
    replacement.write_bytes(b"other")
    os.utime(replacement, ns=(stamp, stamp))
    replacement.replace(original)
    assert registry.resolve_link(token) is None
    assert registry.open_link(token) is None


def test_old_cloud_links_are_invalidated_during_identity_migration(tmp_path: Path) -> None:
    root = tmp_path / "old"
    root.mkdir()
    path = root / "cloud.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE cloud_schema (version INTEGER NOT NULL)")
        db.execute("INSERT INTO cloud_schema VALUES (1)")
        db.execute(
            "CREATE TABLE links (token_hash TEXT PRIMARY KEY, username TEXT NOT NULL, "
            "relative_path TEXT NOT NULL, expires REAL NOT NULL, "
            "size INTEGER NOT NULL, modified INTEGER NOT NULL)"
        )
        db.execute(
            "INSERT INTO links VALUES (?, 'alice', 'clip.mp3', 9999999999, 5, 1)", (digest("old"),)
        )
    registry = Registry(_settings(root))
    with registry.connect() as db:
        assert db.execute("SELECT version FROM cloud_schema").fetchone()[0] == 2
        assert db.execute("SELECT COUNT(*) FROM links").fetchone()[0] == 0
