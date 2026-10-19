"""Real worker processes share queue/history and honor the existing runner lock."""

import contextlib
import threading
import time
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path

import pytest
from filelock import FileLock

from pinak import history
from pinak import queue as core
from pinak.mcp_server.models import Policy
from pinak.mcp_server.tools import Tools

pytest.importorskip("mcp")


@pytest.fixture
def download_server():
    buffer = BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setparams((1, 2, 8000, 0, "NONE", "not compressed"))
        audio.writeframes(b"\x00\x01" * 8000)
    payload = buffer.getvalue()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            with contextlib.suppress(ConnectionError, OSError):
                self.wfile.write(payload)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/sample.wav", payload
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def await_terminal(tools, run_id, timeout=25):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = tools.call("queue_run_status", {"run_id": run_id})
        assert status["ok"], status
        if status["data"]["state"] not in {"starting", "running", "stopping"}:
            return status["data"]
        time.sleep(0.05)
    pytest.fail(f"Worker did not finish: {status}")


def test_real_worker_download_and_replay(isolated_history_db, tmp_path, download_server):
    tools = Tools(Policy(default_output_dir=tmp_path / "output"))
    url, payload = download_server
    try:
        job_id = tools.call("queue_add", {"url": url, "request_key": "add"})["data"]["job_id"]
        result = tools.call("queue_start", {"request_key": "run"})
        assert result["ok"], result
        run_id = result["data"]["run_id"]
        state = await_terminal(tools, run_id)
        assert state["state"] == "completed", state
        job = core.get_job(job_id)
        assert job.status == "succeeded", job.last_error
        assert len(job.files) == 1
        with wave.open(str(Path(job.files[0])), "rb") as audio:
            assert audio.readframes(8000) == b"\x00\x01" * 8000
        assert len(history.get_history()) == 1
        replay = tools.call("queue_start", {"request_key": "run"})
        assert replay["data"]["run_id"] == run_id
        assert core.get_job(job_id).attempts == 1
    finally:
        tools.close()


def test_cli_runner_lock_is_not_stolen(isolated_history_db, tmp_path):
    tools = Tools(Policy(default_output_dir=tmp_path))
    try:
        with FileLock(history.DB_FILE + ".queue-run.lock"):
            result = tools.call("queue_start", {"request_key": "run"})
            assert result["error"]["code"] == "RUNNER_BUSY"
    finally:
        tools.close()


def test_empty_run_does_not_spawn_worker(isolated_history_db, tmp_path):
    tools = Tools(Policy(default_output_dir=tmp_path))
    try:
        assert tools.call("queue_start", {"request_key": "run"})["data"]["state"] == "no_work"
        assert not tools.controller._children
    finally:
        tools.close()
