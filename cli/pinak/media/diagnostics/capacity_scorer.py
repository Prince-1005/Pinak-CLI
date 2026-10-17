"""Hardware capacity scoring and playback profile classification."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .telemetry_probe import DeviceTelemetry


@dataclass
class HardwareProfile:
    tier: Literal["high", "mid", "constrained"]
    capacity_score: float
    recommendation: str
    suggested_resolution: str
    suggested_fps: float


class CapacityScorer:
    """Evaluates host telemetry to grade hardware and suggest tuned playback settings."""

    @classmethod
    def evaluate(
        cls, telem: DeviceTelemetry, media_type: str = "video", is_4k: bool = False
    ) -> HardwareProfile:
        # 1. CPU Score: core count & load
        core_factor = min(100.0, telem.cpu_cores_logical * 12.5)
        load_factor = max(0.0, 1.0 - (telem.cpu_usage_pct / 100.0))
        s_cpu = core_factor * load_factor

        # 2. RAM Score: available MB
        s_ram = max(0.0, min(100.0, (telem.ram_available_mb / 4096.0) * 100.0))

        # 3. GPU Score
        s_gpu = 100.0 if telem.gpu_acceleration else 40.0

        # 4. Power Score
        s_pwr = 100.0 if not telem.is_on_battery else float(telem.battery_pct or 50)

        # Composite Capacity Score
        c_sys = (0.35 * s_cpu) + (0.30 * s_ram) + (0.25 * s_gpu) + (0.10 * s_pwr)

        if c_sys >= 75.0 and not is_4k:
            tier: Literal["high", "mid", "constrained"] = "high"
            rec = "High-performance hardware detected. Running native resolution at 60 FPS."
            res = "1080p"
            fps = 60.0
        elif c_sys >= 50.0:
            tier = "mid"
            rec = "Moderate hardware workload. Mode 2 Half-Block recommended at 720p 30-60 FPS."
            res = "720p"
            fps = 30.0
        else:
            tier = "constrained"
            rec = "Constrained device resources. Downscaling to 480p or ASCII mode for stability."
            res = "480p"
            fps = 24.0

        return HardwareProfile(
            tier=tier,
            capacity_score=round(c_sys, 1),
            recommendation=rec,
            suggested_resolution=res,
            suggested_fps=fps,
        )
