"""Authenticated Streamable HTTP gateway over isolated persistent local adapters."""

from __future__ import annotations

import contextlib
import json
import time
from collections import deque
from contextvars import ContextVar
from typing import Any
from urllib.parse import urlsplit

import anyio
import mcp.types as types
from filelock import FileLock
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import Field, StrictInt, ValidationError
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Route
from starlette.types import Receive, Scope, Send

from .. import __version__
from ..mcp_server.models import PositiveID, StrictModel
from ..mcp_server.server import OUTPUT_SCHEMA
from ..mcp_server.tools import DEFINITIONS, Tools
from .egress import EgressProxy
from .peers import Pool
from .registry import Registry
from .settings import Settings

principal: ContextVar[str] = ContextVar("pinak_cloud_user")


class FileLink(StrictModel):
    job_id: PositiveID
    file_index: StrictInt = Field(default=1, ge=1)


def create_app(settings: Settings) -> Any:
    registry = Registry(settings)
    egress = EgressProxy()
    pool = Pool(registry, "")
    limits: dict[str, deque[float]] = {}

    async def list_tools(context: Any, params: Any) -> types.ListToolsResult:
        entries = dict(DEFINITIONS)
        entries["file_link"] = (
            FileLink,
            f"Issue a {settings.link_seconds}-second bearer download link for your completed file. Anyone with the link can use it until expiry.",
            False,
        )
        return types.ListToolsResult(
            tools=[
                types.Tool(
                    name=name,
                    description=description,
                    input_schema=model.model_json_schema(),
                    output_schema=OUTPUT_SCHEMA,
                    annotations=types.ToolAnnotations(
                        read_only_hint=readonly,
                        destructive_hint=name in {"queue_remove", "queue_clean_completed"},
                        idempotent_hint=name != "file_link",
                        open_world_hint=name == "queue_start",
                    ),
                )
                for name, (model, description, readonly) in entries.items()
            ]
        )

    async def invoke(context: Any, params: Any) -> types.CallToolResult:
        name = principal.get()
        try:
            peer = await pool.get(name)
            if params.name == "file_link":
                model = FileLink.model_validate(params.arguments or {})
                shown = await peer.call(
                    "queue_show", {"job_id": model.job_id, "cursor": model.file_index, "limit": 1}
                )
                if not shown["ok"]:
                    result = shown
                elif (
                    shown["data"]["status"] not in {"succeeded", "skipped"}
                    or not shown["data"]["files"]
                ):
                    result = Tools.failure("FILE_UNAVAILABLE", "No completed file at that index.")
                else:
                    from pathlib import Path

                    link = await anyio.to_thread.run_sync(
                        registry.issue_link, name, Path(shown["data"]["files"][0])
                    )
                    result = {"ok": True, "data": link, "warnings": []}
            else:
                result = await peer.call(params.name, params.arguments or {})
                if params.name == "server_info" and result["ok"]:
                    result["data"].update(
                        transport="streamable-http",
                        tools=[*DEFINITIONS, "file_link"],
                        deployment="user-operated",
                        cloud_user=name,
                        downloads_survive_client_disconnect=True,
                        storage_limit_bytes=settings.storage_bytes,
                        storage_limit_kind="soft",
                    )
        except ValidationError:
            result = Tools.failure("INVALID_ARGUMENT", "Invalid file-link arguments.")
        except (ValueError, OSError):
            result = Tools.failure(
                "FILE_UNAVAILABLE", "File is unavailable; inspect the job and operator diagnostics."
            )
        except Exception:
            result = Tools.failure(
                "ADAPTER_UNAVAILABLE", "User adapter unavailable; inspect operator diagnostics."
            )
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=json.dumps(result))],
            structured_content=result,
            is_error=not result["ok"],
        )

    server = Server(
        "Pinak-MCP-Cloud", version=__version__, on_list_tools=list_tools, on_call_tool=invoke
    )
    host = urlsplit(settings.public_url).netloc
    manager = StreamableHTTPSessionManager(
        server,
        stateless=True,
        json_response=True,
        security_settings=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=[host],
            allowed_origins=[settings.public_url],
        ),
        max_request_body_size=65536,
    )

    @contextlib.asynccontextmanager
    async def lifespan(app: Any) -> Any:
        # Multiple gateway workers would create multiple adapters for the same user.
        lock = FileLock(str(settings.data_dir / "gateway.lock"), timeout=0)
        with lock:
            await egress.start()
            pool.proxy_url = egress.url
            try:
                async with anyio.create_task_group() as tasks, manager.run():
                    pool.tasks = tasks
                    tasks.start_soon(pool.watch_revocations)
                    try:
                        yield
                    finally:
                        pool.close()
            finally:
                await egress.close()

    async def health(request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    async def download(request: Request) -> Any:
        path = await anyio.to_thread.run_sync(registry.resolve_link, request.path_params["token"])
        if path is None:
            return JSONResponse({"error": "File link invalid or expired"}, status_code=404)
        return FileResponse(
            path,
            filename=path.name,
            headers={
                "Cache-Control": "no-store",
                "Referrer-Policy": "no-referrer",
                "X-Content-Type-Options": "nosniff",
            },
        )

    routes = Starlette(
        routes=[
            Route("/healthz", health),
            Route("/files/{token}", download, methods=["GET", "HEAD"]),
        ],
        lifespan=lifespan,
    )

    class Gateway:
        async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
            if scope["type"] != "http":
                await routes(scope, receive, send)
                return
            headers = dict(scope["headers"])
            if scope["path"] != "/healthz" and (
                headers.get(b"host", b"").decode("latin-1") != host
                or (
                    b"origin" in headers
                    and headers[b"origin"].decode("latin-1") != settings.public_url
                )
            ):
                await JSONResponse({"error": "Host or Origin denied"}, status_code=403)(
                    scope, receive, send
                )
                return
            if scope["path"] == "/mcp":
                auth = headers.get(b"authorization", b"").decode("latin-1")
                token = auth[7:] if auth.lower().startswith("bearer ") else ""
                user = await anyio.to_thread.run_sync(registry.authenticate, token)
                if user is None:
                    await JSONResponse(
                        {"error": "Bearer token required"},
                        status_code=401,
                        headers={"WWW-Authenticate": 'Bearer realm="pinak-cloud"'},
                    )(scope, receive, send)
                    return
                window = limits.setdefault(user, deque())
                now = time.monotonic()
                while window and window[0] <= now - 60:
                    window.popleft()
                if len(window) >= settings.calls_per_minute:
                    await JSONResponse(
                        {"error": "Rate limit"}, status_code=429, headers={"Retry-After": "60"}
                    )(scope, receive, send)
                    return
                window.append(now)
                marker = principal.set(user)
                try:
                    await manager.handle_request(scope, receive, send)
                finally:
                    principal.reset(marker)
            else:
                await routes(scope, receive, send)

    return Gateway()
