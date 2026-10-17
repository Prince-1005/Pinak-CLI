"""Unit tests for the On-Screen Controller (OSC) HUD overlay."""

import time

from PIL import Image

from pinak.media.osc.controller import OnScreenController, OSCState


def test_osc_idle_state_and_interaction():
    osc = OnScreenController(idle_timeout=0.1)
    assert osc.is_visible is True
    assert osc.check_idle() is True

    # Sleep past idle timeout
    time.sleep(0.12)
    assert osc.check_idle() is False
    assert osc.is_visible is False

    # Trigger interaction revives visibility
    osc.trigger_interaction()
    assert osc.is_visible is True
    assert osc.check_idle() is True


def test_osc_render_overlay():
    osc = OnScreenController(idle_timeout=2.0)
    frame = Image.new("RGB", (800, 450), color=(30, 40, 50))

    state = OSCState(
        title="Test Movie Clip.mp4",
        current_pts=45.0,
        duration_sec=120.0,
        is_playing=True,
        volume=0.85,
        is_muted=False,
        subtitle_track_name="English",
        quality_label="1080p",
        renderer_mode="HALFBLOCK",
    )

    rendered = osc.render_overlay(frame, state)
    assert rendered.size == (800, 450)
    assert rendered.mode == "RGB"

    # When idle, returns original frame copy without drawing
    osc.is_visible = False
    osc._last_interaction_time = time.perf_counter() - 5.0
    idle_rendered = osc.render_overlay(frame, state)
    assert idle_rendered.size == (800, 450)


def test_osc_time_formatting():
    assert OnScreenController._format_time(0.0) == "00:00"
    assert OnScreenController._format_time(65.0) == "01:05"
    assert OnScreenController._format_time(3665.0) == "01:01:05"
