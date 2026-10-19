"""Own local worker processes without blocking the MCP protocol loop."""

from __future__ import annotations

import contextlib
import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import psutil
from filelock import FileLock, Timeout

from .. import history
from .. import queue as core
from .models import Policy, Start, Stop
from .policy import ToolFailure, output_path
from .store import ACTIVE_RUNS, Store


def verified_process(pid: int | None, started: float | None, run_id: str) -> psutil.Process | None:
    if not pid or not started:
        return None
    try:
        process = psutil.Process(pid)
        if abs(process.create_time() - started) > 0.01 or run_id not in process.cmdline():
            return None
        return process if process.is_running() else None
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return None


def terminate_owned(pid: int, started: float, run_id: str) -> None:
    process = verified_process(pid, started, run_id)
    if process is None:
        return
    if sys.platform != "win32":
        import signal

        # Each worker is launched into a dedicated session/process group.
        with contextlib.suppress(ProcessLookupError):
            if os.getpgid(pid) != pid:
                raise RuntimeError("Worker process group ownership could not be verified")
            os.killpg(pid, signal.SIGKILL)
    else:
        # The worker owns a KILL_ON_JOB_CLOSE Job Object; killing that verified
        # root closes the job and the kernel terminates all its descendants.
        process.kill()


def process_exited(pid: int | None, started: float | None) -> bool:
    """Check the actual worker, including Windows' retained exited process IDs."""
    if not pid or not started:
        return False
    try:
        process = psutil.Process(pid)
        if abs(process.create_time() - started) > 0.01:
            return True  # that identity is gone; never signal the reused PID
        process.wait(timeout=0)
        return True
    except psutil.NoSuchProcess:
        return True
    except (psutil.TimeoutExpired, psutil.AccessDenied):
        return False


