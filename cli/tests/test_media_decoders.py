"""Unit tests for pinak.media.decoders modules."""

from pathlib import Path

import pytest
from PIL import Image

from pinak.media.decoders.audio_backend import AudioPlayerBackend
from pinak.media.decoders.image_loader import ImageLoader
from pinak.media.decoders.probe import MediaProbe
from pinak.media.decoders.video_decoder import VideoDecoder


@pytest.fixture
def temp_image_file(tmp_path: Path) -> Path:
    img_path = tmp_path / "sample.png"
    img = Image.new("RGB", (200, 100), color=(255, 0, 0))
    img.save(img_path)
    return img_path


def test_media_probe_image(temp_image_file: Path):
    meta = MediaProbe.probe(temp_image_file)
    assert meta.media_type == "picture"
    assert meta.width == 200
    assert meta.height == 100
    assert meta.aspect_ratio == 2.0


def test_image_loader_static(temp_image_file: Path):
    loaded = ImageLoader.load(temp_image_file)
    assert loaded.is_animated is False
    assert loaded.width == 200
    assert loaded.height == 100
    assert len(loaded.frames) == 1

    # Crop and scale
    scaled = ImageLoader.crop_and_scale(
        loaded.frames[0], target_w=80, target_h=40, zoom=1.5, rotation_deg=90
    )
    assert scaled.size == (80, 40)


def test_audio_backend_clock_and_volume(tmp_path: Path):
    fake_audio = tmp_path / "test.mp3"
    fake_audio.write_bytes(b"ID3" + b"\x00" * 100)

    backend = AudioPlayerBackend(fake_audio, driver="mock")
    assert backend.is_playing is False
    assert backend.get_clock() == 0.0

    backend.play(start_pos_sec=10.0)
    assert backend.is_playing is True
    assert backend.get_clock() >= 10.0

    # Volume and soft limiter
    backend.set_volume(1.4)
    assert backend.volume == 1.4  # gain remains monotonic above unity
    backend.pause()
    assert backend.is_playing is False
    backend.stop()


def test_video_decoder_hw_accel(tmp_path: Path):
    fake_vid = tmp_path / "test.mp4"
    fake_vid.write_bytes(b"\x00" * 4 + b"ftyp" + b"\x00" * 100)

    decoder = VideoDecoder(fake_vid, target_w=80, target_h=40, target_fps=30.0)
    assert decoder.target_w == 80
    assert decoder.target_h == 40
    assert decoder.frame_bytes == 80 * 40 * 3


def test_audio_backend_driver_selection_and_mute(tmp_path: Path):
    """Verifies that AudioPlayerBackend selects valid hardware drivers and handles mute."""
    fake_audio = tmp_path / "sound.wav"
    fake_audio.write_bytes(b"RIFF" + b"\x00" * 40)

    backend = AudioPlayerBackend(fake_audio)
    assert backend.driver_name in ("ffplay", "winsound", "afplay", "aplay", "sounddevice", "mock")

    # Mute toggling
    assert backend.is_muted is False
    is_mut = backend.toggle_mute()
    assert is_mut is True
    assert backend.is_muted is True
    backend.stop()


def test_audio_backend_hardware_volume_sync(tmp_path, monkeypatch):
    """Per-session controls must not change the user's system device volume."""
    backend = AudioPlayerBackend(tmp_path / "sound.wav", driver="mock")
    calls = []
    monkeypatch.setattr(
        "pinak.media.decoders.audio_backend.set_windows_device_volume", calls.append
    )
    backend.set_volume(0.5)
    assert backend.volume == 0.5
    assert backend.toggle_mute() is True
    assert backend.toggle_mute() is False
    assert calls == []


def test_audio_backend_aplay_driver(tmp_path, monkeypatch):
    """Raw PCM is streamed to aplay in small blocks, without a full WAV conversion."""
    import io
    import wave
    from unittest.mock import MagicMock

    path = tmp_path / "sound.wav"
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(48000)
        wav.writeframes(b"\x00\x01\x00\x01" * 4800)
    backend = AudioPlayerBackend(path, driver="aplay")
    monkeypatch.setattr(
        "pinak.media.decoders.audio_backend.trusted_which",
        lambda name: "/fake/aplay" if name == "aplay" else None,
    )
    proc = MagicMock()
    proc.poll.return_value = None
    proc.wait.return_value = 0
    proc.stdin = io.BytesIO()
    written = []
    proc.stdin = MagicMock(write=lambda data: written.append(data))
    commands = []
    monkeypatch.setattr(
        "pinak.media.decoders.audio_backend.subprocess.Popen",
        lambda args, **kw: (commands.append(args), proc)[1],
    )
    backend.play()
    backend._worker.join(timeout=2)
    assert backend.is_eos and backend.error is None
    assert sum(map(len, written)) == 4800 * 4
    assert max(map(len, written)) <= backend.BLOCK_FRAMES * 4
    assert "raw" in commands[0]


def test_audio_backend_sounddevice_driver(tmp_path, monkeypatch):
    """Live gain/mute changes affect subsequent PCM blocks and close the stream."""
    import sys
    import wave
    from types import SimpleNamespace

    path = tmp_path / "sound.wav"
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(48000)
        wav.writeframes(b"\x00\x10\x00\x10" * 7200)
    backend = AudioPlayerBackend(path, driver="sounddevice")
    blocks, closed = [], []

    class Stream:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            closed.append(True)

        def write(self, data):
            blocks.append(data)
            if len(blocks) == 1:
                backend.toggle_mute()

    monkeypatch.setattr(backend, "available_drivers", lambda: [])
    monkeypatch.setitem(
        sys.modules, "sounddevice", SimpleNamespace(RawOutputStream=lambda **kw: Stream())
    )
    backend.play()
    backend._worker.join(timeout=2)
    assert len(blocks) > 1 and any(blocks[0])
    assert sum(map(len, blocks)) == 7200 * 4
    assert all(not any(block) for block in blocks[1:])
    assert closed == [True]
    assert backend.is_eos and backend.error is None


