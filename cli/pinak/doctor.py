"""Pinak Doctor — environment diagnostics with actionable hints."""

from __future__ import annotations

import os
import shutil
import sys
import urllib.request

import yt_dlp
from rich.console import Console
from rich.table import Table

from .config import CONFIG_FILE, PinakSettings, config
from .ffmpeg_setup import ensure_ffmpeg, ensure_ffprobe
from .subproc import run_cmd
from .utils import BOLD, RESET

console = Console()


def _check_cli_on_path() -> tuple[bool, str, str]:
    """Check the ``pinak`` console script is reachable from PATH."""
    found = shutil.which("pinak")
    if found:
        return True, found, ""
    return (
        False,
        "not on PATH",
        "Reinstall with pipx (pipx install pinak-cli), or run via: "
        "python -m pinak. Also check that Python's Scripts folder is on PATH.",
    )


def _check_ffmpeg_executable(path: str) -> tuple[bool, str]:
    """Check the binary exists AND runs (version check)."""
    if not path:
        return False, "not configured"
    if os.path.exists(path):
        binary = path
    else:
        binary = shutil.which(os.path.basename(path)) or shutil.which(path) or ""
        if not binary:
            return False, f"{path} (not found)"
    proc = run_cmd([binary, "-version"], timeout=10.0)
    if proc.returncode == 0:
        return True, binary
    detail = (proc.stderr or proc.stdout or "unknown error").strip().splitlines()
    return False, f"{binary} ({detail[0] if detail else 'non-zero exit'})"


def run_doctor(verbose: bool = False) -> bool:
    print(f"\n{BOLD}--- Pinak Doctor ---{RESET}")
    checks: list[tuple[str, str, bool, str]] = []

    checks.append(("Python", sys.version.split()[0], True, ""))

    try:
        ytdlp_ver = getattr(yt_dlp.version, "__version__", "installed")
        checks.append(("yt-dlp", str(ytdlp_ver), True, ""))
    except Exception as exc:  # pragma: no cover
        checks.append(
            (
                "yt-dlp",
                f"import failed: {exc}",
                False,
                "Reinstall with: pip install -U yt-dlp",
            )
        )

    # ensure_* activates the static-ffmpeg fallback (warm cache: instant, no
    # download) so doctor agrees with what real downloads will resolve.
    ffmpeg_path = ensure_ffmpeg()
    ok, detail = _check_ffmpeg_executable(ffmpeg_path)
    checks.append(
        (
            "ffmpeg",
            detail,
            ok,
            (
                ""
                if ok
                else "Run: pinak --install-ffmpeg (downloads a static build), or install "
                "FFmpeg from https://ffmpeg.org/download.html, add it to PATH, "
                "or set ffmpeg_path in config."
            ),
        )
    )

    ffprobe_path = ensure_ffprobe()
    ok, detail = _check_ffmpeg_executable(ffprobe_path)
    checks.append(
        (
            "ffprobe",
            detail,
            ok,
            (
                ""
                if ok
                else "ffprobe ships with FFmpeg — install FFmpeg or set ffprobe_path in config."
            ),
        )
    )

    output_dir = str(config.get("output_dir", "downloads"))
    try:
        os.makedirs(output_dir, exist_ok=True)
        test_file = os.path.join(output_dir, ".pinak_write_test")
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(test_file)
        # Disk space check (>= 500 MB free recommended).
        free_mb = shutil.disk_usage(os.path.abspath(output_dir)).free / (1024 * 1024)
        space_ok = free_mb >= 500
        space_detail = f"{os.path.abspath(output_dir)} ({free_mb:.0f} MB free)"
        checks.append(
            (
                "Output folder writable",
                space_detail,
                True,
                (
                    ""
                    if space_ok
                    else "Low disk space (<500 MB). Free space or choose another output_dir."
                ),
            )
        )
    except Exception as exc:
        checks.append(
            (
                "Output folder writable",
                f"{os.path.abspath(output_dir)} ({exc})",
                False,
                "Choose a writable folder with --output <dir> or /setout <dir>.",
            )
        )

    cli_ok, cli_detail, cli_hint = _check_cli_on_path()
    checks.append(("CLI on PATH", cli_detail, cli_ok, cli_hint))

    config_detail = os.path.abspath(CONFIG_FILE) if os.path.exists(CONFIG_FILE) else "not found"
    config_ok = os.path.exists(CONFIG_FILE)
    config_hint = ""
    if config_ok:
        try:
            PinakSettings(**{k: v for k, v in config.items() if k in PinakSettings.model_fields})
        except Exception as exc:
            config_ok = False
            config_detail = f"{config_detail} (INVALID: {exc})"
            config_hint = "Fix invalid values (quality/format/retry_count) or delete the file to regenerate defaults."
    else:
        config_hint = "Run pinak once to generate a default config."
    checks.append(("Config file valid", config_detail, config_ok, config_hint))

    try:
        timeout = float(config.get("connect_timeout", 10))
    except Exception:
        timeout = 10.0
    internet_ok = False
    connected_host = ""
    for host in (
        "https://www.google.com",
        "https://1.1.1.1",
        "https://www.cloudflare.com",
        "https://httpbin.org/status/200",
    ):
        try:
            # Fixed HTTPS connectivity probe — no user-controlled scheme. nosec B310
            req = urllib.request.Request(host, headers={"User-Agent": "PinakCLI"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310
                if hasattr(resp, "close"):
                    resp.close()
                internet_ok = True
                connected_host = host.split("//")[-1].split("/")[0]
                break
        except Exception:
            continue

    if not internet_ok:
        import socket

        sock_timeout = min(timeout, 2.0)
        for ip, port in (("1.1.1.1", 53), ("8.8.8.8", 53)):
            try:
                with socket.create_connection((ip, port), timeout=sock_timeout):
                    internet_ok = True
                    connected_host = f"{ip}:{port} (socket fallback)"
                    break
            except Exception:
                continue

    checks.append(
        (
            "Internet Connection",
            f"{connected_host} accessible" if internet_ok else "unreachable",
            internet_ok,
            "" if internet_ok else "Check network/VPN/firewall, then retry.",
        )
    )

    table = Table(title="Pinak Doctor Diagnostics", style="blue")
    table.add_column("Check", style="cyan")
    table.add_column("Details", style="magenta")
    table.add_column("Status", justify="center")
    if verbose:
        table.add_column("Fix", style="yellow")

    all_ok = True
    for name, detail, ok, hint in checks:
        if not ok:
            all_ok = False
        status_text = "[green]OK[/]" if ok else "[red]FAIL[/]"
        if verbose:
            table.add_row(name, str(detail), status_text, hint or "-")
        else:
            table.add_row(name, str(detail), status_text)

    console.print(table)

    if not verbose:
        failures = [c for c in checks if not c[2]]
        for name, _detail, _ok, hint in failures:
            if hint:
                console.print(f"[yellow]Tip ({name}): {hint}[/]")

    if all_ok:
        console.print("[green][+] All checks passed.[/]")
    else:
        console.print(
            "[yellow][!] Some checks failed. Re-run with --verbose / --doctor --verbose for fix hints.[/]"
        )

    return all_ok
