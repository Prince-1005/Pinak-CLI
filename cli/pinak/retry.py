"""Retry helpers with exponential backoff + jitter.

Used by the download engine and image fetchers so transient network
failures (timeouts, 429s, connection resets) recover automatically
instead of failing immediately.
"""

from __future__ import annotations

import random
import re
import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


def is_rate_limited(exc: BaseException) -> bool:
    """Recognize throttling separately from short-lived connection failures."""
    return bool(re.search(r"\b429\b|too many requests|rate[- ]limit", str(exc).lower()))


# Exceptions that are generally worth retrying.
RETRYABLE_MARKERS: tuple[str, ...] = (
    "timeout",
    "timed out",
    "connection",
    "temporary",
    "try again",
    "429",
    "too many requests",
    "rate-limit",
    "rate limit",
    "reset by peer",
    "broken pipe",
    "service unavailable",
    "502",
    "503",
    "504",
)


def is_retryable(exc: BaseException) -> bool:
    """Heuristic: is this exception likely transient?"""
    text = f"{type(exc).__name__}: {exc}".lower()
    return any(marker in text for marker in RETRYABLE_MARKERS)


def backoff_delay(attempt: int, base: float = 2.0, cap: float = 30.0, jitter: bool = True) -> float:
    """Exponential backoff: base * 2**(attempt-1), capped, with optional jitter.

    attempt is 1-indexed (first retry == attempt 1).
    """
    delay = base * (2 ** max(0, attempt - 1))
    delay = min(delay, cap)
    if jitter:
        delay = delay * (0.5 + random.random() * 0.5)  # 50%-100% of delay
    return round(delay, 2)


def retry_with_backoff(
    func: Callable[[], T],
    *,
    max_attempts: int = 3,
    base: float = 2.0,
    cap: float = 30.0,
    retryable: Callable[[BaseException], bool] = is_retryable,
    on_retry: Callable[[int, int, BaseException, float], None] | None = None,
) -> T:
    """Run ``func`` with exponential-backoff retries.

    Raises the last exception if all attempts fail.
    """
    last_exc: BaseException | None = None
    attempts = max(1, int(max_attempts))
    for attempt in range(1, attempts + 1):
        try:
            return func()
        except Exception as exc:  # noqa: BLE001 - intentional: classify then re-raise
            last_exc = exc
            if attempt >= attempts or not retryable(exc):
                raise
            delay = backoff_delay(attempt, base=base, cap=cap)
            if on_retry is not None:
                on_retry(attempt, attempts, exc, delay)
            time.sleep(delay)
    assert last_exc is not None  # for type checkers
    raise last_exc


def sleep_with_interrupt(seconds: float) -> bool:
    """Sleep that returns False if interrupted by KeyboardInterrupt.

    Returns True when the full duration elapsed, False when cancelled.
    """
    try:
        from .engine import cancellation_requested, managed_stop_enabled

        if not managed_stop_enabled():
            time.sleep(seconds)
            return True

        deadline = time.monotonic() + seconds
        while (remaining := deadline - time.monotonic()) > 0:
            if cancellation_requested():
                return False
            time.sleep(min(0.2, remaining))
        return True
    except KeyboardInterrupt:
        return False
