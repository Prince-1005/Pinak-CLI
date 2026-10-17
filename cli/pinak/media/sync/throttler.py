"""Dynamic terminal stdout bandwidth and rendering throttler."""

from __future__ import annotations

import collections


class BandwidthThrottler:
    """Monitors terminal frame write latencies and throttles rendering to prevent TTY backpressure."""

    def __init__(self, target_fps: float = 60.0, window_size: int = 15) -> None:
        self.target_frame_time = 1.0 / max(1.0, target_fps)
        self.history: collections.deque[float] = collections.deque(maxlen=window_size)
        self.throttle_level: int = 0  # 0: Normal, 1: Halve FPS, 2: Heavy Throttling

    def record_render_time(self, elapsed_sec: float) -> None:
        """Records the time taken to generate and flush a single terminal frame."""
        self.history.append(elapsed_sec)
        threshold = self.history.maxlen if self.history.maxlen is not None else 15
        if len(self.history) >= threshold:
            avg_time = sum(self.history) / len(self.history)
            if avg_time > self.target_frame_time * 1.3:
                self.throttle_level = min(2, self.throttle_level + 1)
            elif avg_time < self.target_frame_time * 0.7:
                self.throttle_level = max(0, self.throttle_level - 1)

    def should_skip_frame(self, frame_index: int) -> bool:
        """Returns True if the frame should be skipped due to terminal backpressure."""
        if self.throttle_level == 1:
            return frame_index % 2 != 0  # Skip every 2nd frame
        if self.throttle_level >= 2:
            return frame_index % 3 != 0  # Render only 1 out of 3 frames
        return False
