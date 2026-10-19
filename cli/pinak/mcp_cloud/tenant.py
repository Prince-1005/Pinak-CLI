"""One persistent local MCP process per cloud user; never shares core globals."""

from __future__ import annotations

import contextlib
import ipaddress
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import anyio

from ..mcp_server.models import load_policy
from ..mcp_server.server import run_server
from ..mcp_server.setup import configure_logging, load_core_settings
from ..mcp_server.tools import Tools


def directory_bytes(root: Path) -> int:
    return sum(
        path.stat().st_size for path in root.rglob("*") if path.is_file() and not path.is_symlink()
    )


def public_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in {"https", "http"} or parsed.username or parsed.password:
            return False
        if not parsed.hostname or parsed.port not in {None, 80, 443}:
            return False
        try:
            return ipaddress.ip_address(parsed.hostname).is_global
        except ValueError:
            # DNS is checked and pinned by the outbound proxy at connection time.
            return parsed.hostname.lower() not in {"localhost", "metadata.google.internal"}
    except (ValueError, OSError):
        return False


class CloudTools(Tools):
    def __init__(self) -> None:
        super().__init__(load_policy())
        self.byte_limit = int(os.environ["PINAK_CLOUD_STORAGE_BYTES"])
        self.job_limit = int(os.environ["PINAK_CLOUD_MAX_JOBS"])
        self.lock = threading.RLock()

    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            key = arguments.get("request_key")
            if isinstance(key, str):
                with self.store.connect() as db:
                    receipt = db.execute(
                        "SELECT 1 FROM mcp_receipts WHERE tool=? AND request_key=? AND created_at>?",
                        (
                            name,
                            key,
                            time.time() - self.policy.mutation_receipt_retention_days * 86400,
                        ),
                    ).fetchone()
                if receipt:
                    return super().call(name, arguments)
            if name == "queue_add":
                # The egress proxy additionally checks every outgoing connection.
                if not public_url(str(arguments.get("url", ""))):
                    return self.failure(
                        "URL_DENIED", "Only public HTTP(S) media URLs on ports 80/443 are allowed."
                    )
                with self.store.connect() as db:
                    count = db.execute("SELECT COUNT(*) FROM queue_jobs").fetchone()[0]
                if count >= self.job_limit:
                    return self.failure(
                        "JOB_LIMIT", "Saved-job limit reached; remove inactive records."
                    )
            if (
                name in {"queue_add", "queue_start"}
                and directory_bytes(self.policy.default_output_dir) >= self.byte_limit
            ):
                return self.failure(
                    "STORAGE_LIMIT", "Download storage limit reached; contact the operator."
                )
            return super().call(name, arguments)


async def serve() -> None:
    with contextlib.redirect_stdout(sys.stderr):
        configure_logging()
        load_core_settings()
        service = CloudTools()

    async def monitor() -> None:
        while True:
            await anyio.sleep(1)
            try:
                used = await anyio.to_thread.run_sync(
                    directory_bytes, service.policy.default_output_dir
                )
                if used >= service.byte_limit:
                    # Do not terminate unrelated processes or delete files to reclaim space.
                    for run_id in list(service.controller._children):

                        def request_stop(target: str = run_id) -> dict[str, Any]:
                            return service.call(
                                "queue_stop", {"run_id": target, "request_key": f"quota:{target}"}
                            )

                        await anyio.to_thread.run_sync(request_stop)
            except OSError:
                continue  # Actual engine writes still fail truthfully if storage disappears.

    async with anyio.create_task_group() as tasks:
        tasks.start_soon(monitor)
        try:
            await run_server(service)
        finally:
            tasks.cancel_scope.cancel()


if __name__ == "__main__":
    anyio.run(serve)
