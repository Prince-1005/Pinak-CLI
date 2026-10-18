"""Terminal adapter for the local durable download queue."""

from __future__ import annotations

import argparse
import os
import shlex
import threading
from collections.abc import Sequence
from datetime import datetime
from typing import NoReturn

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn
from rich.table import Table
from rich.text import Text

from ..engine import DownloadEvent, DownloadRequest
from ..queue import QueueJob, add_job, import_file, list_jobs, retry_failed, run_queue
from ..utils import human_size

console = Console()


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


class QueueDisplay:
    """One live terminal surface shared by CLI and slash-command queue runs."""

    def __init__(self, total: int) -> None:
        self.lock = threading.RLock()
        self.overall = Progress(
            TextColumn("[cyan]Jobs[/]"),
            BarColumn(),
            TextColumn("{task.completed:.0f}/{task.total:.0f}"),
            console=console,
            auto_refresh=False,
            expand=True,
        )
        self.overall_id = self.overall.add_task("Queue", total=total)
        self.transfer = Progress(
            SpinnerColumn(),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
            auto_refresh=False,
            expand=True,
        )
        self.transfer_id = self.transfer.add_task("Download", total=None)
        self.job: QueueJob | None = None
        self.filename = ""
        self.status = "Checking saved jobs…"
        self.started = 0
        self.live = Live(self.render(), console=console, refresh_per_second=8, transient=True)

    def __enter__(self) -> QueueDisplay:
        self.live.start(refresh=True)
        return self

    def __exit__(self, *_args: object) -> None:
        self.live.stop()

    def render(self) -> Panel:
        with self.lock:
            parts: list = [self.overall]
            if self.job:
                request = self.job.request
                mode = "Audio" if request.extract_audio else "Media"
                parts.extend(
                    [
                        Text(
                            f"Job #{self.job.id} · {mode} · {request.quality} · Attempt {self.job.attempts}",
                            style="bold cyan",
                        ),
                        Text(request.url, overflow="fold"),
                        Text(f"Save to: {request.output_dir}", style="dim", overflow="fold"),
                        Text(self.filename or "Preparing download…", style="cyan", overflow="fold"),
                        self.transfer,
                    ]
                )
                task = self.transfer.tasks[self.transfer_id]
                size = human_size(task.completed)
                total = human_size(task.total) if task.total else "unknown size"
                speed = f"{human_size(task.speed)}/s" if task.speed else "—"
                eta = f"{int(task.time_remaining)}s" if task.time_remaining is not None else "—"
                parts.append(Text(f"{size} / {total}  •  {speed}  •  ETA {eta}", style="dim"))
            parts.extend(
                [
                    Text(self.status, overflow="fold"),
                    Text("Ctrl+C stops this run; unfinished jobs stay saved.", style="dim"),
                ]
            )
            return Panel(
                Group(*parts), title="[bold cyan]PINAK DOWNLOAD QUEUE[/]", border_style="cyan"
            )

    def handle(self, job: QueueJob, event: DownloadEvent) -> None:
        with self.lock:
            if event.kind == "started":
                self.job = job
                self.started += 1
                overall = self.overall.tasks[self.overall_id]
                if self.started > (overall.total or 0):
                    self.overall.update(self.overall_id, total=self.started)
                self.filename = ""
                self.status = "Preparing download…"
                self.transfer.reset(self.transfer_id, total=None)
            elif event.kind == "message" and event.message:
                self.status = event.message
            elif event.kind == "progress":
                task = self.transfer.tasks[self.transfer_id]
                if (event.message and event.message != self.filename) or (
                    event.downloaded or 0
                ) < task.completed:
                    self.transfer.reset(self.transfer_id, total=event.total or None)
                self.filename = event.message or self.filename
                self.transfer.update(
                    self.transfer_id, total=event.total or None, completed=event.downloaded or 0
                )
                self.status = "Downloading…"
            elif event.kind == "processing":
                self.status = "Processing / merging media…"
            elif event.kind == "finished":
                style = {
                    "succeeded": "green",
                    "skipped": "yellow",
                    "failed": "red",
                    "interrupted": "yellow",
                }.get(event.message, "white")
                label = (
                    "Interrupted — saved for next run"
                    if event.message == "interrupted"
                    else event.message.capitalize()
                )
                console.print(Text(f"#{job.id}  {label}  ·  {job.request.url}", style=style))
                if event.files:
                    console.print(
                        Text(
                            f"    Saved {len(event.files)} file(s) to {job.request.output_dir}",
                            style="dim",
                        )
                    )
                for error in event.errors:
                    console.print(
                        Text(f"    {error}", style="red" if event.message == "failed" else "yellow")
                    )
                if event.message != "interrupted":
                    self.overall.advance(self.overall_id)
                self.status = label
            self.live.update(self.render())


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
            total = sum(job.status in {"queued", "running"} for job in list_jobs())
            if args.limit is not None:
                total = min(total, args.limit)
            with QueueDisplay(max(0, total)) as display:
                summary = run_queue(on_event=display.handle, limit=args.limit)
            console.print(
                Panel(
                    Text.assemble(
                        (f"{summary.succeeded} succeeded", "green"),
                        "  ·  ",
                        (f"{summary.skipped} skipped", "yellow"),
                        "  ·  ",
                        (f"{summary.failed} failed", "red"),
                    ),
                    title="Queue paused" if summary.interrupted else "Queue complete",
                    border_style="yellow" if summary.interrupted else "cyan",
                )
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
