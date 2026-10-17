"""Bounded PCM output, per-session gain, and cancellable driver failover."""

from __future__ import annotations

import atexit
import contextlib
import importlib.util
import io
import logging
import math
import os
import subprocess
import sys
import tempfile
import threading
import time
import wave
from pathlib import Path
from typing import Any

import numpy as np

from ...ffmpeg_setup import ensure_ffmpeg
from ...utils import trusted_which

if sys.platform == "win32":
    try:
        import winsound
    except ImportError:
        winsound = None  # type: ignore[assignment]
else:
    winsound = None

logger = logging.getLogger("pinak.media.audio_backend")
_pending_temp_files: set[str] = set()


def _flush_pending_temp_files() -> None:
    for filename in list(_pending_temp_files):
        with contextlib.suppress(OSError):
            Path(filename).unlink(missing_ok=True)
            _pending_temp_files.discard(filename)


atexit.register(_flush_pending_temp_files)


def set_windows_device_volume(vol: float) -> None:
    """Deprecated device-wide API. Playback deliberately uses per-session PCM gain."""
    logger.debug("Device-wide volume is deprecated; apply volume through the playback session")


class AudioPlayerBackend:
    BLOCK_FRAMES = 960  # 20 ms at 48 kHz; keep controls and device latency responsive.

    def __init__(self, file_path: str | Path, driver: str | None = None) -> None:
        self.file_path = Path(file_path).resolve()
        self.volume = 1.0
        self.is_muted = False
        self.is_playing = False
        self.error: str | None = None
        self._eos = False
        self._explicit_mock = driver == "mock"
        self._driver = driver or "mock"
        self._lock = threading.RLock()
        self._start_time = self._elapsed_offset = 0.0
        self._proc: subprocess.Popen[bytes] | None = None
        self._decoder_proc: subprocess.Popen[bytes] | None = None
        self._temp_wav: str | None = None
        self._worker: threading.Thread | None = None
        self._cancel = threading.Event()
        self._generation = 0
        self._last_progress = 0.0
        if driver is None:
            self._select_driver()

    @staticmethod
    def available_drivers() -> list[str]:
        drivers = []
        if importlib.util.find_spec("sounddevice") is not None:
            drivers.append("sounddevice")
        if trusted_which("ffplay"):
            drivers.append("ffplay")
        if os.name == "nt" and winsound is not None:
            drivers.append("winsound")
        for name in ("aplay", "afplay"):
            if trusted_which(name):
                drivers.append(name)
        return drivers

    def _select_driver(self) -> None:
        drivers = self.available_drivers()
        self._driver = drivers[0] if drivers else "mock"

    @property
    def driver_name(self) -> str:
        return self._driver

    def play(self, start_pos_sec: float = 0.0) -> None:
        self.stop()
        with self._lock:
            self._elapsed_offset = max(0.0, start_pos_sec)
            self._start_time = self._last_progress = time.perf_counter()
            self.error = None
            self._eos = False
            self._cancel = threading.Event()
            if self._explicit_mock:
                self.is_playing = True
                return
            self._worker = threading.Thread(
                target=self._play_worker,
                args=(self._generation, self._cancel),
                name="PinakPCMOutput",
                daemon=True,
            )
            self._worker.start()

    def _play_worker(self, generation: int, cancelled: threading.Event) -> None:
        attempted: set[str] = set()
        failures = []
        start = self._elapsed_offset
        for driver in [self._driver, *self.available_drivers()]:
            if driver in attempted or driver == "mock" or cancelled.is_set():
                continue
            attempted.add(driver)
            try:
                self._stream(driver, start, generation, cancelled)
                return
            except Exception as exc:
                failures.append(f"{driver}: {exc}")
                logger.warning("Audio output failed; trying another driver: %s", failures[-1])
                with self._lock:
                    if generation != self._generation:
                        return
                    start = self._elapsed_offset
                    self.is_playing = False
                self._stop_processes()
        if not cancelled.is_set() and generation == self._generation:
            with self._lock:
                self.is_playing = False
                self.error = "; ".join(failures) or "No audio output driver is available"
            logger.error("Playback unavailable: %s", self.error)

    def _stream(
        self, driver: str, start: float, generation: int, cancelled: threading.Event
    ) -> None:
        with contextlib.ExitStack() as resources:
            sample_rate, channels = 48000, 2
            decoder = None
            block_frames = 12000 if driver in ("winsound", "afplay") else self.BLOCK_FRAMES
            if self.file_path.suffix.lower() == ".wav":
                source = resources.enter_context(wave.open(str(self.file_path), "rb"))
                if source.getsampwidth() != 2:
                    raise ValueError("WAV fallback requires 16-bit PCM")
                sample_rate, channels = source.getframerate(), source.getnchannels()
                source.setpos(min(source.getnframes(), int(start * sample_rate)))

                def read_wav() -> bytes:
                    return source.readframes(block_frames)

                read = read_wav
            else:
                ffmpeg = ensure_ffmpeg()
                decoder = subprocess.Popen(
                    [
                        ffmpeg,
                        "-v",
                        "error",
                        "-ss",
                        f"{start:.3f}",
                        "-i",
                        str(self.file_path),
                        "-vn",
                        "-f",
                        "s16le",
                        "-ar",
                        str(sample_rate),
                        "-ac",
                        str(channels),
                        "pipe:1",
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                )
                with self._lock:
                    if generation != self._generation:
                        self._terminate(decoder)
                        return
                    self._decoder_proc = decoder
                assert decoder.stdout is not None
                resources.callback(self._terminate, decoder)
                pipe = decoder.stdout

                def read_pipe() -> bytes:
                    return pipe.read(block_frames * channels * 2)

                read = read_pipe
            # Fail invalid/silent containers before opening a physical device.
            # This also lets FFmpeg prepare the first PCM block in parallel.
            first_block = read()
            if not first_block:
                if decoder is not None and decoder.wait(timeout=2) != 0:
                    raise RuntimeError("Audio decoder exited unsuccessfully")
                if generation == self._generation and not cancelled.is_set():
                    self._eos = True
                    self.is_playing = False
                return
            if cancelled.is_set() or generation != self._generation:
                return
            output: Any = None
            if driver in ("ffplay", "aplay"):
                executable = trusted_which(driver)
                if not executable:
                    raise FileNotFoundError(driver)
                args = (
                    [
                        executable,
                        "-nodisp",
                        "-autoexit",
                        "-probesize",
                        "32",
                        "-analyzeduration",
                        "0",
                        "-f",
                        "s16le",
                        "-ar",
                        str(sample_rate),
                        "-ac",
                        str(channels),
                        "-i",
                        "pipe:0",
                    ]
                    if driver == "ffplay"
                    else [
                        executable,
                        "-q",
                        "-t",
                        "raw",
                        "-f",
                        "S16_LE",
                        "-r",
                        str(sample_rate),
                        "-c",
                        str(channels),
                    ]
                )
                output = subprocess.Popen(
                    args,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    bufsize=0,
                )
                with self._lock:
                    if generation != self._generation:
                        self._terminate(output)
                        return
                    self._proc = output
                resources.callback(self._terminate, output)
            elif driver == "sounddevice":
                import sounddevice as sd  # type: ignore[import-not-found]

                options: dict[str, Any] = {}
                if os.name == "nt":
                    # PortAudio defaults to legacy MME on Windows. Prefer the
                    # shared WASAPI endpoint for the SAME default output device.
                    # Do not change system/default device selection globally.
                    with contextlib.suppress(Exception):
                        current_name = sd.query_devices(kind="output")["name"]
                        for api in sd.query_hostapis():
                            index = api["default_output_device"]
                            if (
                                "WASAPI" in api["name"]
                                and index >= 0
                                and sd.query_devices(index)["name"] == current_name
                            ):
                                options["device"] = index
                                break
                output = resources.enter_context(
                    sd.RawOutputStream(
                        samplerate=sample_rate,
                        channels=channels,
                        dtype="int16",
                        blocksize=self.BLOCK_FRAMES,
                        latency="low",
                        **options,
                    )
                )
            elif driver not in ("winsound", "afplay"):
                raise ValueError(f"Unsupported output driver: {driver}")
            with self._lock:
                if generation != self._generation:
                    return
                self._driver = driver
                self.is_playing = True
                self._start_time = time.perf_counter()
                self._elapsed_offset = start
            submitted = 0
            stream_started = self._start_time
            while not cancelled.is_set():
                data, first_block = (first_block or read()), b""
                if not data:
                    if decoder is not None and decoder.wait(timeout=2) != 0:
                        raise RuntimeError("Audio decoder exited unsuccessfully")
                    if driver in ("ffplay", "aplay") and not cancelled.is_set():
                        output.stdin.close()
                        if output.wait(timeout=3) != 0:
                            raise RuntimeError(f"{driver} failed while draining audio")
                    break
                samples = np.frombuffer(data[: len(data) - len(data) % 2], dtype="<i2")
                with self._lock:
                    gain = 0.0 if self.is_muted else self.volume
                pcm = (
                    np.clip(samples.astype(np.float32) * gain, -32768, 32767)
                    .astype("<i2")
                    .tobytes()
                )
                if driver in ("ffplay", "aplay"):
                    if output.poll() is not None:
                        raise RuntimeError(f"{driver} exited before end of input")
                    output.stdin.write(pcm)
                elif driver == "sounddevice":
                    output.write(pcm)
                else:
                    buffer = io.BytesIO()
                    with wave.open(buffer, "wb") as wav:
                        wav.setnchannels(channels)
                        wav.setsampwidth(2)
                        wav.setframerate(sample_rate)
                        wav.writeframes(pcm)
                    if driver == "winsound":
                        if winsound is None:
                            raise RuntimeError("winsound unavailable")
                        winsound.PlaySound(
                            buffer.getvalue(),
                            winsound.SND_MEMORY | getattr(winsound, "SND_SYNC", 0),
                        )
                    else:
                        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                            tmp.write(buffer.getvalue())
                            filename = tmp.name
                        try:
                            executable = trusted_which("afplay")
                            if not executable:
                                raise FileNotFoundError("afplay")
                            subprocess.run(
                                [executable, filename],
                                timeout=3,
                                check=True,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL,
                            )
                        finally:
                            with contextlib.suppress(OSError):
                                os.unlink(filename)
                submitted += len(pcm) // (channels * 2)
                # Anchor pacing to the whole stream, not the previous block's
                # completion: scheduling/processing delays must not accumulate.
                deadline = stream_started + submitted / sample_rate
                cancelled.wait(max(0.0, deadline - time.perf_counter()))
                with self._lock:
                    if generation != self._generation:
                        return
                    self._last_progress = time.perf_counter()
                    self._elapsed_offset = start + submitted / sample_rate
                    self._start_time = self._last_progress
            if not cancelled.is_set() and generation == self._generation:
                with self._lock:
                    self._eos = True
                    self.is_playing = False

    @staticmethod
    def _terminate(proc: subprocess.Popen[bytes]) -> None:
        with contextlib.suppress(OSError):
            proc.terminate()
        try:
            proc.wait(timeout=0.2)
        except (subprocess.TimeoutExpired, OSError):
            with contextlib.suppress(OSError):
                proc.kill()
                proc.wait(timeout=0.5)
        for stream in (proc.stdin, proc.stdout, proc.stderr):
            if stream:
                with contextlib.suppress(OSError, ValueError):
                    stream.close()

    def _stop_processes(self) -> None:
        with self._lock:
            processes = (self._proc, self._decoder_proc)
            self._proc = self._decoder_proc = None
        for proc in processes:
            if proc is not None:
                self._terminate(proc)

    def stop(self) -> None:
        with self._lock:
            self.is_playing = False
            self._generation += 1
            self._cancel.set()
            worker, self._worker = self._worker, None
        self._stop_processes()
        if worker is not None and worker is not threading.current_thread():
            worker.join(timeout=3.5)
        self._cleanup_temp_wav()
        _flush_pending_temp_files()

    def pause(self) -> None:
        position = self.get_clock()
        self.stop()
        with self._lock:
            self._elapsed_offset = position

    def resume(self) -> None:
        if not self.is_playing:
            self.play(self._elapsed_offset)

    def seek(self, target_sec: float) -> None:
        was_playing = self.is_playing or (
            self._worker is not None and self.error is None and not self._eos
        )
        if was_playing:
            self.play(max(0.0, target_sec))
        else:
            self.stop()
            self._elapsed_offset = max(0.0, target_sec)

    def set_volume(self, vol: float) -> None:
        if not math.isfinite(vol):
            raise ValueError("Volume must be finite")
        with self._lock:
            self.volume = max(0.0, min(1.5, vol))

    def toggle_mute(self) -> bool:
        with self._lock:
            self.is_muted = not self.is_muted
            return self.is_muted

    @property
    def is_eos(self) -> bool:
        return self._eos

    def get_clock(self) -> float:
        with self._lock:
            if not self.is_playing:
                return self._elapsed_offset
            return self._elapsed_offset + min(
                0.1 if not self._explicit_mock else float("inf"),
                time.perf_counter() - self._start_time,
            )

    def _cleanup_temp_wav(self) -> None:
        if self._temp_wav:
            target, self._temp_wav = self._temp_wav, None
            try:
                Path(target).unlink(missing_ok=True)
            except OSError:
                _pending_temp_files.add(target)
