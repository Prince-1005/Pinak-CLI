"""Operator-managed identities and expiring file capabilities, separate from queues."""

from __future__ import annotations

import contextlib
import hashlib
import os
import re
import secrets
import sqlite3
import time
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO

from .settings import Settings


def digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class Registry:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        settings.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = settings.data_dir / "cloud.sqlite3"
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS cloud_schema (version INTEGER NOT NULL)")
            row = db.execute("SELECT version FROM cloud_schema").fetchone()
            if row and row[0] not in (1, 2):
                raise ValueError("Unsupported cloud schema; preserve data and use compatible code")
            if not row:
                db.execute("INSERT INTO cloud_schema VALUES (2)")
            db.execute("""CREATE TABLE IF NOT EXISTS users (
                name TEXT PRIMARY KEY, token_hash TEXT UNIQUE NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1, created REAL NOT NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS links (
                token_hash TEXT PRIMARY KEY, username TEXT NOT NULL,
                relative_path TEXT NOT NULL, expires REAL NOT NULL,
                size INTEGER NOT NULL, modified INTEGER NOT NULL,
                device INTEGER NOT NULL, inode INTEGER NOT NULL)""")
            if row and row[0] == 1:
                db.execute("ALTER TABLE links ADD COLUMN device INTEGER NOT NULL DEFAULT 0")
                db.execute("ALTER TABLE links ADD COLUMN inode INTEGER NOT NULL DEFAULT 0")
                db.execute("DELETE FROM links")  # Old capabilities lack an identity binding.
                db.execute("UPDATE cloud_schema SET version=2")
        self.path.chmod(0o600)

    @contextlib.contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        with contextlib.closing(sqlite3.connect(self.path, timeout=5)) as db, db:
            db.row_factory = sqlite3.Row
            yield db

    def create(self, name: str) -> str:
        if not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", name):
            raise ValueError("User name must match [a-z][a-z0-9_-]{0,31}")
        token = secrets.token_urlsafe(32)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT COUNT(*) FROM users").fetchone()[0] >= self.settings.max_users:
                raise ValueError("Maximum users reached; raise the operator limit deliberately")
            db.execute("INSERT INTO users VALUES (?, ?, 1, ?)", (name, digest(token), time.time()))
        return token

    def authenticate(self, token: str) -> str | None:
        if len(token) > 256:
            return None
        with self.connect() as db:
            row = db.execute(
                "SELECT name FROM users WHERE token_hash=? AND enabled=1", (digest(token),)
            ).fetchone()
        return str(row[0]) if row else None

    def rotate(self, name: str, *, revoke: bool = False) -> str | None:
        token = secrets.token_urlsafe(32)
        with self.connect() as db:
            changed = db.execute(
                "UPDATE users SET token_hash=?, enabled=? WHERE name=?",
                (digest(token), 0 if revoke else 1, name),
            ).rowcount
            if not changed:
                raise ValueError("Unknown user")
            db.execute("DELETE FROM links WHERE username=?", (name,))
        return None if revoke else token

    def list_users(self) -> list[dict[str, object]]:
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT name, enabled, created FROM users")]

    def root(self, name: str) -> Path:
        # Only names from the authenticated registry may reach this method.
        if not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", name):
            raise ValueError("Invalid user")
        return self.settings.data_dir / "users" / name

    def issue_link(self, name: str, path: Path) -> dict[str, object]:
        root = (self.root(name) / "downloads").resolve()
        resolved = path.resolve(strict=True)
        if not resolved.is_relative_to(root) or not resolved.is_file():
            raise ValueError("File is outside this user's download area")
        stat = resolved.stat()
        token = secrets.token_urlsafe(32)
        expires = time.time() + self.settings.link_seconds
        with self.connect() as db:
            db.execute("DELETE FROM links WHERE expires < ?", (time.time(),))
            db.execute(
                "INSERT INTO links VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    digest(token),
                    name,
                    str(resolved.relative_to(root)),
                    expires,
                    stat.st_size,
                    stat.st_mtime_ns,
                    stat.st_dev,
                    stat.st_ino,
                ),
            )
        return {
            "url": f"{self.settings.public_url}/files/{token}",
            "expires_at": datetime.fromtimestamp(expires, timezone.utc).isoformat(),
            "bytes": stat.st_size,
            "warning": "Anyone with this temporary link can retrieve this file.",
        }

    def _link_row(self, token: str) -> sqlite3.Row | None:
        if len(token) > 256:
            return None
        with self.connect() as db:
            return db.execute(
                "SELECT links.* FROM links JOIN users ON users.name=links.username "
                "WHERE links.token_hash=? AND links.expires>? AND users.enabled=1",
                (digest(token), time.time()),
            ).fetchone()

    def resolve_link(self, token: str) -> Path | None:
        row = self._link_row(token)
        if row is None:
            return None
        root = (self.root(row["username"]) / "downloads").resolve()
        path = (root / row["relative_path"]).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            return None
        stat = path.stat()
        expected = (row["size"], row["modified"], row["device"], row["inode"])
        actual = (stat.st_size, stat.st_mtime_ns, stat.st_dev, stat.st_ino)
        return path if actual == expected else None

    def open_link(self, token: str) -> tuple[BinaryIO, int, str] | None:
        """Open the capability's exact file and keep its descriptor pinned for delivery."""
        row = self._link_row(token)
        if row is None:
            return None
        root = (self.root(row["username"]) / "downloads").resolve()
        path = root / row["relative_path"]
        try:
            resolved = path.resolve(strict=True)
            if not resolved.is_relative_to(root):
                return None
            flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(resolved, flags)
            try:
                details = os.fstat(descriptor)
                expected = (row["size"], row["modified"], row["device"], row["inode"])
                actual = (details.st_size, details.st_mtime_ns, details.st_dev, details.st_ino)
                if actual != expected or not path.resolve(strict=True).is_relative_to(root):
                    return None
                handle = os.fdopen(descriptor, "rb")
                descriptor = -1
                return handle, details.st_size, resolved.name
            finally:
                if descriptor >= 0:
                    os.close(descriptor)
        except (OSError, ValueError):
            return None
