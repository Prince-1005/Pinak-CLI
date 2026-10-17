"""Audio extraction, resampling to 48 kHz stereo, and visualizer tap."""

from __future__ import annotations

import array
import contextlib
import logging
import math
import os
import shutil
import struct
import subprocess
import threading
import time
import wave
from collections import deque
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("pinak.media.audio")


@dataclass
class AudioChunk:
    """Represents a discrete PCM audio block."""

    pts: float
    pcm_bytes: bytes
    sample_rate: int = 48000
    channels: int = 2


class _WavFallbackSource:
    """Reads uncompressed PCM from WAV containers directly without external FFmpeg."""

    def __init__(self, file_path: Path, target_sr: int = 48000) -> None:
        self.file_path = file_path
        self.target_sr = target_sr
        self._wav: wave.Wave_read | None = None
        self._open()

    def _open(self) -> None:
        try:
            self._wav = wave.open(str(self.file_path), "rb")  # noqa: SIM115
        except Exception as e:
            logger.warning(f"Failed to open WAV fallback: {e}")
            self._wav = None

    def seek_time(self, seconds: float) -> None:
        if self._wav:
            frame = int(seconds * self._wav.getframerate())
            frame = max(0, min(self._wav.getnframes(), frame))
            self._wav.setpos(frame)

    def read_chunk(self, n_samples: int) -> bytes | None:
        if not self._wav:
            return None
        try:
            frames = self._wav.readframes(n_samples)
            if not frames:
                return None
            samp_width = self._wav.getsampwidth()
            channels = self._wav.getnchannels()
            if samp_width == 2 and channels == 2:
                return frames
            if samp_width == 2 and channels == 1:
                # Duplicate mono channel to stereo
                out = bytearray(len(frames) * 2)
                for i in range(0, len(frames), 2):
                    out[i * 2 : i * 2 + 2] = frames[i : i + 2]
                    out[i * 2 + 2 : i * 2 + 4] = frames[i : i + 2]
                return bytes(out)
            return frames
        except Exception:
            return None

    def close(self) -> None:
        if self._wav:
            with contextlib.suppress(Exception):
                self._wav.close()
            self._wav = None


class _ProceduralFallbackSource:
    """Synthesizes dynamic harmonic audio PCM derived from audio file seed bytes."""

    def __init__(self, file_path: Path, sample_rate: int = 48000) -> None:
        self.sample_rate = sample_rate
        self.time_sec: float = 0.0
        seed = 42
        try:
            with open(file_path, "rb") as f:
                header = f.read(256)
                if header:
                    seed = sum(header) % 500
        except Exception:
            pass
        self.base_freq = 110.0 + (seed % 220)  # Musical fundamental A2 - A4

    def seek_time(self, seconds: float) -> None:
        self.time_sec = max(0.0, seconds)

    def read_chunk(self, n_samples: int) -> bytes:
        dt = 1.0 / self.sample_rate
        out = bytearray(n_samples * 4)  # 2 channels * 2 bytes
        t = self.time_sec

        for i in range(n_samples):
            # Harmonic richness: fundamental + 2nd + 3rd harmonic + rhythm envelope
            beat = 0.6 + 0.4 * math.sin(2.0 * math.pi * 2.0 * t)  # ~120 BPM pulse
            osc = (
                0.5 * math.sin(2.0 * math.pi * self.base_freq * t)
                + 0.3 * math.sin(2.0 * math.pi * (self.base_freq * 1.5) * t)
                + 0.2 * math.sin(2.0 * math.pi * (self.base_freq * 2.0) * t)
            )
            val = int(osc * beat * 18000.0)
            val = max(-32768, min(32767, val))
            struct.pack_into("<hh", out, i * 4, val, val)
            t += dt

        self.time_sec = t
        return bytes(out)

    def close(self) -> None:
        pass


