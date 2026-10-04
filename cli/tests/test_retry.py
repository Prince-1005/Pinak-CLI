"""Unit tests for pinak.retry — backoff math & retry behaviour."""

from pinak.retry import backoff_delay, is_retryable, retry_with_backoff


def test_backoff_delay_grows_exponentially():
    d1 = backoff_delay(1, base=2.0, cap=100.0, jitter=False)
    d2 = backoff_delay(2, base=2.0, cap=100.0, jitter=False)
    d3 = backoff_delay(3, base=2.0, cap=100.0, jitter=False)
    assert (d1, d2, d3) == (2.0, 4.0, 8.0)


def test_backoff_delay_respects_cap():
    assert backoff_delay(10, base=2.0, cap=30.0, jitter=False) == 30.0


def test_is_retryable_detects_transient():
    assert is_retryable(TimeoutError("connection timed out"))
    assert is_retryable(RuntimeError("HTTP 429 too many requests"))
    assert is_retryable(ConnectionError("reset by peer"))


def test_is_retryable_rejects_permanent():
    assert not is_retryable(ValueError("invalid quality option"))


def test_retry_with_backoff_succeeds_after_failures(monkeypatch):
    monkeypatch.setattr("pinak.retry.time.sleep", lambda s: None)
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise TimeoutError("timed out")
        return "ok"

    assert retry_with_backoff(flaky, max_attempts=3, base=0.01) == "ok"
    assert calls["n"] == 3


def test_retry_with_backoff_gives_up(monkeypatch):
    monkeypatch.setattr("pinak.retry.time.sleep", lambda s: None)
    calls = {"n": 0}

    def always_fail():
        calls["n"] += 1
        raise TimeoutError("timed out")

    try:
        retry_with_backoff(always_fail, max_attempts=2, base=0.01)
        raise AssertionError("should have raised")
    except TimeoutError:
        pass
    assert calls["n"] == 2


def test_retry_with_backoff_does_not_retry_permanent(monkeypatch):
    monkeypatch.setattr("pinak.retry.time.sleep", lambda s: None)
    calls = {"n": 0}

    def permanent():
        calls["n"] += 1
        raise ValueError("bad input")

    try:
        retry_with_backoff(permanent, max_attempts=3, base=0.01)
        raise AssertionError("should have raised")
    except ValueError:
        pass
    assert calls["n"] == 1
