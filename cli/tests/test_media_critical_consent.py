"""Critical device consent and native viewing regressions."""

from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest

from pinak.media.core.input_parser import KeyEvent
from pinak.media.decoders.probe import MediaMetadata
from pinak.media.diagnostics.capacity_scorer import CapacityScorer
from pinak.media.diagnostics.preflight_modal import PreflightConsentModal
from pinak.media.diagnostics.telemetry_probe import DeviceTelemetry
from pinak.media.window.native_window import NativeVideoWindow


def _telemetry() -> DeviceTelemetry:
    return DeviceTelemetry(
        cpu_cores_logical=8,
        cpu_cores_physical=4,
        cpu_usage_pct=15,
        ram_total_mb=8192,
        ram_available_mb=2048,
        ram_usage_pct=75,
        gpu_acceleration=None,
        is_on_battery=False,
        battery_pct=100,
        terminal_type="test",
        has_truecolor=True,
    )


def _media(media_type: str = "video", width: int = 1920, height: int = 1080) -> MediaMetadata:
    return MediaMetadata(
        media_type=media_type,  # type: ignore[arg-type]
        file_path=Path("movie.mp4"),
        file_size_bytes=1000,
        width=width,
        height=height,
    )


def _critical(telem: DeviceTelemetry, meta: MediaMetadata) -> tuple[bool, str]:
    profile = CapacityScorer.evaluate(telem, media_type=meta.media_type)
    return PreflightConsentModal.is_critical_situation(telem, profile, meta)


def test_only_measured_critical_conditions_request_consent() -> None:
    normal = _telemetry()
    meta = _media()
    assert _critical(normal, meta) == (False, "")
    assert _critical(replace(normal, cpu_usage_pct=98, ram_usage_pct=94), meta) == (False, "")
    assert _critical(replace(normal, measurements_available=False, ram_available_mb=0), meta) == (
        False,
        "",
    )
    assert _critical(replace(normal, is_on_battery=True, battery_pct=16), meta) == (False, "")
    assert (
        "Low battery (15%)"
        in _critical(replace(normal, is_on_battery=True, battery_pct=15), meta)[1]
    )
    assert "High temperature (85°C)" in _critical(replace(normal, temperature_c=85), meta)[1]
    assert "Low RAM" in _critical(replace(normal, ram_available_mb=400), meta)[1]


def test_video_ram_budget_scales_with_resolution() -> None:
    telem = replace(_telemetry(), ram_available_mb=550)
    assert _critical(telem, _media("audio", 0, 0)) == (False, "")
    assert _critical(telem, _media("video", 1280, 720)) == (False, "")
    critical, reason = _critical(telem, _media("video", 3840, 2160))
    assert critical and "Low RAM" in reason


def test_noninteractive_critical_state_requires_explicit_override(capsys) -> None:
    critical = replace(_telemetry(), is_on_battery=True, battery_pct=7)
    with (
        patch(
            "pinak.media.diagnostics.preflight_modal.DeviceDiagnosticsProbe.inspect",
            return_value=critical,
        ),
        patch("pinak.media.diagnostics.preflight_modal.sys.stdin") as stdin,
    ):
        stdin.isatty.return_value = False
        assert PreflightConsentModal.prompt_user(_media()) is False
        assert PreflightConsentModal.prompt_user(_media(), auto_consent=True) is True
    assert "Low battery (7%)" in capsys.readouterr().err


def test_interactive_critical_state_accepts_only_an_explicit_choice(capsys) -> None:
    critical = replace(_telemetry(), is_on_battery=True, battery_pct=7)
    with (
        patch(
            "pinak.media.diagnostics.preflight_modal.DeviceDiagnosticsProbe.inspect",
            return_value=critical,
        ),
        patch("pinak.media.diagnostics.preflight_modal.sys.stdin") as stdin,
        patch("pinak.media.diagnostics.preflight_modal.TerminalSessionContext"),
        patch("pinak.media.diagnostics.preflight_modal.InputParser") as parser,
    ):
        stdin.isatty.return_value = True
        parser.return_value.poll_events.return_value = [KeyEvent("n")]
        assert PreflightConsentModal.prompt_user(_media()) is False
        parser.return_value.poll_events.return_value = [KeyEvent("enter")]
        assert PreflightConsentModal.prompt_user(_media()) is True
    assert "Low battery (7%)" in capsys.readouterr().out


def test_critical_modal_lists_all_reasons() -> None:
    telem = replace(
        _telemetry(), is_on_battery=True, battery_pct=5, ram_available_mb=100, temperature_c=90
    )
    profile = CapacityScorer.evaluate(telem)
    critical, reason = _critical(telem, _media())
    assert critical
    message = PreflightConsentModal.render_modal_text(telem, profile, "movie.mp4", "video", reason)
    assert "Low battery (5%)" in message
    assert "Low RAM" in message
    assert "High temperature (90°C)" in message


@pytest.mark.parametrize("failed_operation", ["write", "flush"])
def test_critical_state_cannot_bypass_consent_when_output_fails(failed_operation) -> None:
    critical = replace(_telemetry(), is_on_battery=True, battery_pct=7)
    with (
        patch(
            "pinak.media.diagnostics.preflight_modal.DeviceDiagnosticsProbe.inspect",
            return_value=critical,
        ),
        patch("pinak.media.diagnostics.preflight_modal.sys.stdin") as stdin,
        patch("pinak.media.diagnostics.preflight_modal.sys.stdout") as stdout,
        patch("pinak.media.diagnostics.preflight_modal.TerminalSessionContext"),
        patch("pinak.media.diagnostics.preflight_modal.InputParser") as parser,
    ):
        stdin.isatty.return_value = True
        getattr(stdout, failed_operation).side_effect = OSError("Terminal output unavailable")
        assert PreflightConsentModal.prompt_user(_media()) is False
        parser.assert_not_called()


def test_native_window_uses_screen_area_and_aspect_ratio() -> None:
    assert NativeVideoWindow.compute_window_size(1920, 1080, 1920, 1080) == (1632, 918)
    assert NativeVideoWindow.compute_window_size(720, 720, 1920, 1080) == (918, 918)
    width, height = NativeVideoWindow.compute_window_size(3840, 2160, 1366, 768)
    assert width <= int(1366 * 0.9)
    assert height <= int(768 * 0.85)
    assert abs(width / height - 16 / 9) < 0.01

    regular = NativeVideoWindow(initial_scale=1.0)._opening_size(1920, 1080, 1920, 1080)
    video = NativeVideoWindow(initial_scale=0.5)._opening_size(1920, 1080, 1920, 1080)
    assert video == (816, 459)
    assert video[0] < regular[0] and video[1] < regular[1]
