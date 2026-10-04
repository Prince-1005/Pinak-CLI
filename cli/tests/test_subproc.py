"""Unit tests for pinak.subproc — centralized subprocess helper."""

import subprocess
import sys

import pytest

from pinak.subproc import run_cmd


def test_run_cmd_captures_output():
    result = run_cmd([sys.executable, "-c", "print('hi')"], timeout=15.0)
    assert result.returncode == 0
    assert result.stdout.strip() == "hi"


def test_run_cmd_check_raises_on_failure():
    with pytest.raises(subprocess.CalledProcessError):
        run_cmd([sys.executable, "-c", "raise SystemExit(3)"], timeout=15.0, check=True)


def test_run_cmd_missing_binary_returns_failure():
    result = run_cmd(["definitely-not-a-real-binary-xyz"], timeout=5.0)
    assert result.returncode != 0
    assert result.stderr != ""


def test_run_cmd_timeout_returns_failure():
    result = run_cmd([sys.executable, "-c", "import time; time.sleep(30)"], timeout=0.5)
    assert result.returncode != 0
    assert "timed out" in result.stderr
