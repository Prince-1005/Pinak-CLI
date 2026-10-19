"""Remote transport, credentials, isolated real adapters, and file capabilities."""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import socket
import tarfile
import threading
import time
import wave
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import anyio
import httpx2
import psutil
import pytest
import uvicorn
from filelock import Timeout
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from starlette.testclient import TestClient

from pinak.mcp_cloud import egress
from pinak.mcp_cloud.app import create_app
from pinak.mcp_cloud.egress import public_connection
from pinak.mcp_cloud.registry import Registry
from pinak.mcp_cloud.settings import Settings


def settings(root: Path, **kwargs: object) -> Settings:
    return Settings(data_dir=root, public_url="https://pinak.example", **kwargs)


def test_configuration_requires_secure_origin(tmp_path: Path) -> None:
    for url in ("http://cloud.example", "https://a.example/path", "https://user:pw@a.example"):
        with pytest.raises(ValueError):
            Settings(data_dir=tmp_path, public_url=url)
    assert Settings(
        data_dir=tmp_path, public_url="http://127.0.0.1:8123", allow_insecure_loopback=True
    )


def test_credentials_and_links(tmp_path: Path) -> None:
    registry = Registry(settings(tmp_path))
    token = registry.create("alice")
    assert registry.authenticate(token) == "alice"
    assert registry.authenticate("wrong") is None
    assert token.encode() not in registry.path.read_bytes()
    with pytest.raises(ValueError):
        registry.create("../bob")
    root = registry.root("alice") / "downloads"
    root.mkdir(parents=True)
    path = root / "song.wav"
    path.write_bytes(b"song")
    link = registry.issue_link("alice", path)
    capability = str(link["url"]).rsplit("/", 1)[1]
    assert registry.resolve_link(capability) == path
    registry.rotate("alice")
    assert registry.authenticate(token) is None
    assert registry.resolve_link(capability) is None
    link = registry.issue_link("alice", path)
    capability = str(link["url"]).rsplit("/", 1)[1]
    with registry.connect() as db:
        db.execute("UPDATE links SET expires=?", (time.time() - 1,))
    assert registry.resolve_link(capability) is None
    with pytest.raises(ValueError):
        registry.issue_link("alice", registry.path)
    link = registry.issue_link("alice", path)
    path.write_bytes(b"changed")
    assert registry.resolve_link(str(link["url"]).rsplit("/", 1)[1]) is None


@pytest.mark.parametrize("host", ["127.0.0.1", "169.254.169.254", "::1", "10.0.0.1"])
def test_proxy_rejects_private_targets(host: str) -> None:
    with pytest.raises(ValueError, match="Nonpublic"):
        asyncio.run(public_connection(host, 80))


def rpc(client: TestClient, token: str, method: str, params: dict[str, object]) -> dict:
    response = client.post(
        "/mcp",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": "2025-11-25",
        },
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert "error" not in body, body
    return body["result"]


def call(client: TestClient, token: str, name: str, **arguments: object) -> dict:
    result = rpc(client, token, "tools/call", {"name": name, "arguments": arguments})
    return result["structuredContent"]


