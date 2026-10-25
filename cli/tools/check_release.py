"""Reject release tags, dispatch inputs, or version files that disagree."""

from __future__ import annotations

import ast
import json
import os
import sys
import tomllib
from pathlib import Path


def validate_release(root: Path, event: str, tag: str = "", requested_version: str = "") -> str:
    project = tomllib.loads((root / "cli/pyproject.toml").read_text(encoding="utf-8"))
    version = project["project"]["version"]
    manifest = json.loads((root / ".release-please-manifest.json").read_text(encoding="utf-8"))
    tree = ast.parse((root / "cli/pinak/__init__.py").read_text(encoding="utf-8"))
    package_version = next(
        (
            ast.literal_eval(node.value)
            for node in tree.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "__version__"
                for target in node.targets
            )
        ),
        None,
    )
    if not version or manifest.get("cli") != version or package_version != version:
        raise ValueError("pyproject.toml, pinak.__version__, and release manifest must agree")
    if event == "release":
        if tag != f"v{version}":
            raise ValueError(f"Release tag must be v{version}; received {tag!r}")
    elif event == "workflow_dispatch":
        if requested_version != version:
            raise ValueError(f"Requested version must be {version}; received {requested_version!r}")
    else:
        raise ValueError(f"Unsupported publishing event: {event!r}")
    return str(version)


def main() -> int:
    try:
        version = validate_release(
            Path(__file__).resolve().parents[2],
            os.environ.get("GITHUB_EVENT_NAME", ""),
            os.environ.get("RELEASE_TAG", ""),
            os.environ.get("REQUESTED_VERSION", ""),
        )
    except (OSError, ValueError, KeyError, SyntaxError) as exc:
        print(f"Release validation failed: {exc}", file=sys.stderr)
        return 1
    print(f"Release version validated: {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
