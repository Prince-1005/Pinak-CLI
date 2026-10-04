"""Entry-point smoke test: real subprocess, real interpreter, no mocks."""

import subprocess
import sys

import pinak.__main__  # noqa: F401 - covers the entry-point import line
from pinak import __version__


def test_module_entrypoint_version():
    proc = subprocess.run(
        [sys.executable, "-m", "pinak", "--version"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0
    assert __version__ in proc.stdout


def test_module_entrypoint_help():
    proc = subprocess.run(
        [sys.executable, "-m", "pinak", "--help"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0
    assert "--dry-run" in proc.stdout
