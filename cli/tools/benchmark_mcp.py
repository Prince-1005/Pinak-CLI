"""Development benchmark; requires repository tests and the dev/MCP extras."""

import argparse
import json
import math
import sys
import tempfile
import time
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))
from test_mcp_process_lifecycle import slow_url

from pinak import history
from pinak import queue as core
from pinak.engine import DownloadRequest
from pinak.mcp_server.models import Policy
from pinak.mcp_server.tools import Tools


def p95(samples):
    return round(sorted(samples)[math.ceil(len(samples) * 0.95) - 1], 4)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="pinak-mcp-benchmark-") as temporary:
        root = Path(temporary).resolve()
        history.DB_FILE = str(root / "data" / "history.db")
        history.init_db()
        output = root / "output"
        output.mkdir()
        service = Tools(Policy(default_output_dir=output))
        with wave.open(str(output / "sample.wav"), "wb") as audio:
            audio.setparams((1, 2, 8000, 0, "NONE", "not compressed"))
            audio.writeframes(b"\x00\x01" * 8000)
        with service.store.connect() as conn, conn:
            request = json.dumps(
                DownloadRequest.capture(
                    "https://example.com/video", output_dir=str(output)
                ).to_dict()
            )
            conn.executemany(
                "INSERT INTO queue_jobs(request_json,fingerprint,status,created_at,updated_at) VALUES(?,'benchmark','queued',?,?)",
                [(request, time.time(), time.time()) for _ in range(10000)],
            )
        readings = {}
        for name, arguments in [
            ("server_info", {}),
            ("queue_list", {"limit": 100}),
            ("media_info", {"path": str(output / "sample.wav")}),
        ]:
            samples = []
            for _ in range(20):
                before = time.perf_counter()
                result = service.call(name, arguments)
                assert result["ok"], result
                samples.append(time.perf_counter() - before)
            readings[name] = {
                "samples": 20,
                "p95_seconds": p95(samples),
                "max_seconds": round(max(samples), 4),
            }
        with service.store.connect() as conn, conn:
            conn.execute("DELETE FROM queue_jobs")
        fixture = slow_url.__wrapped__()
        url = next(fixture)
        starts, stops = [], []
        try:
            for index in range(20):
                job = service.call(
                    "queue_add",
                    {"url": url, "options": {"force": True}, "request_key": f"add-{index}"},
                )
                assert job["ok"], job
                before = time.perf_counter()
                run = service.call(
                    "queue_start",
                    {
                        "job_ids": [job["data"]["job_id"]],
                        "max_jobs": 1,
                        "request_key": f"run-{index}",
                    },
                )
                assert run["ok"], run
                starts.append(time.perf_counter() - before)
                run_id = run["data"]["run_id"]
                claim_deadline = time.monotonic() + 5
                while core.get_job(job["data"]["job_id"]).status != "running":
                    if time.monotonic() > claim_deadline:
                        raise RuntimeError("Benchmark worker did not claim its fixture job")
                    time.sleep(0.01)
                before = time.perf_counter()
                result = service.call(
                    "queue_stop", {"run_id": run_id, "request_key": f"stop-{index}"}
                )
                assert result["ok"], result
                deadline = time.monotonic() + 12
                while time.monotonic() < deadline:
                    state = service.controller.status(run_id)
                    if state["state"] not in {"starting", "running", "stopping"}:
                        break
                    time.sleep(0.02)
                else:
                    raise RuntimeError("Stop deadline exceeded")
                stops.append(time.perf_counter() - before)
        finally:
            fixture.close()
            service.close()
        readings["start"] = {
            "samples": 20,
            "p95_seconds": p95(starts),
            "max_seconds": round(max(starts), 4),
        }
        readings["stop"] = {
            "samples": 20,
            "p95_seconds": p95(stops),
            "max_seconds": round(max(stops), 4),
        }
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(readings, indent=2), encoding="utf-8")
        print("MCP_PERF " + json.dumps(readings))


if __name__ == "__main__":
    main()
