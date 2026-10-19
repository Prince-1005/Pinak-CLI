"""Build a self-contained cloud deployment bundle around a verified wheel."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import zipfile
from pathlib import Path

from package_mcp import prepare

TEMPLATES = (
    ".dockerignore",
    ".env.example",
    ".gitignore",
    "Caddyfile",
    "Dockerfile",
    "client.template.json",
    "compose.yaml",
    "entrypoint.sh",
    "render.yaml",
)


def write_archive(output: Path, archive: Path) -> None:
    if archive.resolve().is_relative_to(output.resolve()):
        raise ValueError("Archive must be outside the installer folder")
    archive.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as zipped:
        for path in sorted(output.iterdir()):
            if path.is_file():
                zipped.write(path, arcname=path.name)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dist", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--archive", type=Path, help="Optional new ZIP outside the output folder")
    args = parser.parse_args()
    wheels = list(args.dist.glob("*.whl"))
    if len(wheels) != 1:
        raise ValueError("Expected exactly one application wheel")
    with zipfile.ZipFile(wheels[0]) as archive:
        if "pinak/mcp_cloud/app.py" not in archive.namelist():
            raise ValueError("Wheel does not contain the cloud server")
    root = Path(__file__).resolve().parents[2]
    docs = root / "MCP(cloud)"
    info = prepare(wheels[0], args.output, args.source_revision)
    for path in docs.glob("*.md"):
        contents = path.read_text(encoding="utf-8").replace(
            "(<../MCP(Local)/README.md>)",
            "(https://github.com/Prince-1005/Pinak-CLI/blob/main/MCP%28Local%29/README.md)",
        )
        (args.output / path.name).write_text(contents, encoding="utf-8", newline="\n")
    # Never accidentally distribute an ignored local .env or credential file.
    for name in TEMPLATES:
        shutil.copy2(docs / "examples" / name, args.output / name)
    shutil.copy2(root / "cli/requirements-cloud-lock.txt", args.output)
    info.update(install_extra="cloud", transport="streamable-http", deployment="user-operated")
    (args.output / "BUILD-INFO.json").write_text(
        json.dumps(info, indent=2) + "\n", encoding="utf-8"
    )
    (args.output / "INSTALL.md").write_text(
        "# Install Pinak-MCP Cloud\n\nVerify SHA256SUMS, then follow DEPLOY_VPS.md or DEPLOY_RENDER.md.\n"
        "The application wheel and hashed dependency lock are included. Docker downloads\n"
        "its base image, system packages and Python dependencies during the build.\n"
        "No Pinak repository checkout is needed. You operate your own hosting account.\n",
        encoding="utf-8",
    )
    lines = [
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}"
        for path in sorted(args.output.iterdir())
        if path.name != "SHA256SUMS"
    ]
    (args.output / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")
    if args.archive:
        write_archive(args.output, args.archive)
    print(json.dumps(info, indent=2))


if __name__ == "__main__":
    main()
