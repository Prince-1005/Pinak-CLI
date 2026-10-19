"""Private supervised worker entry point. No MCP protocol or network listener."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import signal
import sys
import threading
import time
from dataclasses import asdict
from typing import Any

import psutil

from .. import history
from .. import queue as core
from ..config import config
from ..engine import DownloadEvent, DownloadRequest, managed_downloads
from .models import Policy
from .policy import clean, output_path
from .store import Store

_windows_job: Any = None


def protect_windows_children() -> Any:
    if os.name != "nt":
        return None
    import win32api
    import win32job

    job = win32job.CreateJobObject(None, "")
    limits = win32job.QueryInformationJobObject(job, win32job.JobObjectExtendedLimitInformation)
    limits["BasicLimitInformation"]["LimitFlags"] |= win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    win32job.SetInformationJobObject(job, win32job.JobObjectExtendedLimitInformation, limits)
    win32job.AssignProcessToJobObject(job, win32api.GetCurrentProcess())
    return job


def main() -> int:
    global _windows_job
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--owner", required=True)
    parser.add_argument("--db", required=True)
    args = parser.parse_args()
    history.DB_FILE = os.path.abspath(args.db)
    payload = json.loads(sys.stdin.readline(1048577))
    policy = Policy.model_validate(payload["policy"])
    config["history_enabled"] = bool(payload.get("history_enabled", True))
    store = Store(policy)
    row = store.run(args.run_id)
    if row["owner"] != args.owner or row["state"] != "starting":
        return 2
    stop, done = threading.Event(), threading.Event()
    last_ping = [time.monotonic()]
    stop_started: list[float | None] = [None]
    last_progress = [0.0]

    def reader() -> None:
        try:
            while sys.stdin.readline(16) == "ping\n":
                last_ping[0] = time.monotonic()
        finally:
            stop.set()

    def monitor() -> None:
        last_db_check = 0.0
        while not done.wait(0.1):
            now = time.monotonic()
            if now - last_ping[0] > policy.orphan_threshold_seconds:
                stop.set()
            if stop.is_set():
                since = stop_started[0]
                if since is None:
                    stop_started[0] = now
                elif now - since >= policy.shutdown_grace_seconds:
                    if sys.platform != "win32":
                        os.killpg(os.getpid(), signal.SIGKILL)
                    os._exit(130)  # Windows closes the owned Job Object and its descendants.
            if now - last_db_check >= 0.5:
                last_db_check = now
                with contextlib.suppress(Exception):
                    if store.run(args.run_id)["stop_requested"]:
                        stop.set()
                    store.update_run(args.run_id, heartbeat=time.time())

    def ready() -> None:
        store.update_run(
            args.run_id,
            state="running",
            pid=os.getpid(),
            process_started=psutil.Process().create_time(),
            heartbeat=time.time(),
        )

    def validate(request: DownloadRequest) -> None:
        # Re-resolve each saved destination, including symlinks changed after enqueue.
        output_path(request.output_dir, policy)

    def progress(job: core.QueueJob, event: DownloadEvent) -> None:
        now = time.monotonic()
        if event.kind in {"started", "finished"} or now - last_progress[0] >= 0.25:
            last_progress[0] = now
            snapshot = clean(
                {
                    "job_id": job.id,
                    "kind": event.kind,
                    "message": event.message[:512],
                    "downloaded_bytes": event.downloaded,
                    "total_bytes": event.total,
                    "timestamp": time.time(),
                }
            )
            store.update_run(args.run_id, progress_json=json.dumps(snapshot))

    try:
        _windows_job = protect_windows_children()
        threading.Thread(target=reader, daemon=True, name="pinak-parent-pipe").start()
        threading.Thread(target=monitor, daemon=True, name="pinak-worker-watchdog").start()
        with managed_downloads(stop.is_set):
            summary = core.run_queue(
                json.loads(row["targets_json"]),
                on_event=progress,
                stop_requested=stop.is_set,
                on_ready=ready,
                validate_request=validate,
            )
        store.update_run(
            args.run_id,
            state="interrupted" if summary.interrupted else "completed",
            summary_json=json.dumps(asdict(summary)),
            heartbeat=time.time(),
        )
        return 0
    except BaseException as exc:
        with contextlib.suppress(Exception):
            store.update_run(
                args.run_id,
                state="interrupted" if stop.is_set() else "failed",
                last_error=str(clean(str(exc)))[:2000],
                heartbeat=time.time(),
            )
        return 1
    finally:
        done.set()


if __name__ == "__main__":
    raise SystemExit(main())