def test_remote_users_and_download_capability(tmp_path: Path) -> None:
    config = settings(tmp_path)
    registry = Registry(config)
    alice, bob = registry.create("alice"), registry.create("bob")
    with TestClient(create_app(config), base_url=config.public_url) as client:
        assert client.get("/healthz").status_code == 200
        assert client.post("/mcp").status_code == 401
        assert client.get("/mcp", headers={"Host": "evil.example"}).status_code == 403
        assert client.post("/mcp", headers={"Origin": "https://evil.example"}).status_code == 403
        discovered = rpc(client, alice, "tools/list", {})
        assert len(discovered["tools"]) == 15
        info = call(client, alice, "server_info")
        assert info["data"]["transport"] == "streamable-http", info
        assert call(client, alice, "_cloud_shutdown")["error"]["code"] == "UNKNOWN_TOOL"
        assert call(client, alice, "server_info")["ok"]
        for token in (alice, bob):
            added = call(
                client, token, "queue_add", url="https://example.com/test.mp4", request_key="first"
            )
            assert added["ok"], added
            assert added["data"]["job_id"] == 1
        assert call(client, alice, "queue_list")["data"]["items"][0]["id"] == 1
        denied = call(
            client,
            alice,
            "queue_add",
            url="http://169.254.169.254/latest/meta-data",
            request_key="private",
        )
        assert denied["error"]["code"] == "URL_DENIED"
        denied = call(
            client,
            alice,
            "queue_add",
            url="https://example.com/a",
            request_key="escape",
            options={"output_dir": str(tmp_path / "users/bob/downloads")},
        )
        assert denied["error"]["code"] == "PATH_DENIED"
        assert not call(client, bob, "queue_show", job_id=2)["ok"]
        assert not call(client, alice, "file_link", job_id=1)["ok"]

        # A completed-file fixture exercises HTTP delivery, ranges and token revocation.
        output = registry.root("alice") / "downloads" / "sample.wav"
        output.write_bytes(b"0123456789")
        link = registry.issue_link("alice", output)
        route = "/files/" + str(link["url"]).rsplit("/", 1)[1]
        response = client.get(route)
        assert response.content == b"0123456789"
        assert response.headers["cache-control"] == "no-store"
        partial = client.get(route, headers={"Range": "bytes=2-4"})
        assert partial.status_code == 206 and partial.content == b"234"
        registry.rotate("alice", revoke=True)
        assert client.get(route).status_code == 404
        assert client.post("/mcp", headers={"Authorization": f"Bearer {alice}"}).status_code == 401
        assert call(client, bob, "queue_list")["ok"]
    assert (registry.root("alice") / "state/history.db").is_file()
    assert (registry.root("bob") / "state/history.db").is_file()
    assert hashlib.sha256(alice.encode()).hexdigest() not in json.dumps(registry.list_users())


def test_actual_remote_download_reconnect_and_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "fixture"
    source.mkdir()
    with wave.open(str(source / "sample.wav"), "wb") as audio:
        audio.setparams((1, 2, 8000, 0, "NONE", "not compressed"))
        audio.writeframes(b"\x00\x01" * 8000)

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args: object, **kwargs: object) -> None:
            super().__init__(*args, directory=str(source), **kwargs)

        def log_message(self, *_args: object) -> None:
            pass

        def do_GET(self) -> None:
            if self.path == "/private.wav":
                self.send_response(302)
                self.send_header("Location", "http://169.254.169.254/latest/meta-data")
                self.end_headers()
            else:
                super().do_GET()

        def do_HEAD(self) -> None:
            if self.path == "/private.wav":
                self.do_GET()
            else:
                super().do_HEAD()

    fixture = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=fixture.serve_forever, daemon=True)
    thread.start()
    original = egress.public_connection
    targets: list[str] = []

    async def fixture_connection(
        host: str, port: int
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        targets.append(host)
        # Only test wiring maps the synthetic public source to the local fixture.
        if host == "fixture.example" and port == 80:
            return await asyncio.open_connection("127.0.0.1", fixture.server_port)
        return await original(host, port)

    monkeypatch.setattr(egress, "public_connection", fixture_connection)
    config = settings(tmp_path / "cloud", calls_per_minute=10000)
    registry = Registry(config)
    token = registry.create("alice")
    try:
        with TestClient(create_app(config), base_url=config.public_url) as client:
            job = call(
                client,
                token,
                "queue_add",
                url="http://fixture.example/sample.wav",
                request_key="real-add",
            )
            assert job["ok"], job
            started = call(client, token, "queue_start", request_key="real-start")
            assert started["ok"], started
            run_id = started["data"]["run_id"]
            # A new HTTP client has no session ownership or process lifetime authority.
            client.cookies.clear()
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                status = call(client, token, "queue_run_status", run_id=run_id)
                assert status["ok"], status
                if status["data"]["state"] not in {"starting", "running", "stopping"}:
                    break
                time.sleep(0.05)
            assert status["data"]["summary"]["succeeded"] == 1, status
            linked = call(client, token, "file_link", job_id=job["data"]["job_id"])
            assert linked["ok"], linked
            route = "/files/" + linked["data"]["url"].rsplit("/", 1)[1]
            delivered = client.get(route).content
            with wave.open(io.BytesIO(delivered), "rb") as downloaded:
                assert downloaded.readframes(8000) == b"\x00\x01" * 8000
            blocked = call(
                client,
                token,
                "queue_add",
                url="http://fixture.example/private.wav",
                request_key="redirect",
            )
            assert blocked["ok"]
            redirected = call(client, token, "queue_start", request_key="redirect-run")
            assert redirected["ok"]
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                state = call(client, token, "queue_run_status", run_id=redirected["data"]["run_id"])
                if state["data"]["state"] not in {"starting", "running", "stopping"}:
                    break
                time.sleep(0.05)
            assert state["data"]["summary"]["failed"] == 1, state
            assert "169.254.169.254" in targets, targets
        with TestClient(create_app(config), base_url=config.public_url) as client:
            shown = call(client, token, "queue_show", job_id=job["data"]["job_id"])
            assert shown["data"]["status"] == "succeeded"
            assert call(client, token, "history_list")["data"]["items"]
            assert client.get(route).content == delivered
    finally:
        fixture.shutdown()
        fixture.server_close()
        thread.join(timeout=5)


def test_official_sdk_over_real_http(tmp_path: Path) -> None:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    config = Settings(
        data_dir=tmp_path, public_url=f"http://127.0.0.1:{port}", allow_insecure_loopback=True
    )
    registry = Registry(config)
    alice, bob = registry.create("alice"), registry.create("bob")
    server = uvicorn.Server(
        uvicorn.Config(create_app(config), log_level="critical", access_log=False)
    )
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.05)
    assert server.started

    async def exercise() -> None:
        for token, name in ((alice, "alice"), (bob, "bob")):
            async with (
                httpx2.AsyncClient(headers={"Authorization": f"Bearer {token}"}) as http,
                streamable_http_client(config.public_url + "/mcp", http_client=http) as streams,
                ClientSession(*streams) as session,
            ):
                await session.initialize()
                assert len((await session.list_tools()).tools) == 15
                result = await session.call_tool("server_info", {})
                assert result.structured_content["data"]["cloud_user"] == name

    try:
        anyio.run(exercise)
    finally:
        server.should_exit = True
        thread.join(timeout=30)
        sock.close()
    assert not thread.is_alive(), "Gateway failed to shut down cleanly"


