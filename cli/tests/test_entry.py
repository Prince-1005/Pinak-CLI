"""Entry-point smoke test: real subprocess, real interpreter, no mocks."""

import os
import subprocess
import sys

import pinak.__main__  # noqa: F401 - covers the entry-point import line
from pinak import __version__


def test_module_entrypoint_version():
    proc = subprocess.run(
        [sys.executable, "-m", "pinak", "--version"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )
    assert proc.returncode == 0
    assert __version__ in proc.stdout


def test_module_entrypoint_help():
    env = os.environ.copy()
    env["NO_COLOR"] = "1"
    env["TERM"] = "dumb"
    env["COLUMNS"] = "1000"
    proc = subprocess.run(
        [sys.executable, "-m", "pinak", "--help"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        env=env,
    )
    assert proc.returncode == 0
    assert proc.stdout is not None
    assert "--dry-run" in proc.stdout