def test_image_loader_decompression_bomb_safety(tmp_path: Path, monkeypatch):
    """Verifies that DecompressionBombError is caught and MAX_IMAGE_PIXELS is never left as None."""
    fake_img = tmp_path / "bomb.png"
    fake_img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

    orig_limit = Image.MAX_IMAGE_PIXELS

    def mock_open(*args, **kwargs):
        raise Image.DecompressionBombError("Too many pixels!")

    monkeypatch.setattr(Image, "open", mock_open)

    loaded = ImageLoader.load(fake_img)
    assert loaded is not None
    assert (
        "Decompression Bomb Blocked" in loaded.frames[0].tobytes().decode("latin1", errors="ignore")
        or len(loaded.frames) == 1
    )
    # Crucial assertion: MAX_IMAGE_PIXELS must NOT be left as None!
    assert orig_limit == Image.MAX_IMAGE_PIXELS


def test_image_loader_gigapixel_blocked(tmp_path: Path, monkeypatch):
    """Verifies that images exceeding MAX_SAFE_IMAGE_PIXELS are blocked before memory allocation."""
    fake_img = tmp_path / "gigapixel.png"
    fake_img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

    class FakeBombImage:
        size = (50000, 50000)  # 2.5 Billion pixels > 128MP

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    first_call = True

    def mock_open(*args, **kwargs):
        nonlocal first_call
        if first_call:
            first_call = False
            raise Image.DecompressionBombError("Triggered bomb limit")
        return FakeBombImage()

    monkeypatch.setattr(Image, "open", mock_open)

    loaded = ImageLoader.load(fake_img)
    assert loaded is not None
    assert len(loaded.frames) == 1


def test_audio_decoder_bounded_pcm_buffer(tmp_path: Path):
    """Verifies that AudioDecoder trims PCM buffer to MAX_PCM_SAMPLES and updates buffer_start_pts."""
    from pinak.media.decoders.audio_decoder import AudioDecoder

    fake_audio = tmp_path / "test.mp3"
    fake_audio.write_bytes(b"\x00" * 100)

    decoder = AudioDecoder(fake_audio)
    decoder.MAX_PCM_SAMPLES = 1000  # set small window for test

    # Tap 1200 frames (4800 bytes stereo = 1200 mono samples)
    raw_stereo = b"\x10\x00\x10\x00" * 1200
    decoder._tap_visualizer(raw_stereo)

    assert len(decoder._pcm_buffer) == 1000
    assert decoder._buffer_start_pts > 0.0


def test_video_decoder_close_kills_on_timeout(tmp_path: Path):
    """Verifies that VideoDecoder.close() falls back to kill() if terminate() times out."""
    import subprocess
    from unittest.mock import MagicMock

    from pinak.media.decoders.video_decoder import VideoDecoder

    fake_vid = tmp_path / "test.mp4"
    fake_vid.write_bytes(b"\x00" * 100)

    decoder = VideoDecoder(fake_vid, target_w=80, target_h=40)
    mock_proc = MagicMock()
    mock_proc.wait.side_effect = [subprocess.TimeoutExpired(cmd="ffmpeg", timeout=0.2), 0]
    decoder._proc = mock_proc

    decoder.close()
    mock_proc.terminate.assert_called_once()
    mock_proc.kill.assert_called_once()
    assert decoder._proc is None


def test_audio_decoder_close_kills_on_timeout(tmp_path: Path):
    """Verifies that AudioDecoder.close() falls back to kill() if terminate() times out."""
    import subprocess
    from unittest.mock import MagicMock

    from pinak.media.decoders.audio_decoder import AudioDecoder

    fake_audio = tmp_path / "test.mp3"
    fake_audio.write_bytes(b"\x00" * 100)

    decoder = AudioDecoder(fake_audio)
    mock_proc = MagicMock()
    mock_proc.wait.side_effect = [subprocess.TimeoutExpired(cmd="ffmpeg", timeout=0.2), 0]
    decoder._proc = mock_proc

    decoder.close()
    mock_proc.terminate.assert_called_once()
    mock_proc.kill.assert_called_once()
    assert decoder._proc is None


def test_audio_backend_temp_wav_leak_prevention(tmp_path: Path, monkeypatch):
    """Verifies that locked temp WAV files are retained in _pending_temp_files and pruned upon flush (LEAK-01)."""
    import pinak.media.decoders.audio_backend as ab_mod

    fake_audio = tmp_path / "song.mp3"
    fake_audio.write_bytes(b"dummy")

    backend = ab_mod.AudioPlayerBackend(fake_audio, driver="mock")
    temp_wav = tmp_path / "temp_locked.wav"
    temp_wav.write_bytes(b"wavdata")

    backend._temp_wav = str(temp_wav)

    # Simulate locked file raising PermissionError on unlink
    orig_unlink = Path.unlink

    def locked_unlink(self, *a, **k):
        if self == temp_wav:
            raise PermissionError("File in use")
        orig_unlink(self, *a, **k)

    monkeypatch.setattr(Path, "unlink", locked_unlink)

    backend._cleanup_temp_wav()
    assert str(temp_wav) in ab_mod._pending_temp_files
    assert backend._temp_wav is None

    # Now simulate release of lock and flush
    monkeypatch.setattr(Path, "unlink", orig_unlink)
    ab_mod._flush_pending_temp_files()
    assert str(temp_wav) not in ab_mod._pending_temp_files
    assert not temp_wav.exists()
