"""Centralized subprocess helper for trusted local binaries (ffmpeg/ffprobe).

All subprocess invocations go through :func:`run_cmd` so timeouts, output
capture, logging, and ``shell=False`` safety are enforced in one place.
Only fixed argument vectors are ever executed — never user input, never a shell.
"""

from __future__ import annotations

import subprocess

from .logging_setup import get_logger

log = get_logger("pinak.subproc")


def run_cmd(
    cmd: list[str],
    *,
    timeout: float = 30.0,
    check: bool = False,
    capture: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run a trusted local command vector without a shell.

    Args:
        cmd: argv vector (executable + fixed flags + validated file paths).
        timeout: seconds before the child is killed.
        check: if True, raise :class:`subprocess.CalledProcessError` on non-zero exit.
        capture: if True, capture stdout/stderr as text instead of inheriting.

    Returns:
        CompletedProcess. If the binary is missing or times out, a synthetic
        result with ``returncode == 1`` is returned (unless ``check=True``,
        which raises instead).
    """
    log.debug("Running: %s (timeout=%ss)", " ".join(cmd), timeout)
    try:
        # Fixed argv, shell=False (default): safe against injection. nosec B603
        result = subprocess.run(  # nosec B603
            cmd,
            capture_output=capture,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        log.debug("Binary not found: %s", cmd[0] if cmd else "")
        result = subprocess.CompletedProcess(cmd, 1, "", str(exc))
    except subprocess.TimeoutExpired as exc:
        log.warning("Command timed out after %ss: %s", timeout, cmd[0] if cmd else "")
        result = subprocess.CompletedProcess(cmd, 1, "", f"timed out after {timeout}s: {exc}")
    except OSError as exc:
        log.debug("Failed to execute %s: %s", cmd[0] if cmd else "", exc)
        result = subprocess.CompletedProcess(cmd, 1, "", str(exc))
    if check and result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode, cmd, output=result.stdout, stderr=result.stderr
        )
    return result
