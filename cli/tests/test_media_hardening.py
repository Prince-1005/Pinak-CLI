"""Unit and regression tests for hardened media subsystems and edge-case mitigations."""

from __future__ import annotations

import io
import wave
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from pinak.media.core.input_parser import InputParser, MouseEvent
from pinak.media.core.lifecycle import TerminalSessionContext
from pinak.media.decoders.audio_decoder import AudioDecoder
from pinak.media.decoders.image_loader import ImageLoader
from pinak.media.decoders.video_decoder import VideoDecoder
from pinak.media.picker.scanner import MediaScanner
from pinak.media.renderers.pixel_sixel import SixelRenderer
from pinak.media.visualizer.turntable import GramophoneTurntable


def test_audio_decoder_pure_python_wav_fallback(tmp_path: Path):
    """Verifies that AudioDecoder uses standard library wave fallback when FFmpeg is absent."""
    wav_file = tmp_path / "test_stereo.wav"
    # Create valid PCM WAV file
    with wave.open(str(wav_file), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(48000)
        # 1000 frames of dummy PCM
        w.writeframes(b"\x00\x10\x00\x20" * 1000)

    # Force FFmpeg not found
    with patch.object(AudioDecoder, "find_ffmpeg", return_value=None):
        decoder = AudioDecoder(wav_file)
        decoder.start()

        chunk = decoder.read_chunk()
        assert chunk is not None
        assert chunk.sample_rate == 48000
        assert chunk.channels == 2
        assert len(chunk.pcm_bytes) > 0

        # Verify visualizer buffer has non-zero samples
        samples = decoder.get_visualizer_samples(count=128)
        assert len(samples) == 128
        decoder.close()


def test_audio_decoder_procedural_fallback_for_non_wav(tmp_path: Path):
    """Verifies that AudioDecoder procedural synthesizer generates dynamic samples when FFmpeg is absent."""
    mp3_file = tmp_path / "fake_song.mp3"
    mp3_file.write_bytes(b"ID3" + b"\x55\xaa" * 200)

    with patch.object(AudioDecoder, "find_ffmpeg", return_value=None):
        decoder = AudioDecoder(mp3_file)
        decoder.start()

        chunk = decoder.read_chunk()
        assert chunk is not None
        assert len(chunk.pcm_bytes) > 0

        samples = decoder.get_visualizer_samples(count=64)
        assert len(samples) == 64
        # Verify samples are normalized within [-1.0, 1.0] and contain non-zero wave data
        assert any(abs(s) > 0.01 for s in samples)
        assert all(-1.0 <= s <= 1.0 for s in samples)
        decoder.close()


def test_input_parser_mouse_drag_debouncing():
    """Verifies that InputParser debounces high-frequency mouse drag motion events."""
    parser = InputParser()
    now = 100.0

    # 1. First move event should be accepted
    with patch("time.perf_counter", return_value=now):
        parser._buffer.extend(b"\x1b[<32;10;20M")  # button 32 is move
        events = parser.poll_events()
        assert len(events) == 1
        assert isinstance(events[0], MouseEvent)
        assert events[0].is_move

    # 2. Second move event arriving 2ms later (< 16ms interval) should be debounced/dropped
    with patch("time.perf_counter", return_value=now + 0.002):
        parser._buffer.extend(b"\x1b[<32;12;22M")
        events = parser.poll_events()
        assert len(events) == 0

    # 3. Third move event arriving 20ms later should be accepted
    with patch("time.perf_counter", return_value=now + 0.020):
        parser._buffer.extend(b"\x1b[<32;15;25M")
        events = parser.poll_events()
        assert len(events) == 1

    # 4. Click release (is_move=False) must never be dropped even if immediate
    with patch("time.perf_counter", return_value=now + 0.021):
        parser._buffer.extend(b"\x1b[<0;15;25m")  # release
        events = parser.poll_events()
        assert len(events) == 1
        assert not events[0].is_move


def test_sixel_fast_quantization_and_rendering():
    """Verifies that SixelRenderer encodes image frames without errors."""
    renderer = SixelRenderer()
    im = Image.new("RGB", (80, 60), (0, 120, 255))
    sixel_str = renderer.render_frame(im, target_cols=40, target_rows=20)

    assert sixel_str.startswith('\x1bPq"1;1;')
    assert sixel_str.endswith("\x1b\\")
    assert "#0;" in sixel_str


def test_image_loader_decompression_bomb_protection(tmp_path: Path):
    """Verifies that ImageLoader safely handles DecompressionBombError."""
    img_file = tmp_path / "gigapixel_mock.png"
    im = Image.new("RGB", (200, 200), (50, 100, 150))
    im.save(img_file)

    # Simulate DecompressionBombError on standard open
    original_open = Image.open

    def bomb_side_effect(fp, *args, **kwargs):
        if getattr(bomb_side_effect, "called", False):
            return original_open(fp, *args, **kwargs)
        bomb_side_effect.called = True
        raise Image.DecompressionBombError("Image size exceeds limit")

    bomb_side_effect.called = False

    with patch("PIL.Image.open", side_effect=bomb_side_effect):
        loaded = ImageLoader.load(img_file)
        assert loaded is not None
        assert loaded.width > 0
        assert loaded.height > 0
        assert len(loaded.frames) == 1


def test_directory_scanner_max_entries_cap(tmp_path: Path):
    """Verifies that MediaScanner caps directory scanning at max_entries."""
    folder = tmp_path / "large_dir"
    folder.mkdir()

    # Create 25 media files
    for i in range(25):
        (folder / f"track_{i:02d}.mp3").write_bytes(b"dummy")

    # Scan with max_entries=10
    items = MediaScanner.scan_directory(folder, max_entries=10)

    # Should contain: parent dir + 10 items + 1 capped warning item
    assert len(items) == 12
    assert any("[... Capped at 10 items" in item.name for item in items)


def test_video_decoder_dynamic_resize(tmp_path: Path):
    """Verifies that VideoDecoder.update_dimensions() recalculates frame bytes and restarts."""
    sample_mp4 = tmp_path / "test.mp4"
    sample_mp4.write_bytes(b"\x00" * 100)

    with patch.object(VideoDecoder, "find_ffmpeg", return_value=None):
        decoder = VideoDecoder(sample_mp4, target_w=64, target_h=48)
        assert decoder.target_w == 64
        assert decoder.target_h == 48
        assert decoder.frame_bytes == 64 * 48 * 3

        with patch.object(decoder, "start") as mock_start:
            decoder.update_dimensions(128, 96)
            assert decoder.target_w == 128
            assert decoder.target_h == 96
            assert decoder.frame_bytes == 128 * 96 * 3
            mock_start.assert_called_once()


def test_turntable_tone_arm_auto_parking():
    """Verifies that GramophoneTurntable tone-arm auto-parks into the cradle."""
    turntable = GramophoneTurntable(diameter=160)
    assert not turntable.is_parked

    # During active playback, needle tracks inward
    canvas_playing = turntable.render_turntable(progress_frac=0.5)
    assert canvas_playing.size == (160, 160)

    # When set to parked or progress >= 1.0, tone-arm rests in cradle
    turntable.set_parked(True)
    assert turntable.is_parked
    canvas_parked = turntable.render_turntable(progress_frac=1.0)
    assert canvas_parked.size == (160, 160)


def test_terminal_session_context_reset():
    """Verifies that TerminalSessionContext.reset_terminal() runs cleanly."""
    fake_stdout = io.StringIO()
    with patch("sys.stdout", fake_stdout):
        TerminalSessionContext.reset_terminal()
        output = fake_stdout.getvalue()
        # Verify critical reset sequences were emitted
        assert "\x1b[?1049l" in output  # Leave alternate buffer
        assert "\x1b[?25h" in output  # Show cursor
        assert "\x1b[?1000l" in output  # Disable mouse
        assert "\x1b[0m" in output  # SGR reset
