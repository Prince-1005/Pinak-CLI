"""Video demuxing and decoding with hardware acceleration and software fallback."""

from __future__ import annotations

import collections
import contextlib
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("pinak.media.video")


@dataclass
class DecodedVideoFrame:
    """Represents a decoded video frame."""

    pts: float
    width: int
    height: int
    rgb_data: bytes


class VideoDecoder:
    """Decodes video containers into packed RGB24 frames with hardware acceleration."""

    def __init__(
        self,
        file_path: str | Path,
        target_w: int = 160,
        target_h: int = 90,
        target_fps: float = 30.0,
    ) -> None:
        self.file_path = Path(file_path).resolve()
        self.target_w = max(16, target_w)
        self.target_h = max(16, target_h)
        self.target_fps = max(1.0, min(60.0, target_fps))
        self.frame_bytes = self.target_w * self.target_h * 3  # RGB24: 3 bytes per pixel
        self._proc: subprocess.Popen | None = None
        self._lock = threading.RLock()
        self._current_pts = 0.0
        self._hw_accel: str | None = None
        self._is_closed = False
        self._frame_queue: collections.deque[DecodedVideoFrame] = collections.deque(maxlen=16)
        self._worker_thread: threading.Thread | None = None
        self._generation = 0
        self._needs_software_fallback = False
        self.eof = False
        self.error: str | None = None
        self._hw_detection_done = False
        self._software_only = False

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

    def detect_hw_accel(self) -> str | None:
        """Probes FFmpeg for supported GPU hardware video decoding."""
        ffmpeg_bin = self.find_ffmpeg()
        if not ffmpeg_bin:
            return None

        try:
            res = subprocess.run(
                [ffmpeg_bin, "-hwaccels"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=2.0,
            )
            available = set(res.stdout.lower().split())
            if os.name == "nt":
                for cand in ("dxva2", "d3d11va", "cuda"):
                    if cand in available:
                        return cand
            elif sys.platform == "darwin":
                if "videotoolbox" in available:
                    return "videotoolbox"
            else:
                for cand in ("vaapi", "cuda", "vdpau"):
                    if cand in available:
                        return cand
        except Exception:
            pass
        return None

    def update_dimensions(
        self, new_w: int, new_h: int, start_time_sec: float | None = None
    ) -> None:
        """Dynamically updates decoding resolution when terminal canvas changes."""
        new_w = max(16, new_w)
        new_h = max(16, new_h)
        if abs(new_w - self.target_w) > 8 or abs(new_h - self.target_h) > 4:
            with self._lock:
                current_pts = self._current_pts if start_time_sec is None else start_time_sec
                self.target_w = new_w
                self.target_h = new_h
                self.frame_bytes = self.target_w * self.target_h * 3
            self.start(start_time_sec=current_pts)

    def start(self, start_time_sec: float = 0.0, *, software_only: bool = False) -> None:
        """Launches the video decoding sub-process."""
        self.close()
        ffmpeg_bin = self.find_ffmpeg()
        if not ffmpeg_bin:
            logger.warning("ffmpeg not found; video playback unavailable")
            self.error = "FFmpeg is unavailable"
            self.eof = True
            return

        self._software_only = self._software_only or software_only
        if self._software_only:
            self._hw_accel = None
        elif not self._hw_detection_done:
            self._hw_accel = self.detect_hw_accel()
            self._hw_detection_done = True
        self._needs_software_fallback = False
        self.eof = False
        self.error = None
        cmd = [ffmpeg_bin, "-v", "quiet"]

        if self._hw_accel:
            cmd.extend(["-hwaccel", self._hw_accel])

        if start_time_sec > 0:
            cmd.extend(["-ss", f"{start_time_sec:.3f}"])

        cmd.extend(
            [
                "-i",
                str(self.file_path),
                "-an",  # Audio handled separately by AudioDecoder
                "-f",
                "rawvideo",
                "-pix_fmt",
                "rgb24",
                "-vf",
                (
                    f"scale=w={self.target_w}:h={self.target_h}:"
                    f"flags=bicubic:force_original_aspect_ratio=decrease,"
                    f"pad={self.target_w}:{self.target_h}:(ow-iw)/2:(oh-ih)/2:black"
                ),
                "-r",
                f"{self.target_fps:.2f}",
                "pipe:1",
            ]
        )

        try:
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                bufsize=self.frame_bytes * 4,
            )
            self._current_pts = start_time_sec
            self._is_closed = False
            self._frame_queue.clear()
            self._frame_queue = collections.deque(
                maxlen=max(2, min(16, (64 * 1024 * 1024) // self.frame_bytes))
            )
            self._worker_thread = threading.Thread(
                target=self._reader_loop, daemon=True, name="PinakVideoDecodeThread"
            )
            self._worker_thread.start()
        except Exception as e:
            logger.error(f"Failed to spawn video decoder with hwaccel '{self._hw_accel}': {e}")
            # Fallback to software CPU decode
            if self._hw_accel:
                self._hw_accel = None
                self.start(start_time_sec, software_only=True)
            else:
                self.error = str(e)
                self.eof = True

    def _reader_loop(self) -> None:
        """Background frame reader loop to prevent blocking UI tick."""
        proc = self._proc
        generation = self._generation
        frame_bytes, width, height = self.frame_bytes, self.target_w, self.target_h
        produced = False
        while not self._is_closed and generation == self._generation and proc is not None:
            try:
                if proc.stdout is None:
                    break
                raw = proc.stdout.read(frame_bytes)
                if not raw or len(raw) < frame_bytes or self._is_closed:
                    break
                with self._lock:
                    if generation != self._generation:
                        return
                    pts = self._current_pts
                    self._current_pts += 1.0 / self.target_fps
                    frame = DecodedVideoFrame(
                        pts=pts,
                        width=width,
                        height=height,
                        rgb_data=raw,
                    )
                    self._frame_queue.append(frame)
                    produced = True
                while (
                    len(self._frame_queue) >= (self._frame_queue.maxlen or 16) - 1
                    and not self._is_closed
                    and generation == self._generation
                ):
                    time.sleep(0.005)
            except (OSError, ValueError) as exc:
                if generation == self._generation:
                    self.error = str(exc)
                break
        if generation == self._generation and not self._is_closed:
            exit_code = proc.poll() if proc is not None else None
            if self._hw_accel and (not produced or exit_code not in (None, 0) or self.error):
                self._needs_software_fallback = True
            else:
                self.eof = True
                if exit_code not in (None, 0):
                    self.error = f"Video decoder exited with status {exit_code}"

    def read_frame(self) -> DecodedVideoFrame | None:
        """Reads the next decoded RGB24 video frame from the stream."""
        if self._needs_software_fallback:
            self.start(self._current_pts, software_only=True)
        with self._lock:
            if self._frame_queue:
                return self._frame_queue.popleft()

            if self._proc is None or self._proc.stdout is None or self._is_closed:
                return None

            # Fallback direct synchronous read (for unit tests where worker thread is not spawned)
            if self._worker_thread is None:
                try:
                    raw = self._proc.stdout.read(self.frame_bytes)
                except (OSError, ValueError):
                    return None

                if not raw or len(raw) < self.frame_bytes:
                    return None

                pts = self._current_pts
                self._current_pts += 1.0 / self.target_fps

                return DecodedVideoFrame(
                    pts=pts,
                    width=self.target_w,
                    height=self.target_h,
                    rgb_data=raw,
                )

            return None

    def seek(self, target_sec: float) -> None:
        """Seeks to the target timestamp."""
        self.start(start_time_sec=target_sec)

    def close(self) -> None:
        """Terminates decoder sub-process."""
        with self._lock:
            self._is_closed = True
            self._generation += 1
            self._frame_queue.clear()
            worker = self._worker_thread
            self._worker_thread = None
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
        if worker is not None and worker is not threading.current_thread():
            worker.join(timeout=1.0)
