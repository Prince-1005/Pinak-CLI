"""Video quality profile manager supporting 1080p, 720p, 480p, 360p, and Auto-Fit."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class QualityProfile:
    id: str
    label: str
    width: int
    height: int


class QualityProfileManager:
    """Manages dynamic resolution downscaling targets for video playback."""

    PROFILES: dict[str, QualityProfile] = {
        "native": QualityProfile(id="native", label="Actual Size (Native)", width=0, height=0),
        "auto": QualityProfile(id="auto", label="Fit Window", width=0, height=0),
        "1080p": QualityProfile(id="1080p", label="1080p (Full HD)", width=1920, height=1080),
        "720p": QualityProfile(id="720p", label="720p (HD)", width=1280, height=720),
        "480p": QualityProfile(id="480p", label="480p (SD)", width=854, height=480),
        "360p": QualityProfile(id="360p", label="360p (Low Bandwidth)", width=640, height=360),
    }

    PROFILE_ORDER = ["native", "auto", "1080p", "720p", "480p", "360p"]

    def __init__(self, default_profile: str = "native") -> None:
        self.active_profile_id = default_profile if default_profile in self.PROFILES else "native"

    @property
    def current_profile(self) -> QualityProfile:
        return self.PROFILES[self.active_profile_id]

    def cycle_profile(self) -> QualityProfile:
        """Cycles to the next resolution profile."""
        cur_idx = self.PROFILE_ORDER.index(self.active_profile_id)
        next_idx = (cur_idx + 1) % len(self.PROFILE_ORDER)
        self.active_profile_id = self.PROFILE_ORDER[next_idx]
        return self.current_profile

    def get_target_dimensions(
        self,
        term_cols: int,
        term_rows: int,
        native_w: int = 0,
        native_h: int = 0,
        is_video: bool = False,
    ) -> tuple[int, int]:
        """Calculates decoder target dimensions for current profile."""
        prof = self.current_profile
        max_virt_w = max(16, term_cols)
        max_virt_h = max(16, term_rows * 2)

        if prof.id == "native":
            if is_video:
                # Video files: By default max of original video resolution
                if native_w > 0 and native_h > 0:
                    tw = native_w - (native_w % 2)
                    th = native_h - (native_h % 2)
                    return (max(16, tw), max(16, th))
                return (1920, 1080)
            if native_w > 0 and native_h > 0:
                scale = min(1.0, max_virt_w / native_w, max_virt_h / native_h)
                scaled_w = max(16, int(native_w * scale))
                scaled_h = max(16, int(native_h * scale))
                if scaled_h % 2 != 0:
                    scaled_h -= 1
                return (scaled_w, max(16, scaled_h))
            return (max_virt_w, max_virt_h)

        if prof.id == "auto":
            if native_w > 0 and native_h > 0:
                scale = min(max_virt_w / native_w, max_virt_h / native_h)
                scaled_w = max(16, int(native_w * scale))
                scaled_h = max(16, int(native_h * scale))
                if scaled_h % 2 != 0:
                    scaled_h -= 1
                return (scaled_w, max(16, scaled_h))
            # For Mode 2 Half-Block: 1 col = 1 px wide, 1 row = 2 px high
            return (max_virt_w, max_virt_h)

        return (prof.width, prof.height)
