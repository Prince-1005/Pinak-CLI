"""Verify an actual running cloud image through the official remote MCP client."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
import time
import urllib.request
import uuid
from pathlib import Path
from urllib.parse import urlsplit

import anyio
import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


def docker(*arguments: str) -> str:
    command = ["docker", *arguments]
    output = subprocess.check_output(command, text=True, timeout=120)  # nosec B603 B607
    return output.strip()


def wait_health(url: str) -> None:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            # The URL is supplied by the operator running this isolated smoke check.
            endpoint = url + "/healthz"
            with urllib.request.urlopen(endpoint, timeout=2) as response:  # nosec B310
                if response.status == 200:
                    return
        except OSError:
            time.sleep(0.2)
    raise RuntimeError("Cloud container did not become healthy")


async def exercise(url: str, alice: str, bob: str, *, existing: bool = False) -> None:
    async def inspect(token: str, username: str) -> None:
        async with (
            httpx2.AsyncClient(headers={"Authorization": f"Bearer {token}"}) as http,
            streamable_http_client(url + "/mcp", http_client=http) as streams,
            ClientSession(*streams) as session,
        ):
            await session.initialize()
            assert len((await session.list_tools()).tools) == 15
            info = await session.call_tool("server_info", {})
            assert info.structured_content["data"]["cloud_user"] == username
            if username == "alice":
                result = await session.call_tool(
                    "queue_add",
                    {"url": "https://example.com/demo.mp4", "request_key": "container-add"},
                )
                assert result.structured_content["ok"], result
                assert result.structured_content["data"]["job_id"] == 1
            jobs = await session.call_tool("queue_list", {})
            assert len(jobs.structured_content["data"]["items"]) == (
                1 if username == "alice" else 0
            )
            if existing:
                assert username == "alice"

    await inspect(alice, "alice")
    if not existing:
        await inspect(bob, "bob")


def check_container(container: str, url: str) -> None:
    wait_health(url)
    tokens = {}
    for name in ("alice", "bob"):
        output = docker("exec", container, "python", "-m", "pinak.mcp_cloud", "users", "add", name)
        tokens[name] = json.loads(output)["token"]
    # Inspect the service process, not docker-exec's administrative identity.
    uid = docker(
        "exec",
        container,
        "python",
        "-c",
        "import psutil; p=next(p for p in psutil.process_iter() if p.cmdline()[1:3]==['-m','pinak.mcp_cloud'] and 'serve' in p.cmdline()); print(p.uids().real)",
    )
    assert uid == "10001", uid
    anyio.run(exercise, url, tokens["alice"], tokens["bob"])
    docker("restart", "--time", "40", container)
    wait_health(url)

    async def check_persistence() -> None:
        await exercise(url, tokens["alice"], tokens["bob"], existing=True)

    anyio.run(check_persistence)
    print(
        "Cloud image: non-root service, remote SDK, 15 tools, user isolation and restart persistence passed"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--container")
    target.add_argument("--compose-dir", type=Path)
    parser.add_argument("--url", required=True)
    parser.add_argument("--image", default="pinak-cloud-check")
    args = parser.parse_args()
    if args.container:
        check_container(args.container, args.url)
        return
    endpoint = urlsplit(args.url)
    if endpoint.scheme != "http" or endpoint.hostname != "127.0.0.1" or not endpoint.port:
        raise ValueError("Compose smoke verification requires an explicit loopback HTTP port")
    with tempfile.TemporaryDirectory(prefix="pinak-cloud-compose-") as temporary:
        root = Path(temporary)
        for name in ("compose.yaml", "Caddyfile"):
            shutil.copy2(args.compose_dir / name, root / name)
        shutil.copy2(args.compose_dir / ".env.example", root / ".env")
        overrides = {
            "services": {
                "app": {
                    "image": args.image,
                    "ports": [f"127.0.0.1:{endpoint.port}:8000"],
                    "environment": {"PINAK_CLOUD_URL": args.url, "PINAK_CLOUD_TEST_LOOPBACK": "1"},
                }
            }
        }
        (root / "override.json").write_text(json.dumps(overrides), encoding="utf-8")
        compose = (
            "compose",
            "--project-name",
            "pinak-check-" + uuid.uuid4().hex[:8],
            "--project-directory",
            str(root),
            "--file",
            str(root / "compose.yaml"),
            "--file",
            str(root / "override.json"),
        )
        try:
            docker(*compose, "up", "--detach", "--no-build", "app")
            container = docker(*compose, "ps", "--quiet", "app")
            check_container(container, args.url)
        except BaseException:
            print(docker(*compose, "logs", "--no-color", "--tail", "100", "app"))
            raise
        finally:
            docker(*compose, "down", "--volumes")


if __name__ == "__main__":
    main()
