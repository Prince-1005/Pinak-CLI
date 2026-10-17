"""mpv-compatible JSON-IPC server for external control and scripting."""

from __future__ import annotations

import contextlib
import json
import logging
import math
import secrets
import socket
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .endpoint import publish_endpoint

if TYPE_CHECKING:
    from ..player.coordinator import MediaSession

logger = logging.getLogger("pinak.media.ipc")


class MediaIPCServer:
    """Listens for mpv-compatible JSON-RPC command payloads over a local TCP loopback port."""

    DEFAULT_PORT = 9285

    def __init__(
        self,
        session: MediaSession,
        port: int = DEFAULT_PORT,
        auth_token: str | None = None,
    ) -> None:
        self.session = session
        self.port = port
        self.actual_port = port
        self.auth_token = auth_token or secrets.token_urlsafe(32)
        self.is_running = False
        self._server_sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._clients: dict[socket.socket, threading.Thread] = {}
        self._clients_lock = threading.Lock()
        self._endpoint_path: Path | None = None
        self.max_clients = 8
        self.max_message_bytes = 65536

    def start(self) -> int:
        """Starts the IPC server daemon thread and returns the active listening port."""
        if self.is_running:
            return self.actual_port

        self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        # Try binding to requested port, fallback to any free ephemeral port if busy
        try:
            self._server_sock.bind(("127.0.0.1", self.port))
        except OSError:
            self._server_sock.bind(("127.0.0.1", 0))

        self.actual_port = self._server_sock.getsockname()[1]

        self._server_sock.listen(5)
        self._server_sock.settimeout(1.0)
        try:
            self._endpoint_path = publish_endpoint(self.actual_port, self.auth_token)
        except Exception:
            self._server_sock.close()
            self._server_sock = None
            raise
        self.is_running = True

        self._thread = threading.Thread(
            target=self._listen_loop, daemon=True, name="Pinak-Media-IPC"
        )
        self._thread.start()
        logger.info(f"Pinak Media JSON-IPC server listening on 127.0.0.1:{self.actual_port}")
        return self.actual_port

    def stop(self) -> None:
        """Terminates IPC listener."""
        self.is_running = False
        with self._clients_lock:
            clients = list(self._clients.items())
        for connection, _ in clients:
            with contextlib.suppress(OSError):
                connection.shutdown(socket.SHUT_RDWR)
            connection.close()
        if self._server_sock:
            with contextlib.suppress(Exception):
                self._server_sock.close()
            self._server_sock = None
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        for _, worker in clients:
            if worker is not threading.current_thread():
                worker.join(timeout=0.2)
        if self._endpoint_path:
            self._endpoint_path.unlink(missing_ok=True)
            self._endpoint_path = None

    def _listen_loop(self) -> None:
        listener = self._server_sock
        while self.is_running and listener:
            try:
                conn, _ = listener.accept()
            except TimeoutError:
                continue
            except OSError:
                break

            with self._clients_lock:
                if len(self._clients) >= self.max_clients:
                    conn.close()
                    continue
                conn.settimeout(1.0)
                client_thread = threading.Thread(
                    target=self._serve_client, args=(conn,), daemon=True
                )
                self._clients[conn] = client_thread
                client_thread.start()

    def _serve_client(self, conn: socket.socket) -> None:
        try:
            self._handle_client(conn)
        finally:
            with self._clients_lock:
                self._clients.pop(conn, None)

    def _handle_client(self, conn: socket.socket) -> None:
        with conn:
            buffer = b""
            is_authenticated = False
            last_message = time.monotonic()
            while self.is_running:
                try:
                    data = conn.recv(4096)
                    if not data:
                        break
                    buffer += data
                    if len(buffer) > self.max_message_bytes or time.monotonic() - last_message > 10:
                        break
                    while b"\n" in buffer:
                        raw_line, buffer = buffer.split(b"\n", 1)
                        line = raw_line.decode("utf-8", errors="strict").strip()
                        last_message = time.monotonic()
                        if not line:
                            continue

                        try:
                            parsed = json.loads(line)
                        except json.JSONDecodeError as err:
                            resp = {"error": f"invalid json: {err}", "data": None}
                            conn.sendall((json.dumps(resp) + "\n").encode("utf-8"))
                            continue

                        if not isinstance(parsed, dict):
                            conn.sendall(b'{"error":"request must be an object","data":null}\n')
                            continue
                        # Authentication is mandatory, including generated default tokens.
                        token = parsed.get("auth")
                        if isinstance(token, str) and secrets.compare_digest(
                            token, self.auth_token
                        ):
                            is_authenticated = True

                        cmd_args = parsed.get("command", [])
                        if (
                            cmd_args
                            and isinstance(cmd_args, list)
                            and str(cmd_args[0]).lower() == "auth"
                        ):
                            if (
                                len(cmd_args) > 1
                                and self.auth_token
                                and isinstance(cmd_args[1], str)
                                and secrets.compare_digest(cmd_args[1], self.auth_token)
                            ):
                                is_authenticated = True
                                conn.sendall(
                                    (
                                        json.dumps(
                                            {
                                                "error": "success",
                                                "data": "authenticated",
                                                "request_id": parsed.get("request_id"),
                                            }
                                        )
                                        + "\n"
                                    ).encode("utf-8")
                                )
                            else:
                                conn.sendall(
                                    (
                                        json.dumps(
                                            {
                                                "error": "unauthorized: invalid auth token",
                                                "data": None,
                                                "request_id": parsed.get("request_id"),
                                            }
                                        )
                                        + "\n"
                                    ).encode("utf-8")
                                )
                            continue

                        if not is_authenticated:
                            conn.sendall(
                                (
                                    json.dumps(
                                        {
                                            "error": "unauthorized: authentication required",
                                            "data": None,
                                            "request_id": parsed.get("request_id"),
                                        }
                                    )
                                    + "\n"
                                ).encode("utf-8")
                            )
                            continue

                        submit = getattr(type(self.session), "submit_ipc_command", None)
                        resp = (
                            self.session.submit_ipc_command(line)
                            if submit
                            else self.dispatch_command(line)
                        )
                        conn.sendall((json.dumps(resp) + "\n").encode("utf-8"))
                except TimeoutError:
                    if time.monotonic() - last_message > 10:
                        break
                except (OSError, UnicodeDecodeError, ValueError, RecursionError):
                    break

    def dispatch_command(self, raw_json: str) -> dict[str, Any]:
        """Parses and executes an mpv-compatible JSON command."""
        try:
            req = json.loads(raw_json)
        except (ValueError, RecursionError) as e:
            return {"error": f"invalid json: {e}", "data": None}

        if not isinstance(req, dict):
            return {"error": "request must be an object", "data": None}
        cmd_args = req.get("command", [])
        req_id = req.get("request_id")
        if not cmd_args or not isinstance(cmd_args, list):
            return {"error": "missing command list", "data": None, "request_id": req_id}

        verb = str(cmd_args[0]).lower()
        result: Any = None
        error: str = "success"

        try:
            if verb == "set_property":
                # ["set_property", "pause", true]
                prop = str(cmd_args[1]).lower()
                val = cmd_args[2]
                if prop == "pause":
                    if not isinstance(val, bool):
                        raise ValueError("pause must be boolean")
                    bool_val = bool(val)
                    if callable(getattr(type(self.session), "set_playing", None)):
                        self.session.set_playing(not bool_val)
                    elif bool_val and self.session.transport.is_playing:
                        self.session.transport.toggle_play_pause()
                        if self.session.audio_backend:
                            self.session.audio_backend.pause()
                    elif not bool_val and not self.session.transport.is_playing:
                        self.session.transport.toggle_play_pause()
                        if self.session.audio_backend:
                            self.session.audio_backend.resume()
                elif prop in ("volume", "vol"):
                    new_vol = float(val) / 100.0
                    if not math.isfinite(new_vol):
                        raise ValueError("volume must be finite")
                    self.session.transport.volume = max(0.0, min(1.5, new_vol))
                    if self.session.audio_backend:
                        self.session.audio_backend.set_volume(self.session.transport.volume)
                elif prop in ("mute", "muted"):
                    if not isinstance(val, bool):
                        raise ValueError("mute must be boolean")
                    if callable(getattr(type(self.session), "set_muted", None)):
                        self.session.set_muted(val)
                    else:
                        self.session.transport.is_muted = val
                    if (
                        self.session.audio_backend
                        and not callable(getattr(type(self.session), "set_muted", None))
                        and self.session.audio_backend.is_muted != bool(val)
                    ):
                        self.session.audio_backend.toggle_mute()
                else:
                    error = f"unknown property: {prop}"

            elif verb == "get_property":
                prop = str(cmd_args[1]).lower()
                if prop in ("playback-time", "time-pos"):
                    result = self.session.transport.current_pts
                elif prop == "duration":
                    result = self.session.transport.duration_sec
                elif prop == "pause":
                    result = not self.session.transport.is_playing
                elif prop in ("volume", "vol"):
                    result = self.session.transport.volume * 100.0
                elif prop in ("mute", "muted"):
                    result = self.session.transport.is_muted
                elif prop in ("media-title", "filename"):
                    cur = self.session.playlist_manager.get_current()
                    result = cur.name if cur else "None"
                else:
                    error = f"unknown property: {prop}"

            elif verb == "cycle":
                target = str(cmd_args[1]).lower()
                if target == "pause":
                    coordinated = callable(getattr(type(self.session), "set_playing", None))
                    if coordinated:
                        self.session.set_playing(not self.session.transport.is_playing)
                    else:
                        self.session.transport.toggle_play_pause()
                    if self.session.transport.is_playing and not coordinated:
                        if self.session.audio_backend:
                            self.session.audio_backend.resume()
                    elif self.session.audio_backend and not coordinated:
                        self.session.audio_backend.pause()
                    result = not self.session.transport.is_playing
                elif target == "mute":
                    self.session.transport.toggle_mute()
                    if self.session.audio_backend:
                        self.session.audio_backend.toggle_mute()
                    result = self.session.transport.is_muted
                elif target in ("sub", "sid"):
                    if hasattr(self.session, "cycle_subtitles"):
                        result = self.session.cycle_subtitles()
                else:
                    error = f"unknown cycle target: {target}"

            elif verb == "seek":
                amount = float(cmd_args[1])
                if not math.isfinite(amount):
                    raise ValueError("seek must be finite")
                mode = str(cmd_args[2]).lower() if len(cmd_args) > 2 else "relative"
                if mode == "absolute":
                    pts = self.session.transport.seek_to(amount)
                else:
                    pts = self.session.transport.seek_relative(amount)
                if callable(getattr(type(self.session), "seek_to", None)):
                    pts = self.session.seek_to(pts)
                else:
                    if self.session.audio_backend:
                        self.session.audio_backend.seek(pts)
                    if self.session.video_decoder:
                        self.session.video_decoder.seek(pts)
                result = pts

            elif verb in ("quit", "stop"):
                self.session.stop()
                result = "stopping"

            else:
                error = f"command '{verb}' not implemented"

        except Exception as e:
            error = str(e)

        resp_dict = {"data": result, "error": error}
        if req_id is not None:
            resp_dict["request_id"] = req_id
        return resp_dict
