"""Studio audio spectrum equalizer, VU meters, beat pulse, and multi-theme terminal visualizer."""

from __future__ import annotations

import math
import re

# 32-band color mapping across 8 acoustic frequency zones
BAND_ZONE_COLORS = [
    # Sub-Bass (35Hz - 80Hz): Electric Cyan
    "\x1b[38;2;0;225;255m",
    "\x1b[38;2;0;225;255m",
    "\x1b[38;2;0;225;255m",
    "\x1b[38;2;0;225;255m",
    # Bass (80Hz - 250Hz): Emerald Green
    "\x1b[38;2;40;240;130m",
    "\x1b[38;2;40;240;130m",
    "\x1b[38;2;40;240;130m",
    "\x1b[38;2;40;240;130m",
    # Low-Mid (250Hz - 500Hz): Lime
    "\x1b[38;2;160;255;60m",
    "\x1b[38;2;160;255;60m",
    "\x1b[38;2;160;255;60m",
    "\x1b[38;2;160;255;60m",
    # Mid (500Hz - 1.2kHz): Amber Gold
    "\x1b[38;2;255;210;40m",
    "\x1b[38;2;255;210;40m",
    "\x1b[38;2;255;210;40m",
    "\x1b[38;2;255;210;40m",
    # High-Mid (1.2kHz - 3kHz): Coral Orange
    "\x1b[38;2;255;130;50m",
    "\x1b[38;2;255;130;50m",
    "\x1b[38;2;255;130;50m",
    "\x1b[38;2;255;130;50m",
    # Presence (3kHz - 6kHz): Warm Pink / Magenta
    "\x1b[38;2;255;70;130m",
    "\x1b[38;2;255;70;130m",
    "\x1b[38;2;255;70;130m",
    "\x1b[38;2;255;70;130m",
    # Treble (6kHz - 10kHz): Neon Purple
    "\x1b[38;2;215;65;255m",
    "\x1b[38;2;215;65;255m",
    "\x1b[38;2;215;65;255m",
    "\x1b[38;2;215;65;255m",
    # Air (10kHz - 16kHz): Bright Violet
    "\x1b[38;2;170;85;255m",
    "\x1b[38;2;170;85;255m",
    "\x1b[38;2;170;85;255m",
    "\x1b[38;2;170;85;255m",
]

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")

try:
    import wcwidth

    def _char_width(c: str) -> int:
        w = wcwidth.wcwidth(c)
        return max(0, w) if w >= 0 else 1

except ImportError:
    import unicodedata

    def _char_width(c: str) -> int:
        return 2 if unicodedata.east_asian_width(c) in ("F", "W") else 1


def _visible_len(s: str) -> int:
    clean = _ANSI_RE.sub("", s)
    return sum(_char_width(c) for c in clean)


def _fit_to_width(s: str, width: int) -> str:
    """Truncates or pads an ANSI-formatted string so its terminal display width is exactly width."""
    cur_w = _visible_len(s)
    if cur_w == width:
        return s
    if cur_w < width:
        return s + (" " * (width - cur_w))

    out: list[str] = []
    w_acc = 0
    i = 0
    n = len(s)
    while i < n:
        m = _ANSI_RE.match(s, i)
        if m:
            out.append(m.group(0))
            i = m.end()
            continue
        c = s[i]
        cw = _char_width(c)
        if w_acc + cw > width:
            break
        out.append(c)
        w_acc += cw
        i += 1
    out.append("\x1b[0m")
    if w_acc < width:
        out.append(" " * (width - w_acc))
    return "".join(out)


