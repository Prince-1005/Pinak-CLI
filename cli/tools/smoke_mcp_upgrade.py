"""Exercise real old/new wheels in disposable venv and optional pipx installations."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import venv
from pathlib import Path

SEED = """
import os
from pinak import history, queue
from pinak.engine import DownloadRequest
history.DB_FILE = os.path.join(os.environ['PINAK_DATA_DIR'], 'history.db')
history.init_db()
job, created = queue.add_job(DownloadRequest.capture('https://example.com/saved', output_dir=os.environ['PINAK_TEST_OUTPUT'], quality='720p', extract_audio=True))
assert job == 1 and created
history.record_download('https://example.com/history')
"""

VERIFY_CORE = """
import os
from pinak import history, queue
history.DB_FILE = os.path.join(os.environ['PINAK_DATA_DIR'], 'history.db')
jobs = queue.list_jobs()
assert len(jobs) == 1 and jobs[0].status == 'queued' and jobs[0].attempts == 0
assert jobs[0].request.quality == '720p' and jobs[0].request.extract_audio
assert len(history.get_history()) == 1
"""

VERIFY_PROTOCOL = """
import os, sys, anyio
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
async def main():
    async with stdio_client(StdioServerParameters(command=sys.executable, args=['-m','pinak.mcp_server','serve'], env=dict(os.environ))) as (r,w), ClientSession(r,w,read_timeout_seconds=15) as session:
        result = await session.initialize()
        assert result.server_info.name == 'Pinak-MCP'
        assert len((await session.list_tools()).tools) == 14
        shown = await session.call_tool('queue_show', {'job_id':1})
        data = shown.structured_content['data']
        assert data['status'] == 'queued' and data['attempts'] == 0
        assert data['options']['quality'] == '720p' and data['options']['extract_audio']
        added = await session.call_tool('queue_add', {'url':'https://example.com/temporary','request_key':'upgrade-add'})
        assert not added.is_error
        removed = await session.call_tool('queue_remove', {'job_ids':[added.structured_content['data']['job_id']], 'request_key':'upgrade-remove'})
        assert not removed.is_error
        jobs = await session.call_tool('queue_list', {})
        assert [job['id'] for job in jobs.structured_content['data']['items']] == [1]
        records = await session.call_tool('history_list', {})
        assert len(records.structured_content['data']['items']) == 1
anyio.run(main)
"""


def run(arguments: list[str], root: Path, environment: dict[str, str]) -> str:
    result = subprocess.run(
        arguments,
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=300,
    )
    if result.returncode:
        raise RuntimeError(
            f"{arguments[:3]} failed ({result.returncode}):\n{result.stdout[-4000:]}\n{result.stderr[-4000:]}"
        )
    return result.stdout


def environment_for(root: Path) -> dict[str, str]:
    environment = {
        key: value
        for key, value in os.environ.items()
        if key != "PYTHONPATH" and not key.startswith(("PINAK_", "PIPX_"))
    }
    output = root / "日本語 downloads"
    policy = root / "policy.json"
    policy.write_text(json.dumps({"default_output_dir": str(output)}), encoding="utf-8")
    environment.update(
        PYTHONUTF8="1",
        PYTHONNOUSERSITE="1",
        PINAK_DATA_DIR=str(root / "state"),
        PINAK_MCP_CONFIG=str(policy),
        PINAK_TEST_OUTPUT=str(output),
    )
    return environment


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--legacy-wheel", type=Path, required=True)
    parser.add_argument("--current-wheel", type=Path, required=True)
    parser.add_argument(
        "--pipx-python", type=Path, help="Optional isolated interpreter with pipx installed"
    )
    args = parser.parse_args()
    legacy, current = args.legacy_wheel.resolve(), args.current_wheel.resolve()
    if not legacy.is_file() or not current.is_file() or legacy == current:
        raise SystemExit("Supply distinct existing pre-MCP and current wheel files")
    with tempfile.TemporaryDirectory(prefix="pinak-upgrade-smoke-") as temporary:
        root = Path(temporary).resolve()
        ordinary = root / "ordinary"
        ordinary.mkdir()
        environment = environment_for(ordinary)
        venv.create(ordinary / "venv", with_pip=True)
        python = str(
            ordinary / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        )
        run([python, "-m", "pip", "install", str(legacy)], ordinary, environment)
        run([python, "-c", SEED], ordinary, environment)
        run(
            [python, "-m", "pip", "install", "--force-reinstall", str(current) + "[mcp]"],
            ordinary,
            environment,
        )
        run([python, "-c", VERIFY_PROTOCOL], ordinary, environment)
        run(
            [python, "-m", "pip", "install", "--force-reinstall", "--no-deps", str(legacy)],
            ordinary,
            environment,
        )
        run([python, "-c", VERIFY_CORE], ordinary, environment)
        run(
            [python, "-m", "pip", "install", "--force-reinstall", "--no-deps", str(current)],
            ordinary,
            environment,
        )
        run([python, "-c", VERIFY_PROTOCOL], ordinary, environment)
        run([python, "-m", "pip", "check"], ordinary, environment)
        print(
            "Venv: actual pre-MCP upgrade, compatible core downgrade, re-upgrade and durable receipt replay passed",
            flush=True,
        )
        if args.pipx_python:
            pipx_root = root / "pipx"
            pipx_root.mkdir()
            environment = environment_for(pipx_root)
            environment.update(
                PIPX_HOME=str(pipx_root / "home"),
                PIPX_BIN_DIR=str(pipx_root / "bin"),
                PIPX_MAN_DIR=str(pipx_root / "man"),
                PIPX_LOG_DIR=str(pipx_root / "logs"),
            )
            command = [str(args.pipx_python.resolve()), "-m", "pipx"]
            version = run([*command, "--version"], pipx_root, environment).strip()
            run(
                [*command, "install", "--python", sys.executable, str(legacy)],
                pipx_root,
                environment,
            )
            python = str(
                pipx_root
                / "home"
                / "venvs"
                / "pinak-cli"
                / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            )
            run([python, "-c", SEED], pipx_root, environment)
            run(
                [
                    *command,
                    "install",
                    "--force",
                    str(current) + "[mcp]",
                ],
                pipx_root,
                environment,
            )
            run([python, "-c", VERIFY_PROTOCOL], pipx_root, environment)
            run([*command, "reinstall", "pinak-cli"], pipx_root, environment)
            run([python, "-c", VERIFY_PROTOCOL], pipx_root, environment)
            run([*command, "upgrade", "pinak-cli"], pipx_root, environment)
            run([python, "-c", VERIFY_PROTOCOL], pipx_root, environment)
            metadata = json.loads(run([*command, "list", "--json"], pipx_root, environment))
            main_package = metadata["venvs"]["pinak-cli"]["metadata"]["main_package"]
            assert "mcp" in main_package["package_or_url"]
            assert any(Path(app).stem == "pinak-mcp" for app in main_package["apps"]), main_package[
                "apps"
            ]
            print(
                f"pipx {version}: old-core to MCP upgrade, reinstall/upgrade with extras retained, stdio and durable state passed",
                flush=True,
            )


if __name__ == "__main__":
    main()
