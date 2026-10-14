"""Single-command (non-REPL) execution: plan, dry-run, download, JSON output.

Keeps ``pinak/cli.py`` thin: ``main()`` parses flags, this module executes.
All functions return plain values / exit codes so they are unit-testable.
"""

from __future__ import annotations

import json
import os
from typing import Any

from rich.console import Console
from rich.table import Table

from .. import updater
from ..config import config, save_config
from ..doctor import run_doctor
from ..downloader import handle_download
from ..notify import print_update_notice
from ..utils import get_platform, human_size, normalize_quality

console = Console()


def maybe_print_update_notice() -> None:
    """Surface cached update notices (set by the background check)."""
    if updater.UPDATE_AVAILABLE and updater.UPDATE_PACKAGE:
        print_update_notice(updater.UPDATE_PACKAGE, updater.UPDATE_AVAILABLE)
    if updater.PINAK_UPDATE_AVAILABLE and updater.PINAK_PACKAGE:
        print_update_notice(updater.PINAK_PACKAGE, updater.PINAK_UPDATE_AVAILABLE)


def build_plan(
    url: str,
    extract_audio: bool,
    quality: str,
    output_dir: str | None = None,
) -> dict[str, Any]:
    """Describe what a download *would* do, without touching the network heavily.

    Only local metadata is resolved (platform guess via yt-dlp extractors,
    config defaults). No media is fetched.
    """
    outdir = os.path.abspath(output_dir or str(config.get("output_dir", "downloads")))
    if extract_audio:
        mode = "audio"
        fmt = str(config.get("audio_format", "mp3"))
        quality_str = f"{config.get('audio_quality', '192')} kbps"
    else:
        mode = "video"
        fmt = str(config.get("video_format", "mp4"))
        quality_str = quality
    return {
        "url": url,
        "platform": get_platform(url),
        "mode": mode,
        "quality": quality_str,
        "format": fmt,
        "output_dir": outdir,
    }


def render_plan(plan: dict[str, Any], as_json: bool = False) -> None:
    """Print a dry-run plan as a table (default) or JSON."""
    if as_json:
        print(json.dumps({"dry_run": True, **plan}, indent=2))
        return
    table = Table(title="Dry Run — nothing will be downloaded", show_header=False)
    table.add_column("Field", style="cyan", justify="right")
    table.add_column("Value", style="magenta")
    table.add_row("URL:", plan["url"])
    table.add_row("Platform:", plan["platform"])
    table.add_row("Mode:", plan["mode"])
    table.add_row("Quality:", plan["quality"])
    table.add_row("Format:", plan["format"])
    table.add_row("Output Dir:", plan["output_dir"])
    console.print(table)


def result_to_jsonable(result: dict[str, Any]) -> dict[str, Any]:
    """Convert a ``handle_download`` result dict into JSON-serializable summary."""
    files = []
    for path in result.get("files", []) or []:
        try:
            size = os.path.getsize(path) if os.path.exists(path) else None
        except OSError:
            size = None
        files.append(
            {
                "path": path,
                "size": size,
                "size_human": human_size(size) if size is not None else "unknown",
            }
        )
    info = result.get("info") or {}
    return {
        "success": bool(result.get("success")),
        "canceled": bool(result.get("canceled", False)),
        "url": result.get("url"),
        "platform": get_platform(result.get("url") or ""),
        "mode": "audio" if result.get("audio") else "video",
        "quality": result.get("quality"),
        "duration": info.get("duration"),
        "files": files,
        "error_count": len(result.get("errors", []) or []),
    }


def run_single(
    url: str | None,
    output: str | None,
    force: bool,
    audio: bool,
    quality: str | None,
    doctor: bool,
    verbose: bool,
    dry_run: bool,
    as_json: bool,
    is_any: bool = False,
) -> int:
    """Execute single-command mode. Returns the process exit code."""
    if output:
        config["output_dir"] = output
        save_config()

    if doctor:
        return 0 if run_doctor(verbose=verbose) else 1

    if not url:
        console.print("[red][!] Error: URL is required in single-command mode.[/red]")
        console.print('[yellow]Tip: pinak "https://example.com/video" --quality 720p[/]')
        console.print("[yellow]Tip: add --dry-run to preview without downloading.[/]")
        return 1

    if not url.startswith("http"):
        console.print(
            f"[red][!] Error: Invalid URL {url!r}. URL must start with http:// or https://[/red]"
        )
        console.print(
            '[yellow]Tip: copy the full link from your browser, e.g. pinak "https://..."[/]'
        )
        return 1

    norm_quality = normalize_quality(quality or config.get("quality", "best"))
    if not norm_quality:
        console.print(f"[red][!] Error: Invalid quality {quality!r}.[/red]")
        console.print(
            "[yellow]Tip: use best, worst, audio, 360p, 720p, or 1080p. Example: --quality 720p[/]"
        )
        return 1

    extract_audio = audio or norm_quality == "audio"

    if dry_run:
        render_plan(build_plan(url, extract_audio, norm_quality, output), as_json=as_json)
        return 0

    result = handle_download(
        url,
        extract_audio=extract_audio,
        force=force,
        quality=norm_quality,
        interactive=False,
        is_any_command=is_any,
    )
    if as_json:
        print(json.dumps(result_to_jsonable(result), indent=2))
    else:
        maybe_print_update_notice()
    return 0 if result.get("success") else 1
