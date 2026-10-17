"""Interactive pre-flight hardware assessment and user consent modal."""

from __future__ import annotations

import sys

from ...text_safety import safe_text
from ..core.input_parser import InputParser, KeyEvent, MouseEvent
from ..core.lifecycle import TerminalSessionContext
from ..decoders.probe import MediaMetadata
from .capacity_scorer import CapacityScorer, HardwareProfile
from .telemetry_probe import DeviceDiagnosticsProbe, DeviceTelemetry


class PreflightConsentModal:
    """Renders hardware diagnostic HUD and prompts user for playback confirmation."""

    @classmethod
    def render_modal_text(
        cls,
        telem: DeviceTelemetry,
        profile: HardwareProfile,
        media_name: str,
        media_details: str,
        critical_reason: str = "",
        cols: int = 80,
    ) -> str:
        """Builds formatted ANSI string for the pre-flight diagnostic assessment card."""
        lines = [
            "\n\x1b[1;36m┌─ 🔱 PINAK MEDIA ENGINE — HARDWARE ASSESSMENT & CONSENT ──────────────────────┐\x1b[0m",
            "│                                                                               │",
            "│  \x1b[1mCURRENT DEVICE TELEMETRY:\x1b[0m                                                    │",
            f"│  • CPU: {telem.cpu_cores_logical} Logical Cores ({telem.cpu_cores_physical} Physical) | Load: {telem.cpu_usage_pct:.1f}%                      │",
            f"│  • Memory: {telem.ram_available_mb:.0f} MB Available of {telem.ram_total_mb:.0f} MB [{telem.ram_usage_pct:.0f}% Used]                     │",
            f"│  • Graphics Acceleration: {'Available (' + telem.gpu_acceleration + ')' if telem.gpu_acceleration else 'Not detected (CPU Software Decode)'}    │",
            f"│  • Power Mode: {'Battery (' + str(telem.battery_pct) + '%)' if telem.is_on_battery else 'AC Connected [Full Performance]'}                       │",
            f"│  • Terminal Canvas: {telem.terminal_type} ({'TrueColor' if telem.has_truecolor else 'ANSI 256c'})                      │",
            "│                                                                               │",
            f"│  \x1b[1mTARGET MEDIA:\x1b[0m {media_name[:60]:<60} │",
            f"│  • Spec: {media_details[:66]:<66} │",
            f"│  • Hardware Assessment: {profile.recommendation[:53]:<53} │",
        ]
        if critical_reason:
            lines.append(
                "│  \x1b[1;31mDEVICE NEEDS ATTENTION BEFORE PLAYBACK:\x1b[0m                                       │"
            )
            for reason in critical_reason.split(" | "):
                lines.append(f"│  \x1b[1;31m• {reason[:72]:<74}\x1b[0m │")
        lines.extend(
            [
                "│                                                                               │",
                "│  \x1b[1;33mWould you like to proceed with playing this media?\x1b[0m                           │",
                "│                                                                               │",
                "│      \x1b[1;32m[ ▶ Yes, Start Playback (Enter) ]\x1b[0m        \x1b[1;31m[ ✕ No, Cancel & Exit (Esc) ]\x1b[0m  │",
                "│                                                                               │",
                "\x1b[1;36m└───────────────────────────────────────────────────────────────────────────────┘\x1b[0m\n",
            ]
        )
        return "\n".join(lines)

    @classmethod
    def is_critical_situation(
        cls,
        telem: DeviceTelemetry,
        profile: HardwareProfile,
        media_meta: MediaMetadata,
    ) -> tuple[bool, str]:
        """
        Determines if host device is in a critical resource constraint:
        - Battery at or below 15% while unplugged
        - Measured available RAM below the playback working set
        - Measured hardware temperature at or above 85°C
        """
        reasons: list[str] = []
        if telem.is_on_battery and telem.battery_pct is not None and telem.battery_pct <= 15:
            reasons.append(f"Low battery ({telem.battery_pct}%)")

        required_mb = 512.0
        if media_meta.media_type == "video" and media_meta.width > 0 and media_meta.height > 0:
            # Decode and display can hold several RGB frames plus audio and GUI buffers.
            required_mb = min(
                2048.0,
                max(512.0, 384.0 + media_meta.width * media_meta.height * 32 / 1048576),
            )
        if telem.measurements_available and telem.ram_available_mb < required_mb:
            reasons.append(
                f"Low RAM ({telem.ram_available_mb:.0f}MB free; playback needs about {required_mb:.0f}MB)"
            )

        if telem.temperature_c is not None and telem.temperature_c >= 85.0:
            reasons.append(f"High temperature ({telem.temperature_c:.0f}°C)")

        if reasons:
            return True, " | ".join(reasons)
        return False, ""

    @classmethod
    def prompt_user(
        cls,
        media_meta: MediaMetadata,
        auto_consent: bool = False,
        force_prompt: bool = False,
    ) -> bool:
        """
        Interactively evaluates device capacity and asks user for playback confirmation
        ONLY when critical hardware resource constraints are detected.
        Returns True if user selects 'Yes' or if system is healthy, False if user selects 'No'.
        """
        if auto_consent:
            return True

        telem = DeviceDiagnosticsProbe.inspect()
        is_4k = media_meta.width >= 3840 or media_meta.height >= 2160
        profile = CapacityScorer.evaluate(telem, media_type=media_meta.media_type, is_4k=is_4k)

        # Check for critical hardware situations
        is_critical, reason = cls.is_critical_situation(telem, profile, media_meta)
        if not is_critical and not force_prompt:
            # Device is healthy and normal: bypass prompt automatically
            return True

        if not sys.stdin.isatty():
            print(
                f"Playback needs confirmation: {reason or 'forced preflight check'}. Run in an interactive terminal.",
                file=sys.stderr,
            )
            return False

        media_desc = f"{media_meta.media_type.upper()}"
        if media_meta.width > 0 and media_meta.height > 0:
            media_desc += f" {media_meta.width}x{media_meta.height}"
        if media_meta.fps > 0:
            media_desc += f" @ {media_meta.fps:.0f} FPS"
        if media_meta.duration_seconds > 0:
            media_desc += f" | Dur: {int(media_meta.duration_seconds)}s"

        modal_text = cls.render_modal_text(
            telem=telem,
            profile=profile,
            media_name=safe_text(media_meta.file_path.name),
            media_details=media_desc,
            critical_reason=reason,
        )

        with TerminalSessionContext(enable_mouse=True):
            try:
                sys.stdout.write(modal_text)
                sys.stdout.flush()
            except OSError:
                return False

            parser = InputParser()
            while True:
                events = parser.poll_events(timeout_seconds=0.1)
                for ev in events:
                    if isinstance(ev, KeyEvent):
                        k = ev.key.lower()
                        if k in ("enter", "y", "space"):
                            return True
                        if k in ("esc", "n", "q") or (ev.key == "c" and ev.ctrl):
                            return False
                    elif isinstance(ev, MouseEvent):
                        # Keyboard consent avoids ambiguous hit targets when the
                        # terminal wraps or clips the assessment card.
                        continue