class AudioDecoder:
    """Decodes audio files via FFmpeg stream pipe or fallback into standardized 48 kHz 16-bit stereo PCM."""

    SAMPLE_RATE = 48000
    CHANNELS = 2
    BYTES_PER_SAMPLE = 2  # 16-bit signed int
    FRAME_SIZE = CHANNELS * BYTES_PER_SAMPLE  # 4 bytes per stereo sample
    CHUNK_SAMPLES = 2048
    CHUNK_BYTES = CHUNK_SAMPLES * FRAME_SIZE  # 8192 bytes
    MAX_PCM_WINDOW_SEC: float = 20.0
    MAX_PCM_SAMPLES: int = int(
        SAMPLE_RATE * MAX_PCM_WINDOW_SEC
    )  # 960,000 samples (~1.92 MB sliding window)

    def __init__(self, file_path: str | Path) -> None:
        self.file_path = Path(file_path).resolve()
        self._proc: subprocess.Popen | None = None
        self._lock = threading.RLock()
        self._visualizer_buffer: deque[float] = deque(maxlen=self.CHUNK_SAMPLES * 4)
        self._pcm_buffer: array.array = array.array("h")
        self._current_pts = 0.0
        self._playback_pts = 0.0
        self._decoded_pts = 0.0
        self._buffer_start_pts = 0.0
        self._is_closed = False
        self._fallback_source: _WavFallbackSource | _ProceduralFallbackSource | None = None
        self._decode_thread: threading.Thread | None = None
        self._generation = 0
        self.eof = False
        self._seed_hash = 42
        try:
            with open(self.file_path, "rb") as f:
                header = f.read(512)
                if header:
                    self._seed_hash = sum(header) % 500
        except Exception:
            pass

    @classmethod
    def find_ffmpeg(cls) -> str | None:
        """Locates system or cached static FFmpeg binary."""
        try:
            from ...ffmpeg_setup import ensure_ffmpeg

            fetched = ensure_ffmpeg()
            if fetched and (os.path.exists(fetched) or shutil.which(fetched)):
                return fetched
        except Exception:
            pass
        return None

    def start(self, start_time_sec: float = 0.0) -> None:
        """Launches the background FFmpeg audio demuxing and resampling process or fallback."""
        self.close()
        ffmpeg_bin = self.find_ffmpeg()
        if not ffmpeg_bin:
            logger.info("ffmpeg not found; activating pure-Python/procedural visualizer fallback")
            self._init_fallback(start_time_sec)
            return

        cmd = [ffmpeg_bin, "-v", "quiet"]
        if start_time_sec > 0:
            cmd.extend(["-ss", f"{start_time_sec:.3f}"])
        cmd.extend(
            [
                "-i",
                str(self.file_path),
                "-vn",
                "-f",
                "s16le",
                "-ac",
                str(self.CHANNELS),
                "-ar",
                str(self.SAMPLE_RATE),
                "pipe:1",
            ]
        )

        try:
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                bufsize=self.CHUNK_BYTES * 8,
            )
            self._current_pts = start_time_sec
            self._playback_pts = start_time_sec
            self._decoded_pts = start_time_sec
            self._buffer_start_pts = start_time_sec
            with self._lock:
                self._pcm_buffer = array.array("h")
                self._visualizer_buffer.clear()
            self._is_closed = False
            self.eof = False
            self._decode_thread = threading.Thread(target=self._background_decode_loop, daemon=True)
            self._decode_thread.start()
        except Exception as e:
            logger.error(f"Failed to spawn audio decoder process: {e}")
            self._init_fallback(start_time_sec)

    def _background_decode_loop(self) -> None:
        """Reads decoded audio stream in the background into indexed buffer synchronized to playback."""
        proc = self._proc
        generation = self._generation
        if proc is None or proc.stdout is None:
            return
        chunk_sz = 8192
        while not self._is_closed and generation == self._generation:
            # Flow control: do not decode more than 3.0s ahead of master playback clock
            with self._lock:
                lead = self._decoded_pts - self._playback_pts
            if lead > 3.0:
                time.sleep(0.02)
                continue

            try:
                data = proc.stdout.read(chunk_sz)
                if not data:
                    break
                n_shorts = len(data) // 2
                if n_shorts >= 2:
                    shorts = struct.unpack(f"<{n_shorts}h", data)
                    mono_shorts = array.array(
                        "h",
                        [(shorts[i] + shorts[i + 1]) // 2 for i in range(0, len(shorts) - 1, 2)],
                    )
                    with self._lock:
                        if generation != self._generation:
                            return
                        self._pcm_buffer.extend(mono_shorts)
                        self._decoded_pts += len(mono_shorts) / self.SAMPLE_RATE
                        excess = len(self._pcm_buffer) - self.MAX_PCM_SAMPLES
                        if excess > 0:
                            del self._pcm_buffer[:excess]
                            self._buffer_start_pts += excess / self.SAMPLE_RATE
                        for s in mono_shorts:
                            self._visualizer_buffer.append(s / 32768.0)
            except Exception:
                break
        if generation == self._generation and not self._is_closed:
            self.eof = True

    def _init_fallback(self, start_time_sec: float) -> None:
        """Initializes pure-Python fallback source when FFmpeg cannot be spawned."""
        with self._lock:
            self._is_closed = False
            self._current_pts = start_time_sec
            self._buffer_start_pts = start_time_sec
            self._pcm_buffer = array.array("h")
            self._visualizer_buffer.clear()
            if self.file_path.suffix.lower() == ".wav":
                self._fallback_source = _WavFallbackSource(self.file_path, self.SAMPLE_RATE)
            else:
                self._fallback_source = _ProceduralFallbackSource(self.file_path, self.SAMPLE_RATE)
            self._fallback_source.seek_time(start_time_sec)

    def read_chunk(self) -> AudioChunk | None:
        """Reads the next 2048-sample audio chunk from the decoder stream or fallback."""
        with self._lock:
            if self._is_closed:
                return None

            raw: bytes | None = None

            # Fallback source if proc produced no data or is inactive
            if self._fallback_source is not None:
                raw = self._fallback_source.read_chunk(self.CHUNK_SAMPLES)
                if raw:
                    self._tap_visualizer(raw)
            elif self._proc is not None:
                # If background decode thread is active, it handles proc.stdout.
                # Avoid reading from proc.stdout directly to prevent pipe race conditions.
                if (
                    self._decode_thread is None or not self._decode_thread.is_alive()
                ) and self._proc.stdout is not None:
                    try:
                        raw = self._proc.stdout.read(self.CHUNK_BYTES)
                    except (OSError, ValueError):
                        raw = None
                    if raw:
                        self._tap_visualizer(raw)

            if not raw:
                # Synthesize chunk from pcm_buffer or linear clock to advance transport
                self._current_pts += self.CHUNK_SAMPLES / self.SAMPLE_RATE
                return AudioChunk(
                    pts=self._current_pts,
                    pcm_bytes=b"\x00" * self.CHUNK_BYTES,
                    sample_rate=self.SAMPLE_RATE,
                    channels=self.CHANNELS,
                )

            sample_count = len(raw) // self.FRAME_SIZE
            duration = sample_count / self.SAMPLE_RATE
            pts = self._current_pts
            self._current_pts += duration

            return AudioChunk(
                pts=pts,
                pcm_bytes=raw,
                sample_rate=self.SAMPLE_RATE,
                channels=self.CHANNELS,
            )

    def _tap_visualizer(self, raw_bytes: bytes) -> None:
        """Feeds recent stereo audio samples into lock-free visualizer deque as mono floats."""
        n_bytes = len(raw_bytes)
        if n_bytes < 4:
            return

        # 16-bit stereo: 4 bytes per frame (2 bytes L, 2 bytes R)
        mono_list = []
        for i in range(0, n_bytes - 3, 4):
            l_val, r_val = struct.unpack_from("<hh", raw_bytes, i)
            mono_int = (l_val + r_val) // 2
            self._pcm_buffer.append(mono_int)
            mono_list.append(mono_int / 32768.0)

        excess = len(self._pcm_buffer) - self.MAX_PCM_SAMPLES
        if excess > 0:
            del self._pcm_buffer[:excess]
            self._buffer_start_pts += excess / self.SAMPLE_RATE

        for m in mono_list:
            self._visualizer_buffer.append(m)

    def get_visualizer_samples(self, count: int = 1024, pts: float | None = None) -> list[float]:
        """Returns the most recent PCM samples normalized to [-1.0, 1.0], synchronized to playback pts."""
        restart = False
        if pts is not None and pts >= 0:
            with self._lock:
                self._playback_pts = pts
                restart = (
                    self._fallback_source is None
                    and self._proc is not None
                    and (
                        pts < self._buffer_start_pts
                        or (self._decoded_pts > 0 and pts > self._decoded_pts + 1.5)
                    )
                )
            if restart:
                self.seek(pts)
        with self._lock:
            # 1. Fallback source (Wav or Procedural) sought directly to presentation timestamp
            if self._fallback_source is not None and pts is not None and pts >= 0:
                try:
                    self._fallback_source.seek_time(pts)
                    raw = self._fallback_source.read_chunk(count)
                    if raw and len(raw) >= 4:
                        floats: list[float] = []
                        for i in range(0, len(raw) - 3, 4):
                            l_val, r_val = struct.unpack_from("<hh", raw, i)
                            floats.append(((l_val + r_val) / 2.0) / 32768.0)
                        if len(floats) < count:
                            floats.extend([0.0] * (count - len(floats)))
                        return floats[:count]
                except Exception:
                    pass

            # 2. If timestamp provided and indexed PCM buffer has decoded samples:
            if pts is not None and pts >= 0:
                offset_sec = pts - self._buffer_start_pts
                if offset_sec >= 0:
                    target_idx = int(offset_sec * self.SAMPLE_RATE)
                    buf_len = len(self._pcm_buffer)
                    if buf_len > 0 and target_idx < buf_len:
                        end = min(buf_len, target_idx + count)
                        slice_shorts = self._pcm_buffer[target_idx:end]
                        if len(slice_shorts) >= 64:
                            floats = [s / 32768.0 for s in slice_shorts]
                            if len(floats) < count:
                                floats.extend([0.0] * (count - len(floats)))
                            return floats[:count]

            # 3. Check ring buffer tap from read_chunk
            if self._visualizer_buffer:
                samples = list(self._visualizer_buffer)
                if len(samples) >= count:
                    return samples[-count:]
                if any(abs(s) > 1e-4 for s in samples):
                    return [0.0] * (count - len(samples)) + samples

            # 4. Dynamic Acoustic Synthesizer fallback tied to pts and file seed
            t_base = pts if pts is not None else self._current_pts
            dt = 1.0 / self.SAMPLE_RATE
            seed_freq = 95.0 + (self._seed_hash % 150)
            result = []
            for i in range(count):
                t = t_base + (i * dt)
                beat = 0.55 + 0.45 * math.sin(2.0 * math.pi * 2.2 * t)
                wave = (
                    0.50 * math.sin(2.0 * math.pi * seed_freq * t)
                    + 0.30 * math.sin(2.0 * math.pi * (seed_freq * 1.5) * t)
                    + 0.20 * math.sin(2.0 * math.pi * (seed_freq * 2.2) * t)
                ) * beat
                result.append(max(-1.0, min(1.0, wave)))
            return result

    def seek(self, target_sec: float) -> None:
        """Restarts decoder stream at target timestamp."""
        with self._lock:
            self._playback_pts = target_sec
            self._decoded_pts = target_sec
            if self._fallback_source is not None:
                self._current_pts = target_sec
                self._fallback_source.seek_time(target_sec)
                return
        if self._fallback_source is None:
            self.start(start_time_sec=target_sec)

    def close(self) -> None:
        """Terminates decoder sub-process or fallback."""
        with self._lock:
            self._is_closed = True
            self._generation += 1
            worker = self._decode_thread
            self._decode_thread = None
            if self._proc is not None:
                proc = self._proc
                try:
                    self._proc.terminate()
                    self._proc.wait(timeout=0.2)
                except subprocess.TimeoutExpired:
                    try:
                        self._proc.kill()
                        self._proc.wait(timeout=1.0)
                    except Exception:
                        pass
                except Exception:
                    with contextlib.suppress(Exception):
                        self._proc.kill()
                finally:
                    self._proc = None
                    if proc.stdout:
                        with contextlib.suppress(OSError, ValueError):
                            proc.stdout.close()
            if self._fallback_source is not None:
                self._fallback_source.close()
                self._fallback_source = None
        if worker is not None and worker is not threading.current_thread():
            worker.join(timeout=1.0)
