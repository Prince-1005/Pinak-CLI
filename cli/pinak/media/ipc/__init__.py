"""mpv-compatible JSON-IPC package."""

from .client import MediaIPCClient
from .server import MediaIPCServer

__all__ = ["MediaIPCClient", "MediaIPCServer"]
