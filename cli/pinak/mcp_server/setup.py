"""Side-effect-free diagnostics and explicit, backed-up client setup."""

from __future__ import annotations

import importlib.metadata
import json
import logging
import logging.handlers
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

import platformdirs
from filelock import FileLock

from .. import __version__, history
from ..config import CONFIG_FILE, config, validate_settings
from ..utils import get_ffmpeg_path, get_ffprobe_path
from .models import Policy, config_path, load_policy
from .policy import clean


def load_core_settings() -> None:
    path = Path(CONFIG_FILE)
    if path.is_file():
        if path.stat().st_size > 65536:
            raise ValueError("Core configuration exceeds 64 KiB")
        payload = json.loads(path.read_text(encoding="utf-8"))
        config.update(validate_settings(payload).model_dump())


def diagnose(policy: Policy | None = None) -> dict[str, Any]:
    policy = policy or load_policy()
    try:
        sdk = importlib.metadata.version("mcp")
    except importlib.metadata.PackageNotFoundError:
        sdk = None
    errors, warnings = [], []
    if sdk != "2.3.0":
        errors.append(
            'Install this release with python -m pip install "pinak-cli[mcp]" in the same interpreter.'
        )
    binaries = {}
    for name, path in (("ffmpeg", get_ffmpeg_path()), ("ffprobe", get_ffprobe_path())):
        found = bool(Path(path).is_file() or shutil.which(path))
        usable = False
        if found:
            try:
                result = subprocess.run(  # nosec B603: trusted local binary resolution, no tool-supplied flags
                    [path, "-version"],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=2,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                usable = result.returncode == 0
            except (OSError, subprocess.TimeoutExpired):
                pass
        binaries[name] = {"available": found, "usable": usable}
        if not found:
            warnings.append(f"{name} unavailable; conversion, merging, or metadata may be limited.")
        elif not usable:
            warnings.append(
                f"{name} is present but failed its bounded version check; repair it before conversion or probing."
            )
    db = Path(history.DB_FILE)
    schema = None
    active_runs = 0
    if db.exists():
        try:
            with sqlite3.connect(db.as_uri() + "?mode=ro", uri=True, timeout=1) as conn:
                deadline = time.monotonic() + 1
                conn.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
                schema = conn.execute("PRAGMA user_version").fetchone()[0]
                if schema > 1:
                    errors.append("Core database schema requires a newer compatible Pinak version.")
                has_extensions = conn.execute(
                    "SELECT name FROM sqlite_master WHERE name='pinak_extensions'"
                ).fetchone()
                if has_extensions:
                    row = conn.execute(
                        "SELECT version FROM pinak_extensions WHERE name='mcp'"
                    ).fetchone()
                    if row and row[0] != 1:
                        errors.append("MCP database extension version is incompatible.")
                    if row and row[0] == 1:
                        active_runs = conn.execute(
                            "SELECT COUNT(*) FROM mcp_runs WHERE state IN ('starting','running','stopping')"
                        ).fetchone()[0]
                        if active_runs:
                            warnings.append(
                                "Saved active runs exist; inspect queue_run_status. This read-only check does not recover stale jobs or prove a worker is alive."
                            )
                if conn.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    errors.append("Database integrity check failed; preserve it before repair.")
        except sqlite3.Error:
            errors.append("Database is locked, unreadable, or corrupt; preserve it before repair.")
    ancestor = policy.default_output_dir
    while not ancestor.exists() and ancestor != ancestor.parent:
        ancestor = ancestor.parent
    writable = os.access(ancestor, os.W_OK)
    if not writable:
        errors.append("Default output root does not appear writable.")
    return {
        "ready": not errors,
        "name": "Pinak-MCP",
        "package_version": __version__,
        "sdk_version": sdk,
        "python": sys.version.split()[0],
        "interpreter": sys.executable,
        "database_exists": db.exists(),
        "core_schema": schema,
        "saved_active_runs": active_runs,
        "mcp_schema_supported": 1,
        "binaries": binaries,
        "output_permissions_advisory": writable,
        "errors": errors,
        "warnings": warnings,
    }


def client_path() -> Path:
    if sys.platform == "win32":
        return (
            Path(os.environ.get("APPDATA") or platformdirs.user_config_dir())
            / "Claude"
            / "claude_desktop_config.json"
        )
    if sys.platform == "darwin":
        return (
            Path.home()
            / "Library"
            / "Application Support"
            / "Claude"
            / "claude_desktop_config.json"
        )
    return (
        Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
        / "Claude"
        / "claude_desktop_config.json"
    )


def connection_profile() -> dict[str, Any]:
    """Transport fields, deliberately independent of any host's config schema."""
    environment = {"PINAK_MCP_CONFIG": str(config_path())}
    if os.environ.get("PINAK_DATA_DIR"):
        environment["PINAK_DATA_DIR"] = os.path.abspath(os.environ["PINAK_DATA_DIR"])
    return {
        "transport": "stdio",
        "command": sys.executable,
        "args": ["-m", "pinak.mcp_server", "serve", "--transport", "stdio"],
        "env": environment,
    }


def configure_client(target: str | None = None, *, apply: bool = False) -> dict[str, Any]:
    path = Path(target).expanduser().absolute() if target else client_path()
    entry = {key: value for key, value in connection_profile().items() if key != "transport"}
    if not apply:
        return {
            "applied": False,
            "target": str(path),
            "entry": {"mcpServers": {"pinak": entry}},
            "next_step": "Review this launch configuration; use --apply to merge it, then restart the host.",
        }
    path.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(str(path) + ".lock", timeout=2):
        if path.is_symlink():
            raise ValueError("Refusing to replace a symlinked client configuration")
        original = path.read_bytes() if path.exists() else None
        if original and len(original) > 1048576:
            raise ValueError("Client configuration exceeds 1 MiB")
        document = json.loads(original) if original is not None else {}
        if not isinstance(document, dict) or not isinstance(document.get("mcpServers", {}), dict):
            raise ValueError("Client configuration must contain a JSON object mcpServers")
        servers = document.setdefault("mcpServers", {})
        old = servers.get("pinak", {})
        if not isinstance(old, dict) or not isinstance(old.get("env", {}), dict):
            raise ValueError("Existing pinak entry or env is malformed")
        entry = {**old, **entry, "env": {**old.get("env", {}), **entry["env"]}}
        if old == entry:
            return {"applied": False, "unchanged": True, "target": str(path)}
        servers["pinak"] = entry
        backup = None
        if original is not None:
            backup = Path(str(path) + f".{uuid.uuid4().hex}.bak")
            backup.write_bytes(original)
            os.chmod(backup, 0o600)
        temporary: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=path.parent, delete=False
            ) as stream:
                temporary = stream.name
                json.dump(document, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary, path.stat().st_mode if path.exists() else 0o600)
            os.replace(temporary, path)
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)
        return {
            "applied": True,
            "target": str(path),
            "backup": str(backup) if backup else None,
            "next_step": "Restart the MCP host. No application was restarted automatically.",
        }


class RedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = clean(record.getMessage())
        record.args = ()
        record.exc_info = None
        record.exc_text = None
        return True


def configure_logging() -> None:
    folder = Path(history.DB_FILE).parent
    folder.mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = [
        logging.StreamHandler(sys.stderr),
        logging.handlers.RotatingFileHandler(
            folder / "pinak-mcp.log", maxBytes=524288, backupCount=2, encoding="utf-8"
        ),
    ]
    for handler in handlers:
        handler.addFilter(RedactFilter())
    logging.basicConfig(level=logging.WARNING, handlers=handlers, force=True)
