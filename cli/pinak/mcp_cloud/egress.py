"""Local download proxy: resolve every target and connect only to public IPs."""

from __future__ import annotations

import asyncio
import contextlib
import ipaddress
import socket
from urllib.parse import urlsplit


async def public_connection(
    host: str, port: int
) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    if port not in {80, 443}:
        raise ValueError("Unsupported destination port")
    loop = asyncio.get_running_loop()
    rows = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    if not rows or any(
        not ipaddress.ip_address(row[4][0]).is_global
        or ipaddress.ip_address(row[4][0]).is_multicast
        for row in rows
    ):
        raise ValueError("Nonpublic destination")
    last: OSError | None = None
    for family, kind, proto, _, address in rows:
        sock = socket.socket(family, kind, proto)
        sock.setblocking(False)
        try:
            await asyncio.wait_for(loop.sock_connect(sock, address), timeout=10)
            return await asyncio.open_connection(sock=sock)
        except OSError as exc:
            last = exc
            sock.close()
        except BaseException:
            sock.close()
            raise
    raise OSError("No reachable public address") from last


class EgressProxy:
    def __init__(self) -> None:
        self.server: asyncio.Server | None = None
        self.connections: set[asyncio.Task[None]] = set()
        self.url = ""

    async def start(self) -> None:
        self.server = await asyncio.start_server(self.accept, "127.0.0.1", 0, limit=65536)
        self.url = f"http://127.0.0.1:{self.server.sockets[0].getsockname()[1]}"

    async def close(self) -> None:
        if self.server:
            self.server.close()
            await self.server.wait_closed()
        tasks = list(self.connections)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def accept(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        task = asyncio.current_task()
        if task is None:
            writer.close()
            return
        if len(self.connections) >= 128:
            writer.close()
            return
        self.connections.add(task)
        upstream: asyncio.StreamWriter | None = None
        try:
            header = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 15)
            lines = header.decode("latin-1").split("\r\n")
            method, target, version = lines[0].split(" ")
            if method == "CONNECT":
                parsed = urlsplit("//" + target)
                if parsed.port != 443 or not parsed.hostname or parsed.username or parsed.path:
                    raise ValueError("Invalid tunnel")
                remote, upstream = await public_connection(parsed.hostname, 443)
                writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                await writer.drain()
            else:
                parsed = urlsplit(target)
                if (
                    parsed.scheme != "http"
                    or not parsed.hostname
                    or parsed.username
                    or parsed.password
                ):
                    raise ValueError("Invalid proxy request")
                remote, upstream = await public_connection(parsed.hostname, parsed.port or 80)
                path = parsed.path or "/"
                if parsed.query:
                    path += "?" + parsed.query
                forwarded = [f"{method} {path} {version}", f"Host: {parsed.netloc}"]
                forwarded.extend(
                    line
                    for line in lines[1:]
                    if line
                    and line.split(":", 1)[0].lower()
                    not in {"host", "connection", "proxy-connection", "proxy-authorization"}
                )
                upstream.write(
                    ("\r\n".join([*forwarded, "Connection: close", "", ""])).encode("latin-1")
                )
                await upstream.drain()

            async def relay(
                source: asyncio.StreamReader, destination: asyncio.StreamWriter
            ) -> None:
                while data := await asyncio.wait_for(source.read(65536), 120):
                    destination.write(data)
                    await destination.drain()

            tasks = [
                asyncio.create_task(relay(reader, upstream)),
                asyncio.create_task(relay(remote, writer)),
            ]
            try:
                await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            finally:
                for relay_task in tasks:
                    relay_task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
        except (
            OSError,
            ValueError,
            asyncio.TimeoutError,
            asyncio.IncompleteReadError,
            asyncio.LimitOverrunError,
        ):
            writer.write(
                b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
            )
        finally:
            if upstream:
                upstream.close()
                with contextlib.suppress(OSError):
                    await upstream.wait_closed()
            writer.close()
            with contextlib.suppress(OSError):
                await writer.wait_closed()
            self.connections.discard(task)
