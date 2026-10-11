"""
Allows running the package directly with:
    python -m pinak
"""

from pinak.cli import run_cli

if __name__ == "__main__":
    run_cli()  # pragma: no cover - exercised via test_entry subprocess smoke
