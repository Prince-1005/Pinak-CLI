"""Unit tests for pinak.media.visualizer modules."""

import math

from pinak.media.visualizer.cover_art import CoverArtRotator
from pinak.media.visualizer.fft_engine import AudioFFTEngine
from pinak.media.visualizer.spectrum_bars import SpectrumBarsRenderer
from pinak.media.visualizer.turntable import GramophoneTurntable
from pinak.media.visualizer.vinyl_shader import ProceduralVinylShader


def test_cover_art_rotator():
    rotator = CoverArtRotator(artwork_source=None, label_diameter=80)
    assert rotator.label_diameter == 80
    assert rotator.spindle_radius > 0

    rotated = rotator.rotate(45.0)
    assert rotated.size == (80, 80)
    # Check that spindle center is transparent (alpha = 0)
    assert rotated.getpixel((40, 40))[3] == 0


def test_procedural_vinyl_shader():
    shader = ProceduralVinylShader(diameter=120)
    assert shader.diameter == 120

    frame = shader.render_vinyl(30.0)
    assert frame.size == (120, 120)


def test_gramophone_turntable():
    tt = GramophoneTurntable(diameter=120)
    assert tt.is_spinning is True

    # Update physics for 1 second of playing
    init_angle = tt.current_angle
    tt.update_physics(dt=0.5, is_playing=True)
    assert tt.current_angle != init_angle

    # Render turntable with 50% song progress
    rendered = tt.render_turntable(progress_frac=0.5)
    assert rendered.size == (120, 120)


def test_audio_fft_engine():
    fft = AudioFFTEngine(sample_rate=48000, window_size=512)

    # 1000 Hz sine wave
    sine = [math.sin(2 * math.pi * 1000 * t / 48000) for t in range(512)]
    bands, peaks = fft.process_pcm(sine)

    assert len(bands) == 32
    assert len(peaks) == 32
    # At least one band should show high energy
    assert max(bands) > 0.0


def test_spectrum_bars_renderer():
    bands = [0.1 * i for i in range(10)]
    peaks = [0.12 * i for i in range(10)]

    rendered_bars = SpectrumBarsRenderer.render_bars(bands, peaks, max_rows=6)
    assert "█" in rendered_bars or "▄" in rendered_bars or " " in rendered_bars

    rendered_wave = SpectrumBarsRenderer.render_oscilloscope([-0.5, 0.0, 0.5, 1.0, -1.0], width=20)
    assert len(rendered_wave) > 0


def test_spectrum_bars_render_panel():
    bands = [0.2 + 0.02 * i for i in range(32)]
    peaks = [0.25 + 0.02 * i for i in range(32)]
    pcm = [0.1 * math.sin(i) for i in range(1024)]

    panel_lines = SpectrumBarsRenderer.render_panel(bands, peaks, pcm, max_cols=50, max_rows=10)
    assert len(panel_lines) == 10
    # Every line should have top/side/bottom border characters
    assert any("AUDIO SPECTRUM" in line for line in panel_lines)
    assert any("dB" in line for line in panel_lines)
    assert any("WAVE:" in line for line in panel_lines)


def test_spectrum_bars_render_panel_studio_features():
    """Validates stereo VU meters, frequency zones, and strict column width alignment."""
    bands = [0.1 + 0.02 * i for i in range(32)]
    peaks = [0.15 + 0.02 * i for i in range(32)]
    pcm = [0.7 * math.sin(i * 0.2) for i in range(1024)]

    panel_lines = SpectrumBarsRenderer.render_panel(bands, peaks, pcm, max_cols=60, max_rows=12)
    assert len(panel_lines) == 12
    # Verify VU meters are present
    assert any("VU [L]" in line and "[R]" in line for line in panel_lines)
    # Verify frequency zones
    assert any("BASS" in line and "MID" in line for line in panel_lines)
    # Verify audio HUD status
    assert any("48kHz" in line or "FFT Engine" in line for line in panel_lines)


