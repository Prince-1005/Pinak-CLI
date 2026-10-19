"""Verify an actual running cloud image through the official remote MCP client."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
import urllib.request

import anyio
import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


def docker(*arguments: str) -> str:
    return subprocess.check_output(["docker", *arguments], text=True).strip()  # nosec B603 B607


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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--container", required=True)
    parser.add_argument("--url", required=True)
    args = parser.parse_args()
    wait_health(args.url)
    tokens = {}
    for name in ("alice", "bob"):
        output = docker(
            "exec", args.container, "python", "-m", "pinak.mcp_cloud", "users", "add", name
        )
        tokens[name] = json.loads(output)["token"]
    # Inspect the service process, not docker-exec's administrative identity.
    uid = docker(
        "exec",
        args.container,
        "python",
        "-c",
        "import psutil; p=next(p for p in psutil.process_iter() if p.cmdline()[1:3]==['-m','pinak.mcp_cloud'] and 'serve' in p.cmdline()); print(p.uids().real)",
    )
    assert uid == "10001", uid
    anyio.run(exercise, args.url, tokens["alice"], tokens["bob"])
    docker("restart", "--time", "40", args.container)
    wait_health(args.url)

    async def check_persistence() -> None:
        await exercise(args.url, tokens["alice"], tokens["bob"], existing=True)

    anyio.run(check_persistence)
    print(
        "Cloud image: non-root service, remote SDK, 15 tools, user isolation and restart persistence passed"
    )


if __name__ == "__main__":
    main()
