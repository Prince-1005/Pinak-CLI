"""Actual official SDK client/server exchange over subprocess stdio."""

import json
import os
import sqlite3
import sys

import pytest

mcp = pytest.importorskip("mcp")
anyio = pytest.importorskip("anyio")
ClientSession = mcp.ClientSession
stdio = pytest.importorskip("mcp.client.stdio")
StdioServerParameters, stdio_client = stdio.StdioServerParameters, stdio.stdio_client


def test_real_stdio_discovery_calls_and_clean_exit(tmp_path):
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"default_output_dir": str(tmp_path / "downloads")}))
    env = {**os.environ, "PINAK_MCP_CONFIG": str(policy), "PINAK_DATA_DIR": str(tmp_path / "data")}

    async def exercise():
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "pinak.mcp_server", "serve"],
            env=env,
            cwd=str(tmp_path),
        )
        with (tmp_path / "stderr.log").open("w", encoding="utf-8") as errors:
            async with (
                stdio_client(params, errlog=errors) as (read, write),
                ClientSession(read, write, read_timeout_seconds=15) as session,
            ):
                initialization = await session.initialize()
                assert initialization.server_info.name == "Pinak-MCP"
                tools = await session.list_tools()
                names = {tool.name for tool in tools.tools}
                assert {
                    "queue_add",
                    "queue_start",
                    "queue_stop",
                    "queue_run_status",
                    "media_info",
                    "diagnostics",
                } <= names
                added = await session.call_tool(
                    "queue_add",
                    {"url": "https://example.com/video?token=secret", "request_key": "add"},
                )
                assert not added.is_error
                assert added.structured_content["ok"]
                assert "secret" not in str(added.structured_content)
                job_id = added.structured_content["data"]["job_id"]
                shown = await session.call_tool("queue_show", {"job_id": job_id})
                assert shown.structured_content["data"]["status"] == "queued"
                invalid = await session.call_tool(
                    "queue_remove", {"job_ids": [-1], "request_key": "bad"}
                )
                assert (
                    invalid.is_error
                    and invalid.structured_content["error"]["code"] == "INVALID_ARGUMENT"
                )
                removed = await session.call_tool(
                    "queue_remove", {"job_ids": [job_id], "request_key": "remove"}
                )
                assert removed.structured_content["data"]["files_kept"]
                repeated = await session.call_tool(
                    "queue_remove", {"job_ids": [job_id], "request_key": "remove"}
                )
                assert repeated.structured_content == removed.structured_content

    anyio.run(exercise)
    with sqlite3.connect(tmp_path / "data" / "history.db") as conn:
        assert conn.execute("SELECT count(*) FROM queue_jobs").fetchone()[0] == 0
    assert "secret" not in (tmp_path / "stderr.log").read_text()


def test_concurrent_calls_reject_overload_without_unbounded_waiters(tmp_path):
    env = {**os.environ, "PINAK_DATA_DIR": str(tmp_path / "data")}
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"default_output_dir": str(tmp_path / "downloads")}))
    env["PINAK_MCP_CONFIG"] = str(policy)
    script = """
import time
from pinak.mcp_server.tools import Tools
from pinak.mcp_server.server import serve_stdio
original = Tools.server_info
def slow(self, model):
    time.sleep(1)
    return original(self, model)
Tools.server_info = slow
serve_stdio()
"""

    async def exercise():
        params = StdioServerParameters(
            command=sys.executable, args=["-c", script], env=env, cwd=str(tmp_path)
        )
        results = []
        async with (
            stdio_client(params) as (read, write),
            ClientSession(read, write, read_timeout_seconds=15) as session,
        ):
            await session.initialize()

            async def call():
                results.append((await session.call_tool("server_info", {})).structured_content)

            async with anyio.create_task_group() as group:
                for _ in range(20):
                    group.start_soon(call)
            assert sum(result["ok"] for result in results) == 8
            rejected = [result for result in results if not result["ok"]]
            assert len(rejected) == 12
            assert all(result["error"]["code"] == "SERVER_BUSY" for result in rejected)
            assert not (await session.call_tool("server_info", {})).is_error

    anyio.run(exercise)


def test_cancelled_request_can_reconcile_committed_mutation(tmp_path):
    env = {**os.environ, "PINAK_DATA_DIR": str(tmp_path / "data")}
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"default_output_dir": str(tmp_path / "downloads")}))
    env["PINAK_MCP_CONFIG"] = str(policy)
    script = """
import time
from pinak.mcp_server.tools import Tools
from pinak.mcp_server.server import serve_stdio
original = Tools.queue_add
def delayed(self, model):
    time.sleep(0.5)
    return original(self, model)
Tools.queue_add = delayed
serve_stdio()
"""

    async def exercise():
        params = StdioServerParameters(
            command=sys.executable, args=["-c", script], env=env, cwd=str(tmp_path)
        )
        async with (
            stdio_client(params) as (read, write),
            ClientSession(read, write, read_timeout_seconds=15) as session,
        ):
            await session.initialize()
            arguments = {
                "url": "https://example.com/video",
                "options": {"force": True},
                "request_key": "cancelled-response",
            }
            with anyio.move_on_after(0.1) as scope:
                await session.call_tool("queue_add", arguments)
            assert scope.cancel_called
            await anyio.sleep(0.7)
            repeated = await session.call_tool("queue_add", arguments)
            assert not repeated.is_error
            jobs = await session.call_tool("queue_list", {})
            assert len(jobs.structured_content["data"]["items"]) == 1

    anyio.run(exercise)
