"""Micro-second host device telemetry probe."""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass

from ...utils import trusted_which


@dataclass
class DeviceTelemetry:
    """Snapshot of host system compute, memory, and acceleration telemetry."""

    cpu_cores_logical: int
    cpu_cores_physical: int
    cpu_usage_pct: float
    ram_total_mb: float
    ram_available_mb: float
    ram_usage_pct: float
    gpu_acceleration: str | None
    is_on_battery: bool
    battery_pct: int | None
    terminal_type: str
    has_truecolor: bool
    measurements_available: bool = True
    temperature_c: float | None = None


class DeviceDiagnosticsProbe:
    """Interrogates host hardware telemetry in <20ms."""

    @classmethod
    def inspect(cls) -> DeviceTelemetry:
        cores_logical = os.cpu_count() or 4
        cores_physical = max(1, cores_logical // 2)

        # 1. CPU & RAM via psutil if present, else fallback heuristics
        cpu_usage = 0.0
        ram_total = 0.0
        ram_avail = 0.0
        measured = False
        temperature_c = None

        try:
            import psutil  # type: ignore[import-untyped]

            cpu_usage = psutil.cpu_percent(interval=None)
            mem = psutil.virtual_memory()
            ram_total = mem.total / (1024 * 1024)
            ram_avail = mem.available / (1024 * 1024)
            measured = True
            sensors = getattr(psutil, "sensors_temperatures", None)
            if sensors is not None:
                try:
                    readings = sensors()
                    temperatures = [
                        float(entry.current)
                        for entries in readings.values()
                        for entry in entries
                        if getattr(entry, "current", None) is not None
                        and 0 < float(entry.current) < 150
                    ]
                    if temperatures:
                        temperature_c = max(temperatures)
                except Exception:
                    pass
        except Exception:
            # Fallback estimation
            pass

        ram_usage_pct = max(0.0, min(100.0, (1.0 - (ram_avail / max(1.0, ram_total))) * 100.0))

        # 2. GPU decode acceleration detection
        gpu_accel = cls._detect_gpu_accel()

        # 3. Battery / Power state
        battery_state = cls._detect_battery()

        # 4. Terminal properties
        has_truecolor = (
            os.environ.get("COLORTERM", "").lower() in ("truecolor", "24bit")
            or "WT_SESSION" in os.environ
            or "kitty" in os.environ.get("TERM", "").lower()
        )
        term_name = os.environ.get("TERM_PROGRAM") or os.environ.get("TERM", "terminal")

        return DeviceTelemetry(
            cpu_cores_logical=cores_logical,
            cpu_cores_physical=cores_physical,
            cpu_usage_pct=cpu_usage,
            ram_total_mb=ram_total,
            ram_available_mb=ram_avail,
            ram_usage_pct=ram_usage_pct,
            gpu_acceleration=gpu_accel,
            is_on_battery=battery_state.get("on_battery", False),
            battery_pct=battery_state.get("percent"),
            terminal_type=term_name,
            has_truecolor=has_truecolor,
            measurements_available=measured,
            temperature_c=temperature_c,
        )

    @classmethod
    def _detect_gpu_accel(cls) -> str | None:
        """Probes for hardware acceleration capabilities."""
        ffmpeg_bin = trusted_which("ffmpeg")
        if not ffmpeg_bin:
            return None
        try:
            res = subprocess.run(
                [ffmpeg_bin, "-hwaccels"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=1.0,
            )
            avail = res.stdout.lower()
            if os.name == "nt":
                for cand in ("dxva2", "d3d11va", "cuda"):
                    if cand in avail:
                        return cand
            elif sys.platform == "darwin":
                if "videotoolbox" in avail:
                    return "videotoolbox"
            else:
                for cand in ("vaapi", "cuda", "vdpau"):
                    if cand in avail:
                        return cand
        except Exception:
            pass
        return None

    @classmethod
    def _detect_battery(cls) -> dict:
        """Inspects laptop battery state."""
        try:
            import psutil  # type: ignore[import-untyped]

            b = psutil.sensors_battery()
            if b is not None:
                return {"on_battery": not b.power_plugged, "percent": int(b.percent)}
        except Exception:
            pass
        return {"on_battery": False, "percent": 100}
