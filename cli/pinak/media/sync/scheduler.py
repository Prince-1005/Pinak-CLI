"""Video frame synchronization scheduler with drift compensation and frame dropping."""

from __future__ import annotations

from enum import Enum


class SyncAction(Enum):
    RENDER_NOW = "render_now"
    SLEEP_WAIT = "sleep_wait"
    RENDER_FAST = "render_fast"
    DROP_FRAME = "drop_frame"


class VideoFrameScheduler:
    """Calculates PTS drift and determines frame render or drop actions."""

    SYNC_TOLERANCE_SEC: float = 0.015  # 15 milliseconds
    MAX_LAG_TOLERANCE_SEC: float = 0.060  # 60 milliseconds

    @classmethod
    def evaluate(
        cls,
        video_pts: float,
        master_pts: float,
    ) -> tuple[SyncAction, float]:
        """
        Evaluates drift = video_pts - master_pts.
        Returns (SyncAction, sleep_duration_sec).
        """
        drift = video_pts - master_pts

        # 1. In Sync: Within 15ms window
        if abs(drift) <= cls.SYNC_TOLERANCE_SEC:
            return SyncAction.RENDER_NOW, 0.0

        # 2. Video is Ahead: Yield CPU and wait
        if drift > cls.SYNC_TOLERANCE_SEC:
            sleep_duration = max(0.001, drift - 0.005)
            return SyncAction.SLEEP_WAIT, sleep_duration

        # 3. Minor Video Lag (-15ms to -60ms): Render immediately without yield
        if drift >= -cls.MAX_LAG_TOLERANCE_SEC:
            return SyncAction.RENDER_FAST, 0.0

        # 4. Severe Video Lag (< -60ms): Drop frame to allow video to catch up!
        return SyncAction.DROP_FRAME, 0.0