class SpectrumBarsRenderer:
    """
    Renders multi-theme studio audio spectrum equalizers:
    - Theme 'fountain': Symmetrical center-burst fountain with laser floating peaks & beat pulse
    - Theme 'matrix': Digital falling matrix cascade with quantum flux levels
    - Theme 'wave': Dual-trace CRT oscilloscope ribbon with mirrored bass reflection
    """

    THEME_FOUNTAIN = "fountain"
    THEME_MATRIX = "matrix"
    THEME_WAVE = "wave"
    THEMES = [THEME_FOUNTAIN, THEME_MATRIX, THEME_WAVE]

    BLOCK_GLYPHS = [" ", " ", "▂", "▃", "▄", "▅", "▆", "▇", "█"]
    PEAK_GLYPH = "▔"

    MATRIX_GLYPHS = [" ", "·", "╎", "┆", "│", "┃", "█"]
    MATRIX_PEAK = "▲"

    @classmethod
    def render_bars(
        cls,
        bands: list[float],
        peaks: list[float],
        max_rows: int = 8,
        bar_width: int = 1,
    ) -> str:
        """Renders vertical spectrum bars with floating peak indicators and gradient colors."""
        lines = cls.render_bar_lines(bands, peaks, max_rows=max_rows, bar_width=bar_width)
        return "\n".join(lines)

    @classmethod
    def render_bar_lines(
        cls,
        bands: list[float],
        peaks: list[float],
        max_rows: int = 8,
        bar_width: int = 1,
        theme: str = "fountain",
    ) -> list[str]:
        """Renders vertical spectrum bars as a list of lines with peak hold markers."""
        if not bands or max_rows <= 0:
            return []

        num_bands = len(bands)
        output_lines: list[str] = []

        if theme == cls.THEME_MATRIX:
            glyphs = cls.MATRIX_GLYPHS
            peak_char = cls.MATRIX_PEAK
        else:
            glyphs = cls.BLOCK_GLYPHS
            peak_char = cls.PEAK_GLYPH

        for row in range(max_rows, 0, -1):
            row_frac_lower = (row - 1) / max_rows
            row_frac_upper = row / max_rows

            line_chars: list[str] = []

            for b in range(num_bands):
                val = bands[b]
                peak = peaks[b] if b < len(peaks) else 0.0

                if theme == cls.THEME_MATRIX:
                    # Matrix cyberpunk theme: luminescent green & cyan
                    if val > 0.8:
                        color_code = "\x1b[38;2;180;255;120m"
                    elif val > 0.4:
                        color_code = "\x1b[38;2;40;255;120m"
                    else:
                        color_code = "\x1b[38;2;0;200;160m"
                elif theme == cls.THEME_FOUNTAIN:
                    # Symmetric center-burst: Center is Bass (Cyan/Emerald), wings are Treble (Violet)
                    dist = abs(b - (num_bands - 1) / 2.0)
                    frac = dist / max(1.0, (num_bands - 1) / 2.0)
                    c_idx = int(frac * (len(BAND_ZONE_COLORS) - 1))
                    color_code = BAND_ZONE_COLORS[min(len(BAND_ZONE_COLORS) - 1, c_idx)]
                else:
                    color_code = BAND_ZONE_COLORS[b % len(BAND_ZONE_COLORS)]

                if val >= row_frac_upper:
                    char = glyphs[-1]
                    seg = f"{color_code}{char * bar_width}\x1b[0m"
                elif val > row_frac_lower:
                    sub_frac = (val - row_frac_lower) / (row_frac_upper - row_frac_lower)
                    idx = int(sub_frac * (len(glyphs) - 1))
                    char = glyphs[max(1, min(len(glyphs) - 1, idx))]
                    seg = f"{color_code}{char * bar_width}\x1b[0m"
                elif peak >= row_frac_lower and peak < row_frac_upper:
                    seg = f"\x1b[1;37m{peak_char * bar_width}\x1b[0m"
                else:
                    seg = " " * bar_width

                line_chars.append(seg)

            output_lines.append("".join(line_chars))

        return output_lines

    @classmethod
    def render_oscilloscope(cls, samples: list[float], width: int = 60) -> str:
        """Renders a real-time vector time-domain oscilloscope waveform line in glowing cyan."""
        if not samples or width <= 0:
            return ""

        step = max(1, len(samples) // width)
        sub = [samples[i] for i in range(0, len(samples), step)][:width]

        wave_glyphs = ["_", ".", "-", "~", "=", "^", "~", "-", "."]
        chars: list[str] = ["\x1b[38;2;80;225;255m"]

        for s in sub:
            idx = int(((s + 1.0) / 2.0) * (len(wave_glyphs) - 1))
            idx = max(0, min(len(wave_glyphs) - 1, idx))
            chars.append(wave_glyphs[idx])

        chars.append("\x1b[0m")
        return "".join(chars)

    @classmethod
    def resample_bands(cls, bands: list[float], target_count: int) -> list[float]:
        """Smoothly interpolates/resamples frequency bands to target_count."""
        if target_count <= 0:
            return []
        if not bands:
            return [0.0] * target_count
        if len(bands) == target_count:
            return list(bands)
        if len(bands) == 1:
            return [bands[0]] * target_count

        resampled: list[float] = []
        n = len(bands)
        for i in range(target_count):
            pos = i * (n - 1) / max(1, target_count - 1)
            i0 = int(pos)
            i1 = min(n - 1, i0 + 1)
            frac = pos - i0
            val = bands[i0] * (1.0 - frac) + bands[i1] * frac
            resampled.append(val)
        return resampled

    @classmethod
    def _create_symmetric_fountain_order(
        cls, bands: list[float], peaks: list[float], count: int
    ) -> tuple[list[float], list[float]]:
        """
        Rearranges FFT frequency bands symmetrically so lowest bass frequencies sit directly
        at the center, erupting outward towards the left and right wings like a cyber fountain.
        Left wing: Treble -> Mid -> Bass
        Right wing: Bass -> Mid -> Treble
        """
        if count <= 0 or not bands:
            return [], []

        half = count // 2
        # Smoothly interpolate half bands from bass (0) to treble (len(bands)-1)
        wing_b = cls.resample_bands(bands, half)
        wing_p = cls.resample_bands(peaks, half)

        # Left wing: Treble (outer) down to Bass (inner)
        left_b = list(reversed(wing_b))
        left_p = list(reversed(wing_p))

        # Right wing: Bass (inner) up to Treble (outer)
        if count % 2 == 1:
            center_b = [bands[0]]
            center_p = [peaks[0] if peaks else 0.0]
            return left_b + center_b + wing_b, left_p + center_p + wing_p
        else:
            return left_b + wing_b, left_p + wing_p

    @classmethod
    def build_symmetric_axis(cls, target_width: int) -> str:
        """Constructs a symmetric Treble-Mid-Bass-Bass-Mid-Treble frequency axis spanning target_width."""
        if target_width < 16:
            return "T..M..B..M..T"[:target_width]

        # Standard symmetrical format: TREBLE ── MID ── BASS ── BASS ── MID ── TREBLE
        # Core keywords: TREBLE (6), MID (3), BASS (4), BASS (4), MID (3), TREBLE (6) = 26 chars
        # 5 separator gaps: g0, g1, g2 (center), g3, g4
        if target_width >= 31:  # at least 1 char per gap (26 + 5)
            avail = target_width - 26
            # Symmetrically distribute avail characters across 5 gaps
            g2 = max(1, avail // 5)
            rem = avail - g2
            g1 = max(1, (rem // 2) // 2)
            g0 = max(1, (rem - (g1 * 2)) // 2)
            total_gaps = g0 + g1 + g2 + g1 + g0
            diff = avail - total_gaps
            g2 += diff

            def make_sep(n: int) -> str:
                if n <= 1:
                    return " "
                if n == 2:
                    return "──"
                if n == 3:
                    return " ─ "
                if n == 4:
                    return " ── "
                d = n - 2
                return " " + "─" * d + " "

            s0 = make_sep(g0)
            s1 = make_sep(g1)
            s2 = make_sep(g2)
            line = f"TREBLE{s0}MID{s1}BASS{s2}BASS{s1}MID{s0}TREBLE"
            if len(line) == target_width:
                return line
            if len(line) < target_width:
                return line + ("─" * (target_width - len(line)))
            return line[:target_width]

        base = "TRB ─ MID ─ BAS ─ BAS ─ MID ─ TRB"
        return _fit_to_width(base, target_width)

    @classmethod
    def build_linear_axis(cls, target_width: int) -> str:
        """Constructs linear frequency axis SUB ... BASS ... MID ... PRESENCE ... AIR spanning target_width."""
        if target_width < 16:
            return "SUB..BAS..MID..AIR"[:target_width]
        if target_width >= 25:
            avail = target_width - 21
            gaps = 4
            g = max(1, avail // gaps)
            rem = avail - (g * gaps)

            def make_sep(n: int) -> str:
                if n <= 1:
                    return " "
                if n == 2:
                    return "──"
                if n == 3:
                    return " ─ "
                return " " + "─" * (n - 2) + " "

            s0 = make_sep(g)
            s1 = make_sep(g)
            s2 = make_sep(g)
            s3 = make_sep(g + rem)
            line = f"SUB{s0}BASS{s1}MID{s2}PRESENCE{s3}AIR"
            if len(line) == target_width:
                return line
            if len(line) < target_width:
                return line + ("─" * (target_width - len(line)))
            return line[:target_width]

        base = "SUB ─ BAS ─ MID ─ AIR"
        return _fit_to_width(base, target_width)

    @classmethod
    def render_panel(
        cls,
        bands: list[float],
        peaks: list[float],
        pcm_samples: list[float],
        max_cols: int,
        max_rows: int,
        theme: str = THEME_FOUNTAIN,
    ) -> list[str]:
        """
        Renders a studio-grade audio visualizer HUD panel with multi-theme support:
        - Theme 'fountain': Symmetrical center-burst cyber fountain with laser peaks & beat dynamics
        - Theme 'matrix': Digital falling quantum frequency cascade
        - Theme 'wave': Mirrored analog CRT ribbon oscilloscope
        Every returned line has exact printable width equal to max_cols.
        """
        if max_cols < 14 or max_rows < 3:
            return [" " * max_cols] * max_rows

        panel_lines: list[str] = []
        inner_w = max_cols - 2
        border_c = "\x1b[38;2;40;180;100m" if theme == cls.THEME_MATRIX else "\x1b[38;2;70;90;120m"
        reset = "\x1b[0m"

        # 1. Top Border with Responsive Themed Title
        if theme == cls.THEME_MATRIX:
            title = " ✦ AUDIO SPECTRUM MATRIX ✦ "
        elif theme == cls.THEME_WAVE:
            title = " ✦ AUDIO SPECTRUM WAVE ✦ "
        else:
            title = " ✦ AUDIO SPECTRUM FOUNTAIN ✦ "

        v_title = _visible_len(title)
        if v_title > inner_w:
            title = " AUDIO SPECTRUM "
            v_title = _visible_len(title)
        avail_bar = max(0, inner_w - v_title)
        left_bar = "─" * (avail_bar // 2)
        right_bar = "─" * (avail_bar - len(left_bar))
        title_color = (
            "\x1b[38;2;80;255;160;1m" if theme == cls.THEME_MATRIX else "\x1b[38;2;120;225;255;1m"
        )
        title_body = f"{left_bar}{title_color}{title}{border_c}{right_bar}"
        top_str = f"┌{_fit_to_width(title_body, inner_w)}┐"
        panel_lines.append(f"{border_c}{top_str}{reset}")

        # Feature budgets based on row availability
        show_vu = max_rows >= 6 and inner_w >= 24
        show_axis = max_rows >= 7 and inner_w >= 30
        show_osc = max_rows >= 8 and inner_w >= 20
        show_beat_hud = max_rows >= 10 and inner_w >= 28

        reserved_rows = 2  # Top and bottom borders
        if show_vu:
            reserved_rows += 1
        if show_axis:
            reserved_rows += 1
        if show_osc:
            reserved_rows += 1
        if show_beat_hud:
            reserved_rows += 1

        bar_rows = max(2, max_rows - reserved_rows)

        # 2. Stereo VU Meters with Overload Peak Clipping Indicator
        if show_vu:
            vu_bar_len = max(3, (inner_w - 28) // 2)
            l_peak = max((abs(s) for s in pcm_samples[::2]), default=0.0) if pcm_samples else 0.0
            r_peak = max((abs(s) for s in pcm_samples[1::2]), default=0.0) if pcm_samples else 0.0
            l_bars = min(vu_bar_len, int(l_peak * vu_bar_len))
            r_bars = min(vu_bar_len, int(r_peak * vu_bar_len))

            l_color = "\x1b[38;2;255;70;70m" if l_peak > 0.90 else "\x1b[38;2;50;230;130m"
            r_color = "\x1b[38;2;255;70;70m" if r_peak > 0.90 else "\x1b[38;2;50;230;130m"

            l_meter = (
                l_color + "■" * l_bars + "\x1b[38;2;60;75;95m" + "░" * (vu_bar_len - l_bars) + reset
            )
            r_meter = (
                r_color + "■" * r_bars + "\x1b[38;2;60;75;95m" + "░" * (vu_bar_len - r_bars) + reset
            )

            clip_tag = " \x1b[1;31m[PEAK]\x1b[0m" if (l_peak > 0.92 or r_peak > 0.92) else ""
            vu_line = f" VU [L] {l_meter} {int(l_peak * 100):>2}%  [R] {r_meter} {int(r_peak * 100):>2}%{clip_tag}"
            row_content = _fit_to_width(vu_line, inner_w)
            panel_lines.append(f"{border_c}│{reset}{row_content}{border_c}│{reset}")

        # 3. Frequency Spectrum Bars (Center-Burst Fountain, Matrix, or Wave)
        db_prefix_w = 6  # " -0dB "
        avail_band_w = max(4, inner_w - db_prefix_w)

        if theme == cls.THEME_FOUNTAIN:
            used_bands, used_peaks = cls._create_symmetric_fountain_order(
                bands, peaks, count=avail_band_w
            )
        else:
            used_bands = cls.resample_bands(bands, avail_band_w)
            used_peaks = cls.resample_bands(peaks, avail_band_w)

        bar_lines = cls.render_bar_lines(
            used_bands, used_peaks, max_rows=bar_rows, bar_width=1, theme=theme
        )

        for r_idx in range(bar_rows):
            # Calculate mathematically exact dBFS level for this row on a 60 dB dynamic range scale
            row_db = -(r_idx / max(1, bar_rows - 1)) * 60.0
            lbl = f"{int(round(row_db)):>3}dB"
            bar_content = bar_lines[r_idx] if r_idx < len(bar_lines) else ""
            content_str = f"\x1b[38;2;130;150;175m{lbl} {reset}{bar_content}"
            row_content = _fit_to_width(content_str, inner_w)
            panel_lines.append(f"{border_c}│{reset}{row_content}{border_c}│{reset}")

        # 4. Frequency Axis (Symmetric for Fountain, Linear for Matrix/Wave)
        if show_axis:
            prefix_pad = " " * db_prefix_w
            if theme == cls.THEME_FOUNTAIN:
                axis_body = cls.build_symmetric_axis(avail_band_w)
            else:
                axis_body = cls.build_linear_axis(avail_band_w)
            axis_line = f"{prefix_pad}{axis_body}"
            row_content = _fit_to_width(f"\x1b[38;2;110;135;165m{axis_line}", inner_w)
            panel_lines.append(f"{border_c}│{row_content}{border_c}│{reset}")

        # 5. Oscilloscope Waveform Line
        if show_osc:
            osc_width = max(8, inner_w - 7)
            osc_str = cls.render_oscilloscope(pcm_samples, width=osc_width)
            osc_line = f" WAVE:{osc_str}"
            row_content = _fit_to_width(f"\x1b[38;2;140;160;185m{osc_line}", inner_w)
            panel_lines.append(f"{border_c}│{row_content}{border_c}│{reset}")

        # 6. Live Beat Pulse Energy Dynamics & Studio HUD
        if show_beat_hud:
            # Calculate instantaneous RMS energy
            rms = (
                math.sqrt(sum(s * s for s in pcm_samples) / max(1, len(pcm_samples)))
                if pcm_samples
                else 0.0
            )
            beat_meter_len = max(4, min(10, inner_w - 38))
            beat_fill = min(beat_meter_len, int(rms * 2.8 * beat_meter_len))
            beat_bar = (
                "\x1b[38;2;255;180;40m"
                + "▰" * beat_fill
                + "\x1b[38;2;60;70;85m"
                + "░" * (beat_meter_len - beat_fill)
                + reset
            )

            if theme == cls.THEME_MATRIX:
                hud_txt = f" [✦ BEAT: {beat_bar} │ 48kHz Stereo │ 32-Band FFT Engine │ MATRIX]"
            elif theme == cls.THEME_WAVE:
                hud_txt = f" [✦ BEAT: {beat_bar} │ 48kHz Stereo │ 32-Band FFT Engine │ CRT WAVE]"
            else:
                hud_txt = f" [✦ BEAT: {beat_bar} │ 48kHz Stereo 16-bit │ 32-Band FFT Engine]"

            # Strict visible length truncation and padding
            v_hud = _visible_len(hud_txt)
            if v_hud > inner_w:
                hud_txt = " [48kHz Stereo 16-bit | 32-Band FFT Engine]"
            row_content = _fit_to_width(f"\x1b[38;2;100;125;155m{hud_txt}", inner_w)
            panel_lines.append(f"{border_c}│{row_content}{border_c}│{reset}")

        # 7. Bottom Border
        bot_str = f"└{'─' * inner_w}┘"
        panel_lines.append(f"{border_c}{bot_str}{reset}")

        # Ensure exact count of rows and exact visible width for every line
        while len(panel_lines) < max_rows:
            panel_lines.insert(
                len(panel_lines) - 1,
                f"{border_c}│{reset}{' ' * inner_w}{border_c}│{reset}",
            )

        # Truncate to max_rows and strictly guarantee exact visible width for every line
        result_lines: list[str] = []
        for line in panel_lines[:max_rows]:
            result_lines.append(_fit_to_width(line, max_cols))

        return result_lines