def test_http_rate_and_body_limits(tmp_path: Path) -> None:
    config = settings(tmp_path, calls_per_minute=1)
    registry = Registry(config)
    token = registry.create("alice")
    with TestClient(create_app(config), base_url=config.public_url) as client:
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            "MCP-Protocol-Version": "2025-11-25",
        }
        response = client.post("/mcp", headers=headers, content=b" " * 65537)
        assert response.status_code == 413
        response = client.post("/mcp", headers=headers, json={})
        assert response.status_code == 429


def test_quota_admission_preserves_replay_and_inspection(tmp_path: Path) -> None:
    config = settings(tmp_path, max_jobs=1, storage_bytes=1024**2)
    registry = Registry(config)
    token = registry.create("alice")
    with TestClient(create_app(config), base_url=config.public_url) as client:
        args = {"url": "https://example.com/a.wav", "request_key": "one"}
        first = call(client, token, "queue_add", **args)
        assert first["ok"]
        assert call(client, token, "queue_add", **args) == first
        full = call(client, token, "queue_add", url="https://example.com/b.wav", request_key="two")
        assert full["error"]["code"] == "JOB_LIMIT"
        output = registry.root("alice") / "downloads" / "full.bin"
        output.write_bytes(b"x" * 1024**2)
        assert call(client, token, "queue_add", **args) == first
        denied = call(client, token, "queue_start", request_key="full-start")
        assert denied["error"]["code"] == "STORAGE_LIMIT"
        assert call(client, token, "queue_show", job_id=1)["ok"]
        assert call(client, token, "queue_remove", job_ids=[1], request_key="remove")["ok"]


