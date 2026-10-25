"""Separate untrusted display text from trusted terminal/Rich formatting."""

from __future__ import annotations

import re
from urllib.parse import urlsplit, urlunsplit

from rich.markup import escape

_CONTROLS = re.compile(r"[\x00-\x1f\x7f-\x9f\u202a-\u202e\u2066-\u2069]")
_ANSI_CSI = re.compile(r"(?:\x1b\[|\x9b)[0-?]*[ -/]*[@-~]")
_ANSI_OSC = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")


def safe_text(value: object) -> str:
    text = _ANSI_OSC.sub("", str(value))
    text = _ANSI_CSI.sub("", text)
    return _CONTROLS.sub("", text)


def safe_rich(value: object) -> str:
    return escape(safe_text(value))


def safe_url_for_log(value: object) -> str:
    """Keep a URL's destination useful in logs without retaining credentials."""
    try:
        parsed = urlsplit(str(value))
        host = parsed.hostname or "redacted"
        if ":" in host:
            host = f"[{host}]"
        if parsed.port is not None:
            host += f":{parsed.port}"
        return safe_text(
            urlunsplit((parsed.scheme, host, parsed.path, "[redacted]" if parsed.query else "", ""))
        )
    except ValueError:
        return "[redacted URL]"
