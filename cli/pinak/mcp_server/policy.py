"""Local path permissions and safe protocol results."""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from ..text_safety import safe_text
from .models import Policy


class ToolFailure(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        recovery: str = "Inspect the request and retry.",
        *,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code, self.recovery, self.retryable = code, recovery, retryable


def permitted(path: Path, roots: list[Path]) -> bool:
    resolved = path.resolve()
    return any(resolved.is_relative_to(root.resolve()) for root in roots)


def output_path(value: str | None, policy: Policy) -> Path:
    path = Path(value).expanduser() if value else policy.default_output_dir
    if not path.is_absolute():
        path = policy.default_output_dir / path
    path = path.resolve()
    if not permitted(path, policy.output_roots or []):
        raise ToolFailure(
            "PATH_DENIED",
            "Output directory is outside approved roots.",
            "Add the directory to your local MCP configuration deliberately.",
        )
    return path


def read_path(value: str, policy: Policy) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = policy.default_output_dir / path
    path = path.resolve()
    if not permitted(path, [*(policy.output_roots or []), *policy.read_roots]):
        raise ToolFailure("PATH_DENIED", "File is outside approved read roots.")
    return path


def redact_url(match: re.Match[str]) -> str:
    try:
        p = urlsplit(match.group())
        host = p.hostname or "redacted"
        if ":" in host:
            host = f"[{host}]"
        if p.port:
            host += f":{p.port}"
        return urlunsplit((p.scheme, host, p.path, "[redacted]" if p.query else "", ""))
    except ValueError:
        return "[redacted URL]"


def clean(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return None  # malformed media metadata must remain valid JSON
    if isinstance(value, str):
        value = safe_text(value)
        value = re.sub(r"https?://[^\s<>\"']+", redact_url, value, flags=re.IGNORECASE)
        value = re.sub(
            r"(?i)(authorization|password|token|api[_-]?key|cookie)(\s*[:=]\s*)[^\s,;]+",
            r"\1\2[redacted]",
            value,
        )
        return value
    if isinstance(value, dict):
        return {str(key): clean(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [clean(item) for item in value]
    return value
