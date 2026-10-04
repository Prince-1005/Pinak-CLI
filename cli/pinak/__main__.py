"""
Allows running the package directly with:
    python -m pinak
"""

from pinak.cli import run_cli  # noqa: F401 - re-exported for the entry point

if __name__ == "__main__":
    run_cli()  # pragma: no cover - exercised via test_entry subprocess smoke
