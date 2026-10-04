"""Property-based fuzz tests: helpers must never crash and must uphold invariants."""

import re

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from pinak import utils

_ILLEGAL = set('<>:"/\\|?*')


@given(st.text())
@settings(max_examples=150, suppress_health_check=[HealthCheck.too_slow])
def test_sanitize_filename_never_empty_or_illegal(name):
    out = utils.sanitize_filename(name)
    assert isinstance(out, str) and len(out) > 0
    assert len(out) <= 180
    assert not any(c in out for c in _ILLEGAL)
    assert not any(ord(c) < 32 for c in out)


@given(st.text())
@settings(max_examples=150, suppress_health_check=[HealthCheck.too_slow])
def test_normalize_quality_contract(value):
    out = utils.normalize_quality(value)
    assert out is None or out in {"best", "worst", "audio"} or re.fullmatch(r"\d{3,4}p", out)


@given(
    st.integers(min_value=-(10**12), max_value=10**12),
    st.integers(min_value=0, max_value=10**6),
)
@settings(max_examples=100)
def test_video_format_for_quality_never_crashes(quality_num, _other):
    for candidate in (
        str(quality_num),
        f"{abs(quality_num) % 9000}p",
        "best",
        "worst",
        None,
    ):
        fmt = utils.video_format_for_quality(candidate)
        assert isinstance(fmt, str) and len(fmt) > 0


@given(st.floats(allow_nan=True, allow_infinity=True), st.integers())
@settings(max_examples=100)
def test_human_helpers_never_raise(size, seconds):
    assert isinstance(utils.human_size(size), str)
    assert isinstance(utils.human_duration(seconds), str)
