"""Prepare a wheel-only MCP installer bundle; users do not need the repository."""

from __future__ import annotations

import argparse
import configparser
import hashlib
import json
import shutil
import zipfile
from email.parser import BytesParser
from pathlib import Path


def prepare(wheel: Path, output: Path, revision: str) -> dict[str, object]:
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        metadata_files = [name for name in names if name.endswith(".dist-info/METADATA")]
        if len(metadata_files) != 1:
            raise ValueError("Expected exactly one wheel metadata file")
        metadata_path = metadata_files[0]
        prefix = metadata_path.rsplit("/", 1)[0] + "/"
        if any(not name.startswith(("pinak/", prefix)) for name in names):
            raise ValueError("Wheel contains files outside the Pinak runtime and package metadata")
        required = ["__init__.py", "engine.py", "queue.py", "history.py", "mcp_server/__main__.py"]
        if any("pinak/" + name not in names for name in required):
            raise ValueError("Wheel is missing the MCP server or shared download engine")
        metadata = BytesParser().parsebytes(archive.read(metadata_path))
        if metadata["Name"] != "pinak-cli" or "mcp" not in metadata.get_all("Provides-Extra", []):
            raise ValueError("Expected pinak-cli with the MCP optional dependency")
        entries = configparser.ConfigParser()
        entries.read_string(archive.read(prefix + "entry_points.txt").decode())
        if entries["console_scripts"].get("pinak-mcp") != "pinak.mcp_server.__main__:main":
            raise ValueError("Wheel does not provide the pinak-mcp executable")
    # Refuse stale bundles rather than publishing leftovers from a previous build.
    output.mkdir(parents=True, exist_ok=False)
    shutil.copy2(wheel, output / wheel.name)
    information: dict[str, object] = {
        "package": metadata["Name"],
        "version": metadata["Version"],
        "source_revision": revision,
        "wheel": wheel.name,
        "wheel_bytes": wheel.stat().st_size,
        "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
        "install_extra": "mcp",
        "transport": "stdio",
    }
    (output / "BUILD-INFO.json").write_text(
        json.dumps(information, indent=2) + "\n", encoding="utf-8"
    )
    version = metadata["Version"]
    (output / "INSTALL.md").write_text(
        f"""# Install Pinak-MCP without cloning the repository

Package version: {version}. Source revision: {revision}.
This bundle contains the application wheel, instructions and checksums only.
It includes Pinak's shared engine/CLI because the MCP adapter uses that engine.
Website media, repository history, tests and planning files are not included.

Requirements: Python 3.10+ and an AI application supporting local stdio MCP.
Internet access is needed for pip dependencies and later media downloads.
Git, Node.js and a repository checkout are unnecessary.

Extract the downloaded ZIP and open a terminal inside the extracted folder.
Keep the environment at a permanent location: the AI client stores its path.

## Windows (PowerShell)

```powershell
python -m venv .venv-mcp
.venv-mcp/Scripts/python.exe -m pip install --upgrade pip
.venv-mcp/Scripts/python.exe -m pip install "./{wheel.name}[mcp]"
.venv-mcp/Scripts/python.exe -m pinak.mcp_server doctor --json
.venv-mcp/Scripts/python.exe -m pinak.mcp_server configure
```

## macOS/Linux

```sh
python3 -m venv .venv-mcp
.venv-mcp/bin/python -m pip install --upgrade pip
.venv-mcp/bin/python -m pip install "./{wheel.name}[mcp]"
.venv-mcp/bin/python -m pinak.mcp_server doctor --json
.venv-mcp/bin/python -m pinak.mcp_server configure
```

If Python reports that venv is unavailable, install your platform's Python venv
support first. Install FFmpeg/FFprobe explicitly for conversion/merging/metadata;
the MCP server does not download them automatically. Review doctor feedback.

Enter the generated command, arguments and environment into the AI application's
local MCP settings, then reload it. Ask it to queue a media URL, start the queue,
and poll download status. Downloaded files default to your Downloads/Pinak folder.
Remote-URL-only AI clients cannot launch this local stdio server.

No Pinak account or hosted service is required. The AI application's provider
may receive prompts and returned metadata; media bytes are not sent by Pinak.

For updates, stop runs, close the host and run prepare-update with this environment's
Python (`-m pinak.mcp_server prepare-update`). Then install the new wheel with
`--force-reinstall` and its `[mcp]` extra. This matters for source builds that share
the same package version. Run doctor and reconnect; resume jobs explicitly.
Do not restore an older database without preserving the current data first.

## Verify the download

BUILD-INFO.json identifies the source and wheel SHA-256. SHA256SUMS covers all
bundle files except itself. On Linux use `sha256sum -c SHA256SUMS`; on macOS use
`shasum -a 256 -c SHA256SUMS`. On Windows use `Get-FileHash -Algorithm SHA256`
with the wheel filename and compare it with SHA256SUMS.
These checks detect changed files; they are not an independent signature.
""",
        encoding="utf-8",
    )
    checksums = "".join(
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n"
        for path in sorted(output.iterdir())
    )
    (output / "SHA256SUMS").write_text(checksums, encoding="utf-8")
    return information


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="Fresh build directory containing one wheel")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-revision", required=True)
    args = parser.parse_args()
    wheels = list(args.directory.glob("*.whl"))
    if len(wheels) != 1:
        parser.error("Expected exactly one wheel in the build directory")
    print(json.dumps(prepare(wheels[0], args.output, args.source_revision), indent=2))


if __name__ == "__main__":
    main()
