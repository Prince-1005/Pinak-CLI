"""Terminal adapter for the local durable download queue."""

from __future__ import annotations

import argparse
import os
import shlex
import threading
from collections.abc import Sequence
from datetime import datetime
from typing import NoReturn

from rich.console import Console
from rich.table import Table

from ..engine import DownloadEvent, DownloadRequest
from ..queue import QueueJob, add_job, import_file, list_jobs, retry_failed, run_queue

console = Console()
_progress_lock = threading.Lock()
_progress_buckets: dict[int, int] = {}


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise ValueError(message)


def _parser(prog: str = "pinak queue") -> argparse.ArgumentParser:
    parser = _Parser(prog=prog, description="Save downloads locally and resume later")
    commands = parser.add_subparsers(dest="action", required=True, parser_class=_Parser)
    add = commands.add_parser("add", help="Save a URL as a durable job")
    add.add_argument("url")
    add.add_argument("--audio", action="store_true")
    add.add_argument("--quality")
    add.add_argument("--output", "-o")
    add.add_argument("--force", action="store_true")
    add.add_argument("--any", action="store_true")
    add.add_argument("--trim")
    imported = commands.add_parser("import", help="Save a UTF-8 batch file as jobs")
    imported.add_argument("file")
    listed = commands.add_parser("list", help="Show saved jobs")
    listed.add_argument("--status", choices=("queued", "running", "succeeded", "skipped", "failed"))
    run = commands.add_parser("run", help="Run queued jobs until finished or interrupted")
    run.add_argument("--limit", type=int)
    retry = commands.add_parser("retry", help="Put failed jobs back in the queue")
    target = retry.add_mutually_exclusive_group(required=True)
    target.add_argument("id", nargs="?", type=int)
    target.add_argument("--failed", action="store_true")
    return parser


def _display_job(job: QueueJob, event: DownloadEvent) -> None:
    if event.kind == "message" and event.message:
        console.print(f"#{job.id} {event.message}", markup=False)
    elif event.kind == "progress" and event.total and event.downloaded is not None:
        bucket = min(100, max(0, int(event.downloaded * 100 / event.total))) // 20 * 20
        with _progress_lock:
            previous = _progress_buckets.get(job.id, -1)
            if bucket > previous:
                _progress_buckets[job.id] = bucket
                console.print(f"Job #{job.id}: {bucket}%")
    elif event.kind == "processing":
        console.print(f"Job #{job.id}: processing media")
    elif event.kind == "result":
        console.print(f"Job #{job.id}: {event.message}")
        with _progress_lock:
            _progress_buckets.pop(job.id, None)


def _show_jobs(status: str | None = None) -> None:
    jobs = list_jobs(status)
    if not jobs:
        console.print("No queue jobs found.")
        return
    table = Table(title="Pinak queue")
    for name in ("ID", "Status", "Attempts", "Added", "URL / error"):
        table.add_column(name)
    for job in jobs:
        when = datetime.fromtimestamp(job.created_at).strftime("%Y-%m-%d %H:%M")
        detail = job.request.url
        if job.last_error:
            detail += f"\n{job.last_error[:140]}"
        table.add_row(str(job.id), job.status, str(job.attempts), when, detail)
    console.print(table)


def main(argv: Sequence[str], *, prog: str = "pinak queue") -> int:
    parser = _parser(prog)
    try:
        args = parser.parse_args(list(argv))
        if args.action == "add":
            request = DownloadRequest.capture(
                args.url,
                output_dir=args.output,
                quality=args.quality,
                extract_audio=args.audio,
                force=args.force,
                is_any_command=args.any,
                trim_range=args.trim,
            )
            job_id, created = add_job(request)
            console.print(f"Job #{job_id} {'queued' if created else 'already queued'}.")
        elif args.action == "import":
            jobs = import_file(args.file)
            console.print(
                f"Imported {sum(created for _, created in jobs)} job(s); {len(jobs)} entries."
            )
        elif args.action == "list":
            _show_jobs(args.status)
        elif args.action == "retry":
            count = retry_failed(None if args.failed else args.id)
            console.print(f"Queued {count} failed job(s) for retry.")
            if count == 0:
                return 1
        elif args.action == "run":
            summary = run_queue(on_event=_display_job, limit=args.limit)
            console.print(
                f"Queue: {summary.succeeded} succeeded, {summary.skipped} skipped, "
                f"{summary.failed} failed."
            )
            if summary.interrupted:
                console.print("Interrupted; the active job is queued for the next run.")
                return 130
            return 1 if summary.failed else 0
        return 0
    except (ValueError, OSError, RuntimeError) as exc:
        console.print(f"Queue error: {exc}")
        return 2


def run_repl(raw: str) -> int:
    """Route /queue arguments through the same parser as `pinak queue`."""
    try:
        args = shlex.split(raw, posix=os.name != "nt")
        if os.name == "nt":
            args = [
                arg[1:-1] if len(arg) > 1 and arg[0] == arg[-1] and arg[0] in "\"'" else arg
                for arg in args
            ]
    except ValueError as exc:
        console.print(f"Queue error: {exc}")
        return 2
    if not args or args[0].lower() == "help":
        args = ["--help"]
    try:
        return main(args, prog="/queue")
    except SystemExit as exc:
        # argparse uses SystemExit for help; returning keeps the REPL open.
        return int(exc.code or 0)
