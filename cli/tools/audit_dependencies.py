"""Audit every pinned version in universal locks, including other platform markers."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name

LOCKFILES = (
    "requirements-lock.txt",
    "requirements-runtime-lock.txt",
    "requirements-mcp-lock.txt",
    "requirements-cloud-lock.txt",
)


def collect_pins(paths: Sequence[Path]) -> list[str]:
    """Flatten all marker branches; an audit must not skip another OS/Python version."""
    pins: set[str] = set()
    for path in paths:
        count = 0
        for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            line = raw.strip()
            if not line or line.startswith(("#", "--hash=")):
                continue
            try:
                requirement = Requirement(line.removesuffix("\\").strip())
            except InvalidRequirement as exc:
                raise ValueError(f"{path}:{number}: invalid locked requirement") from exc
            specifiers = list(requirement.specifier)
            if (
                requirement.url
                or requirement.extras
                or len(specifiers) != 1
                or specifiers[0].operator != "=="
                or "*" in specifiers[0].version
            ):
                raise ValueError(f"{path}:{number}: expected an exact package==version pin")
            # Removing markers is intentional. Multiple versions of a package
            # are independent advisory queries, not a set to install together.
            pins.add(f"{canonicalize_name(requirement.name)}=={specifiers[0].version}")
            count += 1
        if not count:
            raise ValueError(f"{path}: dependency lock is empty")
    if not pins:
        raise ValueError("No dependency locks were provided")
    return sorted(pins)


def main(argv: Sequence[str] | None = None) -> int:
    import tempfile

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("locks", nargs="*", type=Path)
    parser.add_argument("--output", type=Path, default=Path("dependency-audit.json"))
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    try:
        pins = collect_pins(args.locks or [root / name for name in LOCKFILES])
        # pip-audit rejects two requirements with the same package name, even
        # with --no-deps. Audit every alternative in a separate name-unique batch.
        batches: list[dict[str, str]] = []
        for pin in pins:
            name = pin.partition("==")[0]
            batch = next((batch for batch in batches if name not in batch), None)
            if batch is None:
                batch = {}
                batches.append(batch)
            batch[name] = pin
        print(
            f"Auditing {len(pins)} unique package versions across all lockfile markers",
            flush=True,
        )
        dependencies: list[dict[str, object]] = []
        fixes: list[dict[str, object]] = []
        status = 0
        with tempfile.TemporaryDirectory(prefix="pinak-lock-audit-") as temporary:
            for index, batch in enumerate(batches):
                requirements = Path(temporary) / f"pins-{index}.txt"
                report_path = Path(temporary) / f"audit-{index}.json"
                requirements.write_text("\n".join(batch.values()) + "\n", encoding="utf-8")
                result = subprocess.run(  # nosec B603
                    [
                        sys.executable,
                        "-m",
                        "pip_audit",
                        "--no-deps",
                        "--disable-pip",
                        "--strict",
                        "-r",
                        str(requirements),
                        "--format=json",
                        "--output",
                        str(report_path),
                    ],
                    check=False,
                    timeout=600,
                )
                if result.returncode not in (0, 1):
                    raise ValueError(
                        f"Audit batch {index + 1} failed with exit {result.returncode}"
                    )
                report = json.loads(report_path.read_text(encoding="utf-8"))
                entries = report["dependencies"]
                actual = {
                    f"{canonicalize_name(entry['name'])}=={entry['version']}" for entry in entries
                }
                if actual != set(batch.values()) or any(
                    entry.get("skip_reason") for entry in entries
                ):
                    raise ValueError(f"Audit batch {index + 1} did not check every pinned version")
                dependencies.extend(entries)
                fixes.extend(report.get("fixes", []))
                if result.returncode or any(entry.get("vulns") for entry in entries):
                    status = 1
        args.output.write_text(
            json.dumps({"dependencies": dependencies, "fixes": fixes}, indent=2) + "\n",
            encoding="utf-8",
        )
        return status
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
        print(f"Dependency audit failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