class WorkerController:
    def __init__(self, store: Store, policy: Policy) -> None:
        self.store, self.policy = store, policy
        self.owner = uuid.uuid4().hex
        self._children: dict[str, tuple[subprocess.Popen[str], float]] = {}
        self._identities: dict[str, tuple[int, float]] = {}
        self._mutex = threading.RLock()
        self._closed = threading.Event()
        self._heartbeat: threading.Thread | None = None

    def _send_heartbeats(self) -> None:
        while not self._closed.wait(self.policy.parent_heartbeat_seconds):
            with self._mutex:
                children = list(self._children.items())
            for run_id, (process, _) in children:
                if process.poll() is None and process.stdin and not process.stdin.closed:
                    with contextlib.suppress(OSError, ValueError):
                        process.stdin.write("ping\n")
                        process.stdin.flush()
                elif process.poll() is not None:
                    # A Windows venv redirector can exit before its actual Python
                    # worker. Close its pipe, but retain ownership until that
                    # worker has also exited.
                    with contextlib.suppress(OSError):
                        if process.stdin:
                            process.stdin.close()
                    try:
                        row = self.store.run(run_id)
                        if row["state"] in ACTIVE_RUNS and not process_exited(
                            row["pid"], row["process_started"]
                        ):
                            continue
                        self._record_exit(run_id)
                    except (sqlite3.Error, ToolFailure):
                        continue  # retain the definitive process handle for retry
                    with contextlib.suppress(OSError):
                        if process.stdin:
                            process.stdin.close()
                    with self._mutex:
                        self._children.pop(run_id, None)
                        self._identities.pop(run_id, None)

    def _record_exit(self, run_id: str) -> None:
        with self.store.connect() as conn, conn:
            conn.execute(
                "UPDATE mcp_runs SET state='interrupted',updated_at=?,last_error='Worker exited; unfinished jobs can be resumed' WHERE run_id=? AND state IN ('starting','running','stopping')",
                (time.time(), run_id),
            )

    def start(self, model: Start) -> dict[str, Any]:
        if self._closed.is_set():
            raise ToolFailure("SHUTTING_DOWN", "This MCP session is shutting down.")
        try:
            with FileLock(history.DB_FILE + ".mcp-start.lock", timeout=1):
                return self._start_locked(model)
        except Timeout as exc:
            raise ToolFailure(
                "RUNNER_BUSY", "Another worker start is in progress.", retryable=True
            ) from exc

    def _start_locked(self, model: Start) -> dict[str, Any]:
        def prepare(conn: Any) -> dict[str, Any]:
            # Lock remains authoritative. Do not recover stale jobs during inspection.
            try:
                with FileLock(history.DB_FILE + ".queue-run.lock", timeout=0):
                    pass
            except Timeout as exc:
                raise ToolFailure(
                    "RUNNER_BUSY",
                    "A CLI or MCP queue runner already owns the download lock.",
                    retryable=True,
                ) from exc
            for row in conn.execute(
                "SELECT * FROM mcp_runs WHERE state IN ('starting','running','stopping')"
            ).fetchall():
                if verified_process(row["pid"], row["process_started"], row["run_id"]) or (
                    row["pid"] is None
                    and time.time() - row["created_at"] < self.policy.orphan_threshold_seconds
                ):
                    raise ToolFailure(
                        "RUNNER_BUSY",
                        "An earlier local run is starting or stopping.",
                        retryable=True,
                    )
                conn.execute(
                    "UPDATE mcp_runs SET state='interrupted',updated_at=?,last_error='Worker no longer exists' WHERE run_id=?",
                    (time.time(), row["run_id"]),
                )
            if model.job_ids:
                rows = [core._find_job(conn, job_id) for job_id in dict.fromkeys(model.job_ids)]
                if any(row["status"] not in {"queued", "running"} for row in rows):
                    raise ToolFailure(
                        "JOB_NOT_QUEUED",
                        "Selected jobs must be queued or recoverable interrupted work.",
                    )
                rows.sort(key=lambda row: row["id"])
                rows = rows[: model.max_jobs]
            else:
                rows = conn.execute(
                    "SELECT * FROM queue_jobs WHERE status IN ('queued','running') ORDER BY id LIMIT ?",
                    (model.max_jobs,),
                ).fetchall()
            for row in rows:
                output_path(core._row_job(row).request.output_dir, self.policy)
            if not rows:
                return {"run_id": None, "state": "no_work", "selected_count": 0}
            run_id = uuid.uuid4().hex
            targets = [row["id"] for row in rows]
            now = time.time()
            conn.execute(
                "INSERT INTO mcp_runs(run_id,owner,targets_json,state,created_at,updated_at) VALUES(?,?,?,'starting',?,?)",
                (run_id, self.owner, json.dumps(targets), now, now),
            )
            return {"run_id": run_id, "state": "starting", "selected_count": len(targets)}

        answer = self.store.mutate("queue_start", model.request_key, model.model_dump(), prepare)
        run_id = answer["run_id"]
        if run_id is None:
            return answer
        run = self.store.run(run_id)
        with self._mutex:
            if self._closed.is_set():
                if run["owner"] == self.owner and run["state"] == "starting" and run["pid"] is None:
                    self.store.update_run(
                        run_id,
                        state="interrupted",
                        last_error="MCP session closed before worker launch",
                    )
                raise ToolFailure("SHUTTING_DOWN", "This MCP session closed before worker launch.")
            if (
                run["owner"] == self.owner
                and run["state"] == "starting"
                and run["pid"] is None
                and run_id not in self._children
            ):
                process = None
                try:
                    process = subprocess.Popen(  # nosec B603: fixed interpreter/module, trusted local DB and opaque IDs
                        [
                            sys.executable,
                            "-m",
                            "pinak.mcp_server.worker",
                            "--run-id",
                            run_id,
                            "--owner",
                            self.owner,
                            "--db",
                            history.DB_FILE,
                        ],
                        stdin=subprocess.PIPE,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        text=True,
                        encoding="utf-8",
                        cwd=Path.home(),
                        start_new_session=os.name != "nt",
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                    started = psutil.Process(process.pid).create_time()
                    self._children[run_id] = (process, started)
                    self._identities[run_id] = (process.pid, started)
                    self.store.update_run(run_id, pid=process.pid, process_started=started)
                    assert process.stdin is not None
                    process.stdin.write(
                        json.dumps(
                            {
                                "policy": self.policy.model_dump(mode="json"),
                                "history_enabled": history.history_enabled(),
                            }
                        )
                        + "\n"
                    )
                    process.stdin.flush()
                    if self._heartbeat is None:
                        self._heartbeat = threading.Thread(
                            target=self._send_heartbeats, daemon=True, name="pinak-parent-heartbeat"
                        )
                        self._heartbeat.start()
                except Exception as exc:
                    # A failure after Popen but before its first payload must not
                    # leave an untracked child waiting forever for policy input.
                    self._children.pop(run_id, None)
                    self._identities.pop(run_id, None)
                    if process is not None:
                        if process.stdin:
                            with contextlib.suppress(OSError):
                                process.stdin.close()
                        try:
                            process.wait(timeout=2)
                        except subprocess.TimeoutExpired:
                            process.kill()  # owned Popen handle; no PID lookup
                            process.wait(timeout=2)
                    with contextlib.suppress(sqlite3.Error):
                        self.store.update_run(
                            run_id, state="failed", last_error="Worker could not be launched"
                        )
                    raise ToolFailure(
                        "WORKER_START_FAILED",
                        "Worker could not be launched.",
                        "Check interpreter installation and local permissions.",
                    ) from exc
        deadline = time.monotonic() + 1.5
        while time.monotonic() < deadline:
            run = self.store.run(run_id)
            if run["pid"] and run["process_started"]:
                with self._mutex:
                    if run_id in self._children:
                        self._identities[run_id] = (run["pid"], run["process_started"])
            if run["state"] != "starting":
                break
            child = self._children.get(run_id)
            if child and child[0].poll() is not None:
                self.store.update_run(
                    run_id, state="failed", last_error="Worker exited before readiness"
                )
                break
            time.sleep(0.02)
        status = self.status(run_id)
        return {**answer, "state": status["state"], "last_error": status["last_error"]}

    def status(self, run_id: str) -> dict[str, Any]:
        with self._mutex:
            # The reaper commits exit before dropping the handle under this
            # mutex. Read both together so a stale DB snapshot cannot race the
            # definitive handle being removed.
            row = self.store.run(run_id)
            child = self._children.get(run_id)
            if child and row["pid"] and row["process_started"]:
                self._identities[run_id] = (row["pid"], row["process_started"])
            known_exited = bool(
                child
                and child[0].pid == row["pid"]
                and row["process_started"] is not None
                and abs(child[1] - row["process_started"]) < 0.01
                and child[0].poll() is not None
            )
        alive = verified_process(row["pid"], row["process_started"], run_id) is not None
        if known_exited:
            alive = False
        if (
            row["state"] in ACTIVE_RUNS
            and row["pid"]
            and not alive
            and (known_exited or process_exited(row["pid"], row["process_started"]))
        ):
            self._record_exit(run_id)
            row = self.store.run(run_id)
        return {
            "run_id": run_id,
            "state": row["state"],
            "owned_by_session": row["owner"] == self.owner,
            "worker_alive": alive,
            "selected_count": len(json.loads(row["targets_json"])),
            "updated_at": row["updated_at"],
            "heartbeat": row["heartbeat"],
            "progress_stale": row["heartbeat"] is None
            or time.time() - row["heartbeat"] > self.policy.orphan_threshold_seconds,
            "progress": json.loads(row["progress_json"]),
            "summary": json.loads(row["summary_json"]) if row["summary_json"] else None,
            "last_error": row["last_error"],
        }

    def stop(self, model: Stop) -> dict[str, Any]:
        def request(conn: Any) -> dict[str, Any]:
            row = conn.execute("SELECT * FROM mcp_runs WHERE run_id=?", (model.run_id,)).fetchone()
            if row is None:
                raise ToolFailure("RUN_NOT_FOUND", "Run ID was not found.")
            if row["owner"] != self.owner:
                raise ToolFailure(
                    "RUN_NOT_OWNED",
                    "This run belongs to a different MCP session.",
                    "Stop it in its original host or wait for supervised shutdown.",
                )
            if row["state"] not in ACTIVE_RUNS:
                return {"run_id": model.run_id, "state": row["state"]}
            conn.execute(
                "UPDATE mcp_runs SET state='stopping',stop_requested=1,updated_at=? WHERE run_id=?",
                (time.time(), model.run_id),
            )
            return {"run_id": model.run_id, "state": "stopping", "partial_files_kept": True}

        return self.store.mutate("queue_stop", model.request_key, model.model_dump(), request)

    def close(self) -> None:
        self._closed.set()
        with self._mutex:
            children = list(self._children.items())
        deadline = time.monotonic() + self.policy.shutdown_grace_seconds
        for _, (process, _) in children:
            if process.stdin:
                with contextlib.suppress(OSError):
                    process.stdin.close()  # EOF is a stop request, even if SQLite is busy.
        for run_id, (process, started) in children:
            identity = self._identities.get(run_id, (process.pid, started))
            with contextlib.suppress(sqlite3.Error, ToolFailure):
                row = self.store.run(run_id)
                if row["pid"] and row["process_started"]:
                    identity = (row["pid"], row["process_started"])
            while time.monotonic() < deadline and not process_exited(*identity):
                time.sleep(0.03)
            if not process_exited(*identity):
                terminate_owned(*identity, run_id)
                kill_deadline = time.monotonic() + 2
                while time.monotonic() < kill_deadline and not process_exited(*identity):
                    time.sleep(0.03)
            try:
                process.wait(timeout=max(0.01, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                process.kill()  # owned launcher handle; real worker handled above
                with contextlib.suppress(subprocess.TimeoutExpired):
                    process.wait(timeout=2)
            with contextlib.suppress(sqlite3.Error, ToolFailure):
                self.status(run_id)
        if self._heartbeat:
            self._heartbeat.join(timeout=1)
