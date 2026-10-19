"""Actual SDK protocol calls start a local download and optional audio conversion."""

import json
import os
import sys
import threading
import time
import wave
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from pinak.utils import ffmpeg_available

mcp = pytest.importorskip("mcp")
anyio = pytest.importorskip("anyio")
stdio = pytest.importorskip("mcp.client.stdio")


@pytest.mark.parametrize("audio", [False, True])
def test_download_through_real_mcp_session(tmp_path, audio):
    if audio and not ffmpeg_available():
        pytest.skip("Actual audio transcoding requires FFmpeg")
    source = tmp_path / "source"
    source.mkdir()
    with wave.open(str(source / "sample.wav"), "wb") as media:
        media.setparams((1, 2, 8000, 0, "NONE", "not compressed"))
        media.writeframes(b"\x00\x01" * 8000)

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(source), **kwargs)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    output = tmp_path / "output"
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"default_output_dir": str(output)}))
    env = {**os.environ, "PINAK_MCP_CONFIG": str(policy), "PINAK_DATA_DIR": str(tmp_path / "data")}

    async def exercise():
        params = stdio.StdioServerParameters(
            command=sys.executable,
            args=["-m", "pinak.mcp_server", "serve"],
            env=env,
            cwd=str(tmp_path),
        )
        async with (
            stdio.stdio_client(params) as (reader, writer),
            mcp.ClientSession(reader, writer, read_timeout_seconds=15) as session,
        ):
            await session.initialize()
            added = await session.call_tool(
                "queue_add",
                {
                    "url": f"http://127.0.0.1:{server.server_port}/sample.wav",
                    "options": {"audio": audio},
                    "request_key": "add",
                },
            )
            assert not added.is_error, added
            job_id = added.structured_content["data"]["job_id"]
            started = await session.call_tool("queue_start", {"request_key": "start"})
            assert not started.is_error, started
            run_id = started.structured_content["data"]["run_id"]
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                info = await session.call_tool("server_info", {})
                assert info.structured_content["data"]["name"] == "Pinak-MCP"
                status = await session.call_tool("queue_run_status", {"run_id": run_id})
                state = status.structured_content["data"]
                if state["state"] not in {"starting", "running", "stopping"}:
                    break
                await anyio.sleep(0.05)
            else:
                pytest.fail("Protocol-initiated download did not finish")
            assert state["state"] == "completed", state
            assert state["summary"]["succeeded"] == 1, state
            shown = (await session.call_tool("queue_show", {"job_id": job_id})).structured_content[
                "data"
            ]
            assert shown["status"] == "succeeded"
            downloaded = Path(shown["files"][0])
            assert downloaded.is_relative_to(output) and downloaded.stat().st_size > 0
            if audio:
                assert downloaded.suffix == ".mp3"
            else:
                with wave.open(str(downloaded), "rb") as media:
                    assert media.readframes(8000) == b"\x00\x01" * 8000
            media_info = await session.call_tool("media_info", {"path": str(downloaded)})
            assert not media_info.is_error, media_info
            assert media_info.structured_content["data"]["duration_seconds"] == pytest.approx(
                1, abs=0.3
            )
            log = (await session.call_tool("history_list", {})).structured_content["data"]
            assert len(log["items"]) == 1 and log["items"][0]["status"] == "success"
            removed = await session.call_tool("queue_clean_completed", {"request_key": "clean"})
            assert removed.structured_content["data"]["removed_count"] == 1
            assert downloaded.exists()

    try:
        anyio.run(exercise)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
