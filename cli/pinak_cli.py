"""pinak_cli.py — Standalone entrypoint wrapper.

Maintained for Docker containers and direct `python pinak_cli.py` invocations.
Package console script entrypoint is defined in pyproject.toml (`pinak.cli:run_cli`).
"""

from pinak.cli import run_cli

if __name__ == "__main__":
    run_cli()