def test_operator_cli_and_sdk_compatibility(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from pinak.mcp_cloud import __main__ as cli

    monkeypatch.setenv("PINAK_CLOUD_DATA", str(tmp_path))
    monkeypatch.setenv("PINAK_CLOUD_URL", "https://pinak.example")
    monkeypatch.setattr("sys.argv", ["pinak-mcp-cloud", "users", "add", "alice"])
    assert cli.main() == 0
    token = json.loads(capsys.readouterr().out)["token"]
    assert Registry(Settings.from_env()).authenticate(token) == "alice"
    assert cli.main() == 2
    assert "registry operation failed" in capsys.readouterr().err
    monkeypatch.setattr("sys.argv", ["pinak-mcp-cloud", "users", "revoke", "alice"])
    assert cli.main() == 0
    assert Registry(Settings.from_env()).authenticate(token) is None
    capsys.readouterr()
    monkeypatch.setattr("sys.argv", ["pinak-mcp-cloud", "serve"])
    monkeypatch.setattr(cli.importlib.metadata, "version", lambda _: "unsupported")
    assert cli.main() == 2
    assert "SDK 2.3.0" in capsys.readouterr().err


def test_adapter_crash_recovery_and_revocation_shutdown(tmp_path: Path) -> None:
    config = settings(tmp_path)
    registry = Registry(config)
    alice, bob = registry.create("alice"), registry.create("bob")
    with TestClient(create_app(config), base_url=config.public_url) as client:
        assert call(
            client, alice, "queue_add", url="https://example.com/a.wav", request_key="persist"
        )["ok"]
        assert call(client, bob, "server_info")["ok"]

        def owned_adapter() -> psutil.Process:
            matches = []
            for process in psutil.Process().children(recursive=True):
                try:
                    if process.cmdline()[-1:] == ["pinak.mcp_cloud.tenant"] and Path(
                        process.cwd()
                    ) == registry.root("alice"):
                        matches.append(process)
                except psutil.NoSuchProcess:
                    pass
            # Windows venv launchers can retain a same-command wrapper parent.
            parent_ids = {process.ppid() for process in matches}
            leaves = [process for process in matches if process.pid not in parent_ids]
            assert len(leaves) == 1
            return leaves[0]

        process = owned_adapter()
        process.kill()  # Verified test-owned child with exact module and isolated cwd.
        process.wait(timeout=5)
        failed = call(client, alice, "queue_list")
        assert failed["error"]["code"] == "ADAPTER_UNAVAILABLE"
        recovered = call(client, alice, "queue_list")
        assert recovered["ok"] and len(recovered["data"]["items"]) == 1
        assert call(client, bob, "queue_list")["ok"]
        replacement = owned_adapter()
        registry.rotate("alice", revoke=True)
        replacement.wait(timeout=15)
        assert call(client, bob, "server_info")["ok"]


def test_gateway_rejects_second_supervisor(tmp_path: Path) -> None:
    config = settings(tmp_path)
    with TestClient(create_app(config), base_url=config.public_url) as first:
        with pytest.raises(Timeout), TestClient(create_app(config), base_url=config.public_url):
            pass
        assert first.get("/healthz").status_code == 200


def test_quiesced_backup_restore_rehearsal(tmp_path: Path) -> None:
    config = settings(tmp_path / "data")
    registry = Registry(config)
    token = registry.create("alice")
    with TestClient(create_app(config), base_url=config.public_url) as client:
        assert call(
            client, token, "queue_add", url="https://example.com/a.wav", request_key="backup"
        )["ok"]
        media = registry.root("alice") / "downloads" / "keep.bin"
        media.write_bytes(b"preserved media")
    archive_path = tmp_path / "backup.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        archive.add(config.data_dir, arcname=".")
    registry.rotate("alice", revoke=True)
    assert registry.authenticate(token) is None
    registry.path.unlink()
    media.unlink()
    (registry.root("alice") / "state/history.db").unlink()
    # Restore only regular files from this test-created archive to the same
    # absolute data root, as the container's /data restoration procedure requires.
    with tarfile.open(archive_path, "r:gz") as archive:
        for member in archive:
            if member.isfile():
                target = (config.data_dir / member.name).resolve()
                assert target.is_relative_to(config.data_dir)
                source = archive.extractfile(member)
                assert source is not None
                with source:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(source.read())
    with TestClient(create_app(config), base_url=config.public_url) as client:
        assert len(call(client, token, "queue_list")["data"]["items"]) == 1
        assert media.read_bytes() == b"preserved media"
    # A restored registry also restores old credentials: operators must rotate.
    Registry(config).rotate("alice")
    assert Registry(config).authenticate(token) is None
