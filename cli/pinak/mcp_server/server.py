"""Official SDK stdio transport with explicit flat tool contracts."""

from __future__ import annotations

import contextlib
import json
import logging
import sys
from typing import Any

import anyio
import mcp.types as types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

from .. import __version__
from . import SERVER_NAME
from .models import load_policy
from .tools import DEFINITIONS, Tools

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "ok": {"type": "boolean"},
        "data": {"type": "object"},
        "warnings": {"type": "array", "items": {"type": "string"}},
        "request_key": {"type": "string"},
        "error": {"type": "object"},
    },
    "required": ["ok"],
    "additionalProperties": False,
    "allOf": [
        {
            "if": {"properties": {"ok": {"const": True}}},
            "then": {"required": ["data"]},
            "else": {"required": ["error"]},
        }
    ],
}


async def run_server(service: Tools) -> None:
    limiter = anyio.CapacityLimiter(8)

    async def list_tools(context: Any, params: Any) -> types.ListToolsResult:
        return types.ListToolsResult(
            tools=[
                types.Tool(
                    name=name,
                    description=description,
                    input_schema=model.model_json_schema(),
                    output_schema=OUTPUT_SCHEMA,
                    annotations=types.ToolAnnotations(
                        read_only_hint=read_only,
                        destructive_hint=name in {"queue_remove", "queue_clean_completed"},
                        idempotent_hint=True,
                        open_world_hint=name == "queue_start",
                    ),
                )
                for name, (model, description, read_only) in DEFINITIONS.items()
            ]
        )

    async def call_tool(context: Any, params: types.CallToolRequestParams) -> types.CallToolResult:
        try:
            limiter.acquire_nowait()
        except anyio.WouldBlock:
            result = Tools.failure(
                "SERVER_BUSY",
                "Eight local calls are already active.",
                "Retry after an outstanding call finishes; no mutation was accepted.",
                True,
            )
        else:
            try:
                result = await anyio.to_thread.run_sync(
                    lambda: service.call(params.name, params.arguments or {})
                )
            except Exception as exc:
                logging.getLogger("pinak.mcp").error(
                    "Tool %s failed with %s", params.name, type(exc).__name__
                )
                result = Tools.failure(
                    "INTERNAL_ERROR",
                    "The local operation failed unexpectedly.",
                    "Inspect local diagnostics; reconcile mutations by request_key before retrying.",
                )
            finally:
                limiter.release()
        text = json.dumps(result, ensure_ascii=False, allow_nan=False)
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=text)],
            structured_content=result,
            is_error=not result["ok"],
        )

    server = Server(
        SERVER_NAME, version=__version__, on_list_tools=list_tools, on_call_tool=call_tool
    )
    try:
        async with stdio_server() as (reader, writer):
            await server.run(reader, writer, server.create_initialization_options())
    finally:
        with anyio.CancelScope(shield=True):
            await anyio.to_thread.run_sync(service.close)


def serve_stdio() -> None:
    from .setup import configure_logging, load_core_settings

    # Even optional legacy initialization must not write onto the protocol wire.
    with contextlib.redirect_stdout(sys.stderr):
        configure_logging()
        load_core_settings()
        service = Tools(load_policy())
    anyio.run(run_server, service)
