"""Lifespan-owned MCP subprocesses; an HTTP disconnect never owns their lifetime."""

from __future__ import annotations

import json
import os
import sys
from typing import Any

import anyio
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from .registry import Registry


class Peer:
    def __init__(self, registry: Registry, name: str, proxy_url: str) -> None:
        self.registry, self.name, self.proxy_url = registry, name, proxy_url
        self.stop = anyio.Event()
        self.session: ClientSession | None = None
        self.error: str | None = None
        self.limiter = anyio.CapacityLimiter(8)

    async def run(self, *, task_status: Any = anyio.TASK_STATUS_IGNORED) -> None:
        root = self.registry.root(self.name)
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        output = root / "downloads"
        output.mkdir(exist_ok=True, mode=0o700)
        policy = root / "policy.json"
        policy.write_text(
            json.dumps({"default_output_dir": str(output), "output_roots": [str(output)]})
        )
        env = {
            key: value
            for key, value in os.environ.items()
            if key.upper()
            in {
                "PATH",
                "SYSTEMROOT",
                "WINDIR",
                "COMSPEC",
                "PATHEXT",
                "TEMP",
                "TMP",
                "LANG",
                "LC_ALL",
                "SSL_CERT_FILE",
                "SSL_CERT_DIR",
                "REQUESTS_CA_BUNDLE",
            }
        }
        env.update(
            PINAK_DATA_DIR=str(root / "state"),
            PINAK_MCP_CONFIG=str(policy),
            PINAK_CLOUD_STORAGE_BYTES=str(self.registry.settings.storage_bytes),
            PINAK_CLOUD_MAX_JOBS=str(self.registry.settings.max_jobs),
            PINAK_CLOUD_PROXY=self.proxy_url,
            HTTP_PROXY=self.proxy_url,
            HTTPS_PROXY=self.proxy_url,
            ALL_PROXY=self.proxy_url,
            http_proxy=self.proxy_url,
            https_proxy=self.proxy_url,
            all_proxy=self.proxy_url,
            NO_PROXY="",
            no_proxy="",
            HOME=str(root),
            USERPROFILE=str(root),
            XDG_CONFIG_HOME=str(root / "config"),
            XDG_CACHE_HOME=str(root / "cache"),
            XDG_STATE_HOME=str(root / "logs"),
            XDG_DATA_HOME=str(root / "data"),
            APPDATA=str(root / "config"),
            LOCALAPPDATA=str(root / "local"),
        )
        started = False
        try:
            params = StdioServerParameters(
                command=sys.executable,
                args=["-m", "pinak.mcp_cloud.tenant"],
                env=env,
                cwd=str(root),
            )
            # Runtime diagnostics rotate in the per-user data directory. Avoid
            # an unbounded second stderr log containing extractor error text.
            with open(os.devnull, "w", encoding="utf-8") as errors:
                async with (
                    stdio_client(params, errlog=errors) as (reader, writer),
                    ClientSession(reader, writer, read_timeout_seconds=30) as session,
                ):
                    await session.initialize()
                    self.session = session
                    task_status.started()
                    started = True
                    await self.stop.wait()
        except Exception:
            self.error = (
                "User adapter unavailable; inspect its operator log and reconcile saved jobs."
            )
            if not started:
                raise
        finally:
            self.session = None

    async def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        from ..mcp_server.tools import Tools

        if self.session is None:
            return Tools.failure(
                "ADAPTER_UNAVAILABLE", self.error or "User adapter is not running."
            )
        try:
            self.limiter.acquire_nowait()
        except anyio.WouldBlock:
            return Tools.failure(
                "SERVER_BUSY", "Eight calls are active for this user.", retryable=True
            )
        try:
            result = await self.session.call_tool(name, arguments)
            return result.structured_content or Tools.failure(
                "ADAPTER_ERROR", "Missing structured result."
            )
        except Exception:
            return Tools.failure(
                "ADAPTER_UNAVAILABLE",
                "Call interrupted; reconcile using the same request_key before retrying.",
            )
        finally:
            self.limiter.release()


class Pool:
    def __init__(self, registry: Registry, proxy_url: str) -> None:
        self.registry, self.proxy_url = registry, proxy_url
        self.peers: dict[str, Peer] = {}
        self.lock = anyio.Lock()
        self.tasks: Any = None
        self.closing = anyio.Event()

    async def get(self, name: str) -> Peer:
        async with self.lock:
            peer = self.peers.get(name)
            if peer is None or peer.session is None:
                peer = Peer(self.registry, name, self.proxy_url)
                await self.tasks.start(peer.run)
                self.peers[name] = peer
            return peer

    def close(self) -> None:
        self.closing.set()
        for peer in self.peers.values():
            peer.stop.set()

    async def watch_revocations(self) -> None:
        while not self.closing.is_set():
            with anyio.move_on_after(2):
                await self.closing.wait()
            if self.closing.is_set():
                return
            users = await anyio.to_thread.run_sync(self.registry.list_users)
            for user in users:
                if not user["enabled"]:
                    peer = self.peers.pop(str(user["name"]), None)
                    if peer:
                        peer.stop.set()
