"""Install the newly built wheel in an isolated environment and exercise imports/CLI."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import venv
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", nargs="?", default="release-dist")
    parser.add_argument("--check-playback-imports", action="store_true")
    args = parser.parse_args()
    directory = Path(args.directory).resolve()
    wheels = list(directory.glob("*.whl"))
    if len(wheels) != 1:
        raise SystemExit("Use a fresh build directory containing exactly one wheel")
    with tempfile.TemporaryDirectory(prefix="pinak-wheel-smoke-") as temporary:
        root = Path(temporary)
        venv.create(root, with_pip=True)
        python = root / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        env = {
            k: v for k, v in os.environ.items() if k != "PYTHONPATH" and not k.startswith("PINAK_")
        }
        env["PYTHONNOUSERSITE"] = "1"
        env["PYTHONUTF8"] = "1"
        # Older Python ensurepip bundles can seed vulnerable bootstrap tools.
        # Upgrade them rather than excluding their advisories from the audit.
        subprocess.run(
            [str(python), "-m", "pip", "install", "--upgrade", "pip>=26.2.1", "setuptools>=83.0.0"],
            cwd=root,
            env=env,
            check=True,
            timeout=300,
        )
        subprocess.run(
            [str(python), "-m", "pip", "install", str(wheels[0])],
            cwd=root,
            env=env,
            check=True,
            timeout=300,
        )
        subprocess.run(
            [str(python), "-c", "import pinak.commands.media; import pinak.media.ipc.server"],
            cwd=root,
            env=env,
            check=True,
            timeout=30,
        )
        if args.check_playback_imports:
            subprocess.run(
                [
                    str(python),
                    "-c",
                    "import sounddevice; import tkinter; print('Playback imports passed')",
                ],
                cwd=root,
                env=env,
                check=True,
                timeout=30,
            )
        subprocess.run(
            [str(python), "-m", "pinak", "--help"],
            cwd=root,
            env=env,
            check=True,
            capture_output=True,
            timeout=30,
        )
        version = subprocess.run(
            [str(python), "-m", "pinak", "--version"],
            cwd=root,
            env=env,
            check=True,
            timeout=30,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        assert wheels[0].name.split("-")[1] in version.stdout, version.stdout
        result = subprocess.run(
            [str(python), "-m", "pinak", "https://example.com/clip.mp4", "--dry-run", "--json"],
            cwd=root,
            env=env,
            check=True,
            timeout=30,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        assert isinstance(json.loads(result.stdout), dict)
        subprocess.run(
            [str(python), "-m", "pip", "check"], cwd=root, env=env, check=True, timeout=30
        )
        installed = subprocess.run(
            [str(python), "-m", "pip", "list", "--format=json"],
            cwd=root,
            env=env,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )
        requirements = root / "installed-runtime.txt"
        requirements.write_text(
            "\n".join(
                f"{package['name']}=={package['version']}"
                for package in json.loads(installed.stdout)
                if package["name"] != "pinak-cli"
            ),
            encoding="utf-8",
        )
        # Audit the resolver's actual wheel environment, which may differ from
        # the development lock. The first-party package is checked as source.
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip_audit",
                "-r",
                str(requirements),
                "--no-deps",
                "--disable-pip",
                "--strict",
                "--format=json",
                "--output",
                str(Path.cwd() / ".audit-wheel-dependencies.json"),
            ],
            check=True,
            timeout=300,
        )
        print(
            "Clean wheel imports, version, JSON, dependency consistency and advisory audit passed"
        )


if __name__ == "__main__":
    main()
