"""Shared control command dispatch for the REPL and one-shot CLI."""

from __future__ import annotations

from rich.console import Console

from ..media.ipc.client import MediaIPCClient
from ..text_safety import safe_rich

console = Console()


def handle_control(args: list[str]) -> int:
    action = args[0].lower() if args else "status"
    client = MediaIPCClient()
    try:
        if action in ("play", "pause"):
            response = client.send_command("set_property", "pause", action == "pause")
        elif action in ("toggle",):
            response = client.send_command("cycle", "pause")
        elif action == "seek":
            response = client.send_command(
                "seek", float(args[1]) if len(args) > 1 else 10, "relative"
            )
        elif action in ("volume", "vol"):
            response = client.send_command(
                "set_property", "volume", float(args[1]) if len(args) > 1 else 100
            )
        elif action in ("status", "time", "pos"):
            response = client.send_command("get_property", "playback-time")
        elif action in ("quit", "stop"):
            response = client.send_command("quit")
        else:
            response = client.send_command(*args)
        if response.get("error") != "success":
            raise ConnectionError(str(response.get("error", "IPC request failed")))
        console.print(f"[green][+] {safe_rich(action)}: {safe_rich(response.get('data'))}[/green]")
        return 0
    except (ValueError, OSError, ConnectionError) as exc:
        console.print(f"[red][!] IPC control failed: {safe_rich(exc)}[/red]")
        return 1
