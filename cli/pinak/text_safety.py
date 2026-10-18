"""Separate untrusted display text from trusted terminal/Rich formatting."""

from __future__ import annotations

import re

from rich.markup import escape

_CONTROLS = re.compile(r"[\x00-\x1f\x7f-\x9f\u202a-\u202e\u2066-\u2069]")
_ANSI_CSI = re.compile(r"(?:\x1b\[|\x9b)[0-?]*[ -/]*[@-~]")


def safe_text(value: object) -> str:
    return _CONTROLS.sub("", _ANSI_CSI.sub("", str(value)))


def safe_rich(value: object) -> str:
    return escape(safe_text(value))
