"""Unit tests for pinak.media.sync modules."""

from pinak.media.core.terminal_caps import TerminalCapabilities
from pinak.media.sync.clock import MasterAudioClock
from pinak.media.sync.fallback_manager import FallbackManager
from pinak.media.sync.scheduler import SyncAction, VideoFrameScheduler
from pinak.media.sync.throttler import BandwidthThrottler


def test_master_audio_clock():
    clk = MasterAudioClock()
    assert clk.get_time() >= 0.0

    clk.set_time(42.0)
    assert clk.get_time() >= 42.0

    clk.pause()
    frozen = clk.get_time()
    assert clk.get_time() == frozen
    clk.resume()


def test_video_frame_scheduler_actions():
    # 1. In Sync: drift <= 15ms
    action, sleep_t = VideoFrameScheduler.evaluate(video_pts=10.010, master_pts=10.000)
    assert action == SyncAction.RENDER_NOW
    assert sleep_t == 0.0

    # 2. Video Ahead: drift > 15ms
    action, sleep_t = VideoFrameScheduler.evaluate(video_pts=10.040, master_pts=10.000)
    assert action == SyncAction.SLEEP_WAIT
    assert sleep_t > 0.0

    # 3. Minor Lag: -60ms <= drift < -15ms
    action, sleep_t = VideoFrameScheduler.evaluate(video_pts=9.960, master_pts=10.000)
    assert action == SyncAction.RENDER_FAST
    assert sleep_t == 0.0

    # 4. Severe Lag: drift < -60ms -> DROP FRAME!
    action, sleep_t = VideoFrameScheduler.evaluate(video_pts=9.900, master_pts=10.000)
    assert action == SyncAction.DROP_FRAME


def test_fallback_manager_selection_and_degradation():
    caps_kitty = TerminalCapabilities(has_kitty=True)
    r1 = FallbackManager.get_best_renderer(caps_kitty)
    assert r1.mode_name == "kitty"

    # Degrade from kitty -> halfblock
    r2 = FallbackManager.degrade_renderer(r1)
    assert r2.mode_name == "halfblock"

    # Degrade from halfblock -> ascii
    r3 = FallbackManager.degrade_renderer(r2)
    assert r3.mode_name == "ascii"


def test_bandwidth_throttler():
    throttler = BandwidthThrottler(target_fps=60.0, window_size=5)
    assert throttler.throttle_level == 0

    # Simulate heavy frame render times
    for _ in range(6):
        throttler.record_render_time(0.040)  # 40ms >> 16.6ms target

    assert throttler.throttle_level > 0
    assert throttler.should_skip_frame(1) is True


def test_bandwidth_throttler_none_maxlen():
    import collections

    throttler = BandwidthThrottler(target_fps=60.0)
    throttler.history = collections.deque()  # maxlen is None
    # Must not raise TypeError: '>=' not supported between instances of 'int' and 'NoneType'
    for _ in range(20):
        throttler.record_render_time(0.050)
    assert throttler.throttle_level > 0
