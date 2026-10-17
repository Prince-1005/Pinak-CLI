"""mpv-compatible JSON-IPC client for remote controlling a live media session."""

from __future__ import annotations

import json
import socket
from typing import Any

from .endpoint import discover_endpoint


class MediaIPCClient:
    """Client for transmitting JSON-RPC commands to a running Pinak Media session."""

    def __init__(
        self,
        port: int | None = None,
        host: str = "127.0.0.1",
        timeout: float = 2.0,
        auth_token: str | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.auth_token = auth_token

    def send_command(self, *cmd_parts: Any, request_id: int | None = None) -> dict[str, Any]:
        """Transmits a single JSON-RPC command list and awaits the JSON response."""
        if self.port is None:
            self.port, self.auth_token = discover_endpoint()
        if len(cmd_parts) == 1 and isinstance(cmd_parts[0], (list, tuple)):
            cmd_list = list(cmd_parts[0])
        else:
            cmd_list = list(cmd_parts)
        req: dict[str, Any] = {"command": cmd_list}
        if request_id is not None:
            req["request_id"] = request_id
        if self.auth_token is not None:
            req["auth"] = self.auth_token

        payload = (json.dumps(req) + "\n").encode("utf-8")
        with socket.create_connection((self.host, self.port), timeout=self.timeout) as sock:
            sock.sendall(payload)
            response_data = b""
            while b"\n" not in response_data:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                response_data += chunk
                if len(response_data) > 65536:
                    raise ValueError("IPC response exceeds the size limit")

        line = response_data.decode("utf-8", errors="replace").strip()
        if not line:
            return {"error": "empty response", "data": None}
        response = json.loads(line)
        if not isinstance(response, dict):
            raise ValueError("IPC response must be an object")
        return response

    @staticmethod
    def _data(response: dict[str, Any]) -> Any:
        if response.get("error") != "success":
            raise ConnectionError(str(response.get("error", "IPC request failed")))
        return response.get("data")

    def toggle_pause(self) -> bool:
        """Toggles play/pause."""
        res = self.send_command("cycle", "pause")
        return bool(self._data(res))

    def seek_relative(self, seconds: float) -> float:
        """Relative seek by seconds (positive or negative)."""
        res = self.send_command("seek", seconds, "relative")
        return float(self._data(res))

    def set_volume(self, volume_percent: float) -> None:
        """Sets volume to given percentage (0 to 150)."""
        self._data(self.send_command("set_property", "volume", volume_percent))

    def get_playback_time(self) -> float:
        """Queries current PTS time in seconds."""
        res = self.send_command("get_property", "playback-time")
        return float(self._data(res))

    def quit(self) -> None:
        """Stops and terminates the media player."""
        self._data(self.send_command("quit"))
