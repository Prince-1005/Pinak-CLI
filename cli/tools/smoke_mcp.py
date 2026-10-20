"""Exercise an installed MCP extra through real stdio and a local WAV download."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
import wave
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import anyio
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="pinak-mcp-smoke-") as temporary:
        root = Path(temporary).resolve()
        source = root / "source"
        source.mkdir()
        with wave.open(str(source / "sample.wav"), "wb") as audio:
            audio.setparams((1, 2, 8000, 0, "NONE", "not compressed"))
            audio.writeframes(b"\x00\x01" * 8000)
        policy = root / "policy.json"
        policy.write_text(json.dumps({"default_output_dir": str(root / "output")}))
        env = {
            key: value
            for key, value in os.environ.items()
            if key != "PYTHONPATH" and not key.startswith("PINAK_")
        }
        env.update(PINAK_DATA_DIR=str(root / "data"), PINAK_MCP_CONFIG=str(policy))

        class Handler(SimpleHTTPRequestHandler):
            def __init__(self, *args: object, **kwargs: object) -> None:
                super().__init__(*args, directory=str(source), **kwargs)

            def log_message(self, *_args: object) -> None:
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        async def exercise() -> None:
            params = StdioServerParameters(
                command=sys.executable,
                args=["-m", "pinak.mcp_server", "serve"],
                env=env,
                cwd=str(root),
            )
            async with (
                stdio_client(params) as (reader, writer),
                ClientSession(reader, writer, read_timeout_seconds=15) as session,
            ):
                initialized = await session.initialize()
                assert initialized.server_info.name == "Pinak-MCP"
                tools = await session.list_tools()
                names = {tool.name for tool in tools.tools}
                assert len(names) == 33
                assert {"history_show", "library_scan", "library_show"} <= names
                added = await session.call_tool(
                    "queue_add",
                    {
                        "url": f"http://127.0.0.1:{server.server_port}/sample.wav",
                        "request_key": "add",
                    },
                )
                assert not added.is_error, added
                job_id = added.structured_content["data"]["job_id"]
                started = await session.call_tool("queue_start", {"request_key": "run"})
                assert not started.is_error, started
                run_id = started.structured_content["data"]["run_id"]
                deadline = time.monotonic() + 40
                while time.monotonic() < deadline:
                    status = await session.call_tool("queue_run_status", {"run_id": run_id})
                    state = status.structured_content["data"]
                    if state["state"] not in {"starting", "running", "stopping"}:
                        break
                    await anyio.sleep(0.05)
                else:
                    raise RuntimeError("Installed wheel worker timed out")
                assert state["summary"]["succeeded"] == 1, state
                shown = await session.call_tool("queue_show", {"job_id": job_id})
                saved = Path(shown.structured_content["data"]["files"][0])
                assert saved.is_file() and saved.is_relative_to(root / "output")
                with wave.open(str(saved), "rb") as audio:
                    assert audio.readframes(8000) == b"\x00\x01" * 8000
                records = await session.call_tool("history_list", {})
                assert len(records.structured_content["data"]["items"]) == 1

        try:
            anyio.run(exercise)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
    print("Installed MCP stdio discovery, actual download, PCM, queue and history passed")


if __name__ == "__main__":
    main()