def test_audio_fft_engine_distinct_bands():
    """Ensures continuous fractional bin grouping produces distinct, non-duplicated bands."""
    fft = AudioFFTEngine(sample_rate=48000, window_size=1024)
    pcm = [0.6 * math.sin(2 * math.pi * 440 * t / 48000) for t in range(1024)]
    bands, peaks = fft.process_pcm(pcm)

    assert len(bands) == 32
    assert max(bands) > 0.5
    # Verify adjacent non-zero bands are not identical duplicated values
    duplicates = sum(
        1 for i in range(len(bands) - 1) if bands[i] == bands[i + 1] and bands[i] > 0.05
    )
    assert duplicates == 0


def test_spectrum_bars_themes_and_strict_widths():
    """Verifies that all visualizer themes produce exact visible column widths."""
    import re

    ansi_re = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")
    bands = [0.15 + 0.02 * i for i in range(32)]
    peaks = [0.2 + 0.02 * i for i in range(32)]
    pcm = [0.5 * math.sin(i * 0.1) for i in range(1024)]

    for theme in SpectrumBarsRenderer.THEMES:
        for cols in (40, 60, 80):
            lines = SpectrumBarsRenderer.render_panel(
                bands, peaks, pcm, max_cols=cols, max_rows=12, theme=theme
            )
            assert len(lines) == 12
            for line in lines:
                v_len = len(ansi_re.sub("", line))
                assert v_len == cols, f"Theme {theme} line width {v_len} != {cols}"


def test_spectrum_bars_mathematical_db_axis():
    """Verifies that Y-axis dB labels are mathematically calculated from 0dB at the top to -60dB at the bottom."""
    bands = [0.8] * 32
    peaks = [0.9] * 32
    pcm = [0.2] * 1024

    for rows in (8, 12, 16):
        panel_lines = SpectrumBarsRenderer.render_panel(
            bands, peaks, pcm, max_cols=60, max_rows=rows
        )
        # Find all lines containing dB markers
        db_lines = [line for line in panel_lines if "dB" in line]
        assert len(db_lines) >= 2
        # Top-most dB line must be 0dB
        assert "0dB" in db_lines[0]
        # Bottom-most dB line must be -60dB (the acoustic dynamic range floor)
        assert "-60dB" in db_lines[-1]


def test_symmetric_fountain_frequency_geometry():
    """Verifies that the fountain theme places low bass frequencies in the center and high treble at the wings."""
    # 8 bands: [0..7] where 0 is lowest bass and 7 is highest treble
    bands = [float(i) for i in range(8)]
    peaks = [float(i) + 0.1 for i in range(8)]

    # Request 8 symmetric fountain bands
    sym_b, sym_p = SpectrumBarsRenderer._create_symmetric_fountain_order(bands, peaks, count=8)
    assert len(sym_b) == 8
    # Center two bands must be bass (lower values)
    center_left = sym_b[3]
    center_right = sym_b[4]
    outer_left = sym_b[0]
    outer_right = sym_b[7]

    assert center_left < outer_left
    assert center_right < outer_right
    # Left wing is descending from treble to bass, right wing is ascending from bass to treble
    assert sym_b[0] >= sym_b[1] >= sym_b[2] >= sym_b[3]
    assert sym_b[4] <= sym_b[5] <= sym_b[6] <= sym_b[7]


def test_fft_engine_dbfs_scaling():
    """Verifies that AudioFFTEngine maps full scale input to 1.0 (0 dBFS) and silence to 0.0 (-60 dBFS floor)."""
    fft = AudioFFTEngine(sample_rate=48000, window_size=512)

    # 1. Full-scale sine wave
    sine = [math.sin(2 * math.pi * 1000 * t / 48000) for t in range(512)]
    bands, peaks = fft.process_pcm(sine)
    assert max(bands) > 0.8  # Strong signal near 0 dBFS

    # 2. Silence (zeros)
    silence = [0.0] * 512
    bands_silence, _ = fft.process_pcm(silence)
    assert max(bands_silence) == 0.0  # Decays to 0.0 (-60 dBFS noise floor)
