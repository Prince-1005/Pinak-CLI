"""Real process shutdown, orphan recovery, and owned descendant cleanup."""

import contextlib
import json
import os
import subprocess
import sys
import threading
import time
import uuid
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO

import psutil
import pytest

from pinak import history
from pinak import queue as core
from pinak.mcp_server.models import Policy
from pinak.mcp_server.tools import Tools
from pinak.mcp_server.worker_controller import terminate_owned, verified_process

pytest.importorskip("mcp")


def wait_for(predicate, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.03)
    pytest.fail("Timed out waiting for process lifecycle condition")


def exited(pid):
    try:
        return psutil.Process(pid).status() == psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return True


@pytest.fixture
def slow_url():
    buffer = BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setparams((1, 2, 8000, 0, "NONE", "not compressed"))
        audio.writeframes(b"\x00\x01" * 512000)
    payload = buffer.getvalue()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            with contextlib.suppress(OSError, ConnectionError):
                for offset in range(0, len(payload), 8192):
                    self.wfile.write(payload[offset : offset + 8192])
                    self.wfile.flush()
                    time.sleep(0.08)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}/slow.wav"
    server.shutdown()
    server.server_close()


def policy(tmp_path):
    return Policy(
        default_output_dir=tmp_path / "output",
        shutdown_grace_seconds=2,
        parent_heartbeat_seconds=0.1,
        orphan_threshold_seconds=2,
    )


def test_stop_requeues_active_and_does_not_claim_new_jobs(isolated_history_db, tmp_path, slow_url):
    tools = Tools(policy(tmp_path))
    other = Tools(policy(tmp_path))
    try:
        job_id = tools.call("queue_add", {"url": slow_url, "request_key": "add"})["data"]["job_id"]
        run = tools.call("queue_start", {"request_key": "run"})
        assert run["ok"], run
        run_id = run["data"]["run_id"]
        wait_for(lambda: core.get_job(job_id).status == "running")
        next_id = tools.call(
            "queue_add", {"url": slow_url, "options": {"force": True}, "request_key": "later"}
        )["data"]["job_id"]
        denial = other.call("queue_stop", {"run_id": run_id, "request_key": "stop"})
        assert denial["error"]["code"] == "RUN_NOT_OWNED"
        result = tools.call("queue_stop", {"run_id": run_id, "request_key": "stop"})
        assert result["ok"]
        wait_for(
            lambda: (
                tools.controller.status(run_id)["state"] not in {"starting", "running", "stopping"}
            )
        )
        tools.close()
        assert core.get_job(job_id).status == "queued"
        assert core.get_job(next_id).attempts == 0
        assert tools.controller.status(run_id)["state"] == "interrupted"
    finally:
        tools.close()
        other.close()


def test_parent_eof_stops_actual_worker(isolated_history_db, tmp_path, slow_url):
    tools = Tools(policy(tmp_path))
    try:
        job_id = tools.call("queue_add", {"url": slow_url, "request_key": "add"})["data"]["job_id"]
        run_id = tools.call("queue_start", {"request_key": "run"})["data"]["run_id"]
        wait_for(lambda: core.get_job(job_id).status == "running")
        process, _ = tools.controller._children[run_id]
        tools.close()
        assert process.poll() is not None
        assert core.get_job(job_id).status == "queued"
    finally:
        tools.close()


def test_worker_kill_requires_lock_safe_recovery(
    isolated_history_db, tmp_path, slow_url, monkeypatch
):
    tools = Tools(policy(tmp_path))
    try:
        job_id = tools.call("queue_add", {"url": slow_url, "request_key": "add"})["data"]["job_id"]
        run_id = tools.call("queue_start", {"request_key": "run"})["data"]["run_id"]
        wait_for(lambda: core.get_job(job_id).status == "running")
        process, started = tools.controller._children[run_id]
        assert verified_process(process.pid, started + 100, run_id) is None
        actual = tools.store.run(run_id)
        terminate_owned(actual["pid"], actual["process_started"], run_id)
        process.wait(timeout=5)
        # Windows can expose a dead PID until every handle is released. The
        # controller's owned Popen exit result must still reconcile the run.
        with monkeypatch.context() as patch:
            patch.setattr(psutil, "pid_exists", lambda _pid: True)
            observed = tools.controller.status(run_id)
            assert observed["state"] == "interrupted", observed
        # Inspection does not race to requeue a still-writing worker.
        assert core.get_job(job_id).status == "running"
        core.run_queue([], limit=1)
        assert core.get_job(job_id).status == "queued"
    finally:
        tools.close()


def test_watchdog_kills_hung_owned_descendant(isolated_history_db, tmp_path):
    tools = Tools(policy(tmp_path))
    run_id = uuid.uuid4().hex
    owner = tools.controller.owner
    with tools.store.connect() as conn, conn:
        conn.execute(
            "INSERT INTO mcp_runs(run_id,owner,targets_json,state,created_at,updated_at) VALUES(?,?,'[]','starting',?,?)",
            (run_id, owner, time.time(), time.time()),
        )
    pid_file = tmp_path / "child.json"
    script = """
import json, pathlib, subprocess, sys, time
from pinak.mcp_server import worker
pid_file = sys.argv[1]
def hang(*args, **kwargs):
    kwargs['on_ready']()
    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
    pathlib.Path(pid_file).write_text(json.dumps({'pid':child.pid}))
    child.wait()
worker.core.run_queue = hang
sys.argv = ['worker', *sys.argv[2:]]
raise SystemExit(worker.main())
"""
    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            script,
            str(pid_file),
            "--run-id",
            run_id,
            "--owner",
            owner,
            "--db",
            history.DB_FILE,
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=os.name != "nt",
    )
    try:
        process.stdin.write(json.dumps({"policy": policy(tmp_path).model_dump(mode="json")}) + "\n")
        process.stdin.flush()
        wait_for(lambda: pid_file.exists())
        child_pid = json.loads(pid_file.read_text())["pid"]
        process.stdin.close()
        process.wait(timeout=8)
        wait_for(lambda: exited(child_pid))
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        process.stderr.close()
        tools.close()


def test_force_killed_adapter_does_not_leave_download_worker(
    isolated_history_db, tmp_path, slow_url
):
    settings = policy(tmp_path)
    script = """
import json, os, sys, time
from pinak import history
from pinak.mcp_server.models import Policy
from pinak.mcp_server.tools import Tools
history.DB_FILE = sys.argv[1]
tools = Tools(Policy.model_validate_json(sys.argv[2]))
added = tools.call('queue_add', {'url':sys.argv[3], 'request_key':'add'})
run = tools.call('queue_start', {'request_key':'run'})
run_id = run['data']['run_id']
process, started = tools.controller._children[run_id]
print(json.dumps({'pid':tools.store.run(run_id)['pid'],'adapter_pid':os.getpid(),'job_id':added['data']['job_id']}), flush=True)
time.sleep(60)
"""
    adapter = subprocess.Popen(
        [sys.executable, "-c", script, isolated_history_db, settings.model_dump_json(), slow_url],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        details = json.loads(adapter.stdout.readline())
        wait_for(lambda: core.get_job(details["job_id"]).status == "running")
        psutil.Process(details["adapter_pid"]).kill()
        adapter.wait(timeout=5)
        wait_for(lambda: exited(details["pid"]))
        assert core.get_job(details["job_id"]).status == "queued"
        assert core.get_job(details["job_id"]).attempts == 1
    finally:
        if adapter.poll() is None:
            adapter.kill()
            adapter.wait(timeout=5)
        adapter.stdout.close()
        adapter.stderr.close()
