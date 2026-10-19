"""End-to-end multimedia session orchestrator connecting decoders, renderers, transport, and TUI."""

from __future__ import annotations

import contextlib
import logging
import queue
import re
import shutil
import threading
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from PIL import Image

from ...text_safety import safe_text
from ..core.event_loop import PrecisionEventLoop
from ..core.input_parser import KeyEvent, MouseEvent
from ..core.lifecycle import TerminalSessionContext
from ..core.terminal_caps import TerminalCapabilities, TerminalProber
from ..decoders.audio_backend import AudioPlayerBackend
from ..decoders.audio_decoder import AudioDecoder
from ..decoders.probe import MediaMetadata, MediaProbe
from ..decoders.video_decoder import DecodedVideoFrame, VideoDecoder
from ..diagnostics.capacity_scorer import CapacityScorer
from ..diagnostics.preflight_modal import PreflightConsentModal
from ..diagnostics.telemetry_probe import DeviceDiagnosticsProbe
from ..ipc.server import MediaIPCServer
from ..lifecycle.close_affordances import CloseAffordanceManager
from ..lifecycle.session_coordinator import MediaSessionCoordinator
from ..osc.controller import OnScreenController, OSCState
from ..picture.viewer import PictureViewer
from ..renderers.ascii_retro import ASCIIRenderer
from ..renderers.base import BaseRenderer
from ..renderers.halfblock import HalfBlockRenderer
from ..renderers.pixel_kitty import KittyRenderer
from ..renderers.quadrant import QuadrantRenderer
from ..subtitles.loader import SubtitleLoader
from ..subtitles.model import SubtitleTrack
from ..subtitles.renderer import SubtitleRenderer
from ..sync.clock import MasterAudioClock
from ..sync.fallback_manager import FallbackManager
from ..sync.scheduler import SyncAction, VideoFrameScheduler
from ..sync.throttler import BandwidthThrottler
from ..visualizer.fft_engine import AudioFFTEngine
from ..visualizer.spectrum_bars import SpectrumBarsRenderer, _fit_to_width
from ..visualizer.turntable import GramophoneTurntable
from ..window.native_window import NativeVideoWindow
from .playlist import PlaylistManager
from .quality import QualityProfileManager
from .transport import TransportController

logger = logging.getLogger("pinak.media.coordinator")


class MediaSession:
    """Manages an active multimedia playback session inside the alternate terminal buffer."""

    def __init__(
        self,
        playlist: Sequence[str | Path] | list[Any],
        initial_index: int = 0,
        target_fps: float = 60.0,
        enable_consent_prompt: bool = True,
        enable_native_window: bool = False,
        ipc_port: int = MediaIPCServer.DEFAULT_PORT,
    ) -> None:
        self.playlist_manager = PlaylistManager(playlist, initial_index=initial_index)
        self.target_fps = target_fps
        self.enable_consent_prompt = enable_consent_prompt
        self.enable_native_window = enable_native_window

        self.caps: TerminalCapabilities = TerminalProber.probe(skip_active_interrogation=True)
        self.renderer: BaseRenderer = FallbackManager.get_best_renderer(self.caps)

        self.quality_manager = QualityProfileManager(default_profile="native")
        self.throttler = BandwidthThrottler(target_fps=self.target_fps)
        self.close_manager = CloseAffordanceManager(on_close=self.stop)

        self._last_term_size: tuple[int, int] | None = None
        self.is_running = False
        self._loop: PrecisionEventLoop | None = None
        self._current_meta: MediaMetadata | None = None

        # Playback components
        self.transport = TransportController()
        self.audio_backend: AudioPlayerBackend | None = None
        self.audio_decoder: AudioDecoder | None = None
        self.video_decoder: VideoDecoder | None = None
        self.picture_viewer: PictureViewer | None = None
        self.turntable: GramophoneTurntable | None = None
        self.fft_engine = AudioFFTEngine(sample_rate=48000, window_size=1024)
        self.fft_band_options = [16, 32, 64, 128]
        self.fft_band_idx = 1
        self.vis_theme_idx = 0
        self.master_clock = MasterAudioClock()
        self._last_video_img: Image.Image | None = None
        self._buffered_video_frame: DecodedVideoFrame | None = None
        self._last_frame_pts: float | None = None
        self._frozen_visualizer_bands: list[float] | None = None
        self._frozen_visualizer_peaks: list[float] | None = None
        self._frozen_visualizer_pcm: list[float] | None = None
        self._frozen_turntable_img: Image.Image | None = None
        self.exit_action: str = "close_media"

        # mpv-grade extensions: OSC, Subtitles, IPC, and Native Window
        self.osc = OnScreenController()
        self.subtitle_tracks: list[SubtitleTrack] = []
        self._subtitles_loading = False
        self._subtitle_enable_pending = False
        self.active_sub_idx: int = -1
        self.native_window: NativeVideoWindow | None = None
        self._pending_window_keys: list[str] = []
        self._render_index = 0
        self._pending_render_dt = 0.0
        self._holding_future_frame = False
        self._playback_profile = "native"
        self._last_video_resync = float("-inf")
        self._subtitle_loader = SubtitleLoader()
        self._cached_audio_thumb: Image.Image | None = None
        self.ipc_server = MediaIPCServer(self, port=ipc_port)
        self._ipc_requests: queue.Queue[tuple[int, str, threading.Event, dict[str, Any]]] = (
            queue.Queue(maxsize=64)
        )
        self._control_generation = 0

    def start(self) -> str:
        """Launches the media session and returns the exit action."""
        cur_file = self.playlist_manager.get_current()
        if not cur_file:
            logger.error("No valid media files in playlist")
            return "close_media"

        # 1. Probe current media
        try:
            self._current_meta = MediaProbe.probe(cur_file)
        except Exception as e:
            logger.error(f"Failed to probe media file: {e}")
            return "close_media"

        # 2. Hardware capacity assessment & user consent check
        if self.enable_consent_prompt:
            consent = PreflightConsentModal.prompt_user(self._current_meta)
            if not consent:
                logger.info("Playback cancelled by user during pre-flight assessment")
                return "close_media"

        profile = CapacityScorer.evaluate(
            DeviceDiagnosticsProbe.inspect(),
            media_type=self._current_meta.media_type,
            is_4k=self._current_meta.width >= 3840,
        )
        if profile.tier == "constrained":
            self._playback_profile = "auto"
            self.target_fps = min(self.target_fps, profile.suggested_fps)
        self.throttler = BandwidthThrottler(target_fps=self.target_fps)

        try:
            MediaSessionCoordinator.acquire_session(self)
            try:
                self.ipc_server.start()
            except Exception as exc:
                logger.warning("Media control unavailable: %s", exc)
            with TerminalSessionContext(enable_mouse=True):
                self._init_media_components()
                if self.enable_native_window:
                    self.toggle_native_window()
                self._loop = PrecisionEventLoop(
                    target_fps=self.target_fps, enable_sync_updates=self.caps.has_sync_updates
                )
                self.is_running = True
                self._loop.run(self._on_tick)
        finally:
            self.is_running = False
            self._teardown_media_components()
            self._subtitle_loader.close()
            with contextlib.suppress(Exception):
                self.ipc_server.stop()
            MediaSessionCoordinator.release_session()

        return self.exit_action

    def stop(self, action: str = "close_media") -> None:
        """Signals the session to terminate with specified exit action."""
        self.exit_action = action
        self.is_running = False
        self._cancel_pending_controls()
        if self._loop is not None:
            self._loop.stop()

    def submit_ipc_command(self, raw: str) -> dict[str, Any]:
        """Socket workers enqueue controls; only the session thread changes playback."""
        if not self.is_running:
            return {"error": "session is not ready", "data": None}
        ready = threading.Event()
        result: dict[str, Any] = {}
        try:
            self._ipc_requests.put_nowait((self._control_generation, raw, ready, result))
        except queue.Full:
            return {"error": "control queue is full", "data": None}
        if not ready.wait(2.0):
            result["cancelled"] = True
            return {"error": "control request timed out", "data": None}
        return result

    def _cancel_pending_controls(self) -> None:
        self._control_generation += 1
        while True:
            try:
                _, _, ready, result = self._ipc_requests.get_nowait()
            except queue.Empty:
                break
            result.update(error="media session changed", data=None)
            ready.set()

    def set_playing(self, playing: bool) -> None:
        self.transport.is_playing = playing
        if playing:
            self.master_clock.resume()
        else:
            self.master_clock.pause()

    def set_muted(self, muted: bool) -> None:
        self.transport.is_muted = muted
        if self.audio_backend and self.audio_backend.is_muted != muted:
            self.audio_backend.toggle_mute()

    def set_volume(self, volume: float) -> None:
        self.transport.volume = max(0.0, min(1.5, volume))
        if self.audio_backend:
            self.audio_backend.set_volume(self.transport.volume)

    def seek_to(self, pts: float) -> float:
        pts = self.transport.seek_to(pts)
        self.master_clock.set_time(pts)
        if self.audio_decoder:
            self.audio_decoder.seek(pts)
        if self.video_decoder:
            self.video_decoder.seek(pts)
        self._buffered_video_frame = None
        self._holding_future_frame = False
        self._last_frame_pts = pts
        self._last_video_img = None
        self._frozen_visualizer_bands = None
        self._frozen_visualizer_peaks = None
        self._frozen_visualizer_pcm = None
        self._frozen_turntable_img = None
        return pts

    def _init_media_components(self) -> None:
        """Initializes decoders based on media type."""
        cur_file = self.playlist_manager.get_current()
        if not cur_file or not self._current_meta:
            return

        self.transport = TransportController(duration_sec=self._current_meta.duration_seconds)

        if self._current_meta.media_type == "picture":
            # Direct picture viewer with 2x2 high-density quadrant renderer for TrueColor
            pic_renderer = self.renderer
            if pic_renderer.mode_name == "halfblock" and self.caps.has_truecolor:
                pic_renderer = QuadrantRenderer()
            self.picture_viewer = PictureViewer(
                self.playlist_manager.original_playlist,
                initial_index=self.playlist_manager.current_idx,
                renderer=pic_renderer,
            )
        elif self._current_meta.media_type == "audio":
            self.audio_backend = AudioPlayerBackend(cur_file)
            self.audio_decoder = AudioDecoder(cur_file)
            self.audio_decoder.start()
            self.audio_backend.play()
            self.master_clock = MasterAudioClock(self.audio_backend)
            self.turntable = GramophoneTurntable(
                diameter=180,
                artwork_bytes=self._current_meta.album_art_bytes,
            )
            self._frozen_visualizer_bands = None
            self._frozen_visualizer_peaks = None
            self._frozen_visualizer_pcm = None
            self._frozen_turntable_img = None
        else:  # Video
            self.quality_manager = QualityProfileManager(default_profile=self._playback_profile)
            cols, rows = shutil.get_terminal_size(fallback=(80, 24))
            canvas_rows = max(4, rows - 6)
            nat_w = self._current_meta.width if self._current_meta else 0
            nat_h = self._current_meta.height if self._current_meta else 0
            target_w, target_h = self._video_decode_dimensions(cols, canvas_rows, nat_w, nat_h)
            fps = 30.0
            if self._current_meta and self._current_meta.fps and self._current_meta.fps > 0:
                fps = min(60.0, max(1.0, float(self._current_meta.fps)))

            # Optional subtitle I/O must not delay the first frame/audio block.
            self.subtitle_tracks = []
            self.active_sub_idx = -1
            self._subtitles_loading = True
            self._subtitle_enable_pending = False
            self._subtitle_loader.load(cur_file)

            # 2. Synchronously start audio backend and master clock at 0.0
            self.audio_backend = AudioPlayerBackend(cur_file)
            self.audio_backend.play(0.0)
            self.master_clock = MasterAudioClock(self.audio_backend)

            # 3. Start video decoder and pre-buffer initial frame anchored to master clock
            self.video_decoder = VideoDecoder(
                cur_file, target_w=target_w, target_h=target_h, target_fps=fps
            )
            self.video_decoder.start(start_time_sec=0.0)
            self._buffered_video_frame = self.video_decoder.read_frame()
            self._last_frame_pts = 0.0

    def _teardown_media_components(self) -> None:
        """Releases hardware resources."""
        self._cancel_pending_controls()
        self._subtitle_loader.clear()
        for name, method in (
            ("native_window", "close"),
            ("audio_backend", "stop"),
            ("audio_decoder", "close"),
            ("video_decoder", "close"),
        ):
            component = getattr(self, name, None)
            try:
                if component:
                    getattr(component, method)()
            except Exception as exc:
                logger.warning("Failed to release %s: %s", name, exc)
            finally:
                setattr(self, name, None)
        self.picture_viewer = None
        self.turntable = None
        self.subtitle_tracks = []
        self.active_sub_idx = -1
        self._subtitles_loading = False
        self._subtitle_enable_pending = False
        self._last_video_img = None
        self._cached_audio_thumb = None
        self._buffered_video_frame = None
        self._holding_future_frame = False
        self._last_frame_pts = None
        self._last_video_resync = float("-inf")
        self._frozen_visualizer_bands = None
        self._frozen_visualizer_peaks = None
        self._frozen_visualizer_pcm = None
        self._frozen_turntable_img = None

    @property
    def current_vis_theme(self) -> str:
        return SpectrumBarsRenderer.THEMES[self.vis_theme_idx % len(SpectrumBarsRenderer.THEMES)]

    def cycle_visualizer_theme(self) -> str:
        """Cycles through visualizer themes (FOUNTAIN -> MATRIX -> WAVE)."""
        self.vis_theme_idx = (self.vis_theme_idx + 1) % len(SpectrumBarsRenderer.THEMES)
        return self.current_vis_theme

    def cycle_subtitles(self) -> str:
        """Cycles through available subtitle tracks (-1 for Off, then 0, 1, ...)."""
        if not self.subtitle_tracks:
            if self._subtitles_loading:
                self._subtitle_enable_pending = not self._subtitle_enable_pending
                return "Loading subtitles" if self._subtitle_enable_pending else "Off"
            return "No Subtitles"
        total = len(self.subtitle_tracks)
        self.active_sub_idx = (self.active_sub_idx + 2) % (total + 1) - 1
        if self.active_sub_idx == -1:
            return "Off"
        return self.subtitle_tracks[self.active_sub_idx].label

    def _poll_subtitles(self) -> None:
        """Publish background tracks without enabling subtitles until requested."""
        tracks = self._subtitle_loader.poll()
        if tracks is not None:
            self.subtitle_tracks = tracks
            self.active_sub_idx = 0 if tracks and self._subtitle_enable_pending else -1
            self._subtitles_loading = False
            self._subtitle_enable_pending = False

    def toggle_native_window(self) -> bool:
        """Opens or closes the OS-native GPU video output window."""
        cur_file = self.playlist_manager.get_current()
        name = cur_file.name if cur_file else "Media"
        if self.native_window and self.native_window.is_open:
            self.native_window.close()
            self.native_window = None
            self.enable_native_window = False
            return False
        else:
            initial_size = None
            if self._current_meta and self._current_meta.width and self._current_meta.height:
                initial_size = (self._current_meta.width, self._current_meta.height)
            elif self.picture_viewer and self.picture_viewer._current_loaded:
                initial_size = (
                    self.picture_viewer._current_loaded.width,
                    self.picture_viewer._current_loaded.height,
                )
            elif self.turntable and self.audio_decoder:
                if self._current_meta and self._current_meta.album_art_bytes:
                    try:
                        import io

                        t_img = Image.open(io.BytesIO(self._current_meta.album_art_bytes))
                        initial_size = (t_img.width, t_img.height)
                    except Exception:
                        initial_size = (600, 600)
                else:
                    initial_size = (600, 600)

            is_pic = self.picture_viewer is not None or (
                self._current_meta and self._current_meta.media_type == "picture"
            )
            is_audio = self.audio_decoder is not None and self.video_decoder is None
            if is_audio:
                tag = "Audio Thumbnail"
            elif is_pic:
                tag = "Photo"
            else:
                tag = "Video"
            dim_str = f" ({initial_size[0]}x{initial_size[1]})" if initial_size else ""
            self.native_window = NativeVideoWindow(
                title=f"Pinak {tag} - {name}{dim_str}",
                initial_scale=0.5,
            )
            if initial_size:
                try:
                    opened = self.native_window.open(initial_size=initial_size)
                except TypeError:
                    opened = self.native_window.open()
            else:
                opened = self.native_window.open()
            if not opened:
                self.native_window = None
            self.enable_native_window = opened
            return opened

    def _handle_action_key(self, k: str, cols: int, rows: int) -> None:
        """Dispatches an action key from either terminal input or native window."""
        self.osc.trigger_interaction()
        if self.picture_viewer and k not in ("x", "esc", "w", "f"):
            self.picture_viewer.handle_input(KeyEvent(k))
            self.playlist_manager.current_idx = self.picture_viewer.current_index
            return
        if k in ("x", "esc"):
            self.stop()
        elif k == "space":
            self.set_playing(not self.transport.is_playing)
            if self.transport.is_playing and self.video_decoder:
                resumed_pts = self.master_clock.get_time()
                self.video_decoder.seek(resumed_pts)
                self._buffered_video_frame = None
                self._holding_future_frame = False
                self._last_frame_pts = resumed_pts
        elif k == "q":
            self._cycle_quality(cols, rows)
        elif k == "f":
            if self.native_window and self.native_window.is_open:
                self.native_window.toggle_fullscreen()
        elif k == "c":
            self.cycle_subtitles()
        elif k == "v":
            if not self.video_decoder:
                self.cycle_visualizer_theme()
        elif k == "w":
            self.toggle_native_window()
        elif k == "left":
            self.seek_to(self.transport.current_pts - 10.0)
        elif k == "right":
            self.seek_to(self.transport.current_pts + 10.0)
        elif k == "up":
            self.set_volume(self.transport.volume + 0.05)
        elif k == "down":
            self.set_volume(self.transport.volume - 0.05)
        elif k in ("ctrl+m", "ctrl-m", "ctrl_m"):
            self.set_muted(not self.transport.is_muted)
        elif k == "m":
            self.cycle_render_mode()
        elif k == "r":
            self.playlist_manager.cycle_repeat_mode()
        elif k == "s":
            if not self.picture_viewer:
                self.playlist_manager.toggle_shuffle()
        elif k == "n":
            if self.picture_viewer:
                self.picture_viewer.next_image()
                self.playlist_manager.current_idx = self.picture_viewer.current_index
            else:
                self._advance_track(
                    delta=1,
                    wrap=bool(self._current_meta and self._current_meta.media_type == "audio"),
                    manual=True,
                )
        elif k == "p":
            if self.picture_viewer:
                self.picture_viewer.prev_image()
                self.playlist_manager.current_idx = self.picture_viewer.current_index
            else:
                self._advance_track(
                    delta=-1,
                    wrap=bool(self._current_meta and self._current_meta.media_type == "audio"),
                    manual=True,
                )

    def _on_tick(self, dt: float, events: list[KeyEvent | MouseEvent]) -> str | None:
        """Main frame tick callback."""
        self._poll_subtitles()
        for _ in range(16):
            try:
                generation, raw, ready, result = self._ipc_requests.get_nowait()
            except queue.Empty:
                break
            if generation != self._control_generation:
                result.update(error="media session changed", data=None)
            elif not result.get("cancelled"):
                result.update(self.ipc_server.dispatch_command(raw))
            ready.set()
        cols, rows = shutil.get_terminal_size(fallback=(80, 24))
        self.close_manager.update_layout(cols, rows)

        # Check native window inputs if open
        if self.native_window and self.native_window.is_open:
            win_keys = self.native_window.poll_events()
            if win_keys:
                self._pending_window_keys.extend(win_keys)

        # Process any pending native window keys
        while self._pending_window_keys:
            wk = self._pending_window_keys.pop(0)
            self._handle_action_key(wk, cols, rows)
            if not self.is_running:
                return None

        # Process terminal inputs
        for ev in events:
            if isinstance(ev, KeyEvent):
                k = ev.key.lower()
                if (ev.key == "c" and ev.ctrl) or k in ("x", "esc"):
                    self.stop()
                    return None
                if (k == "m" and ev.ctrl) or k in ("ctrl+m", "ctrl-m", "ctrl_m"):
                    self._handle_action_key("ctrl+m", cols, rows)
                else:
                    self._handle_action_key(ev.key if self.picture_viewer else k, cols, rows)
                if not self.is_running:
                    return None

            elif isinstance(ev, MouseEvent):
                self.osc.trigger_interaction()
                if ev.is_pressed:
                    if self.close_manager.handle_click(ev.col, ev.row):
                        return None
                    if ev.row >= rows - 1 and 18 <= ev.col <= 38:
                        self._cycle_quality(cols, rows)
                if self.picture_viewer:
                    self.picture_viewer.handle_input(ev)

        self._render_index += 1
        self._pending_render_dt += dt
        if self.throttler.should_skip_frame(self._render_index):
            return None
        dt = self._pending_render_dt
        self._pending_render_dt = 0.0
        render_started = time.perf_counter()
        try:
            # Render frame
            if self.picture_viewer:
                self.picture_viewer.is_native_window_open = bool(
                    self.native_window and self.native_window.is_open
                )
                tui_output = self.picture_viewer.render_tui(cols, rows, time.perf_counter())
                if self.native_window and self.native_window.is_open:
                    img = self.picture_viewer.get_current_display_image()
                    if img:
                        win_keys = self.native_window.show_frame(img)
                        if win_keys:
                            self._pending_window_keys.extend(win_keys)
                return tui_output

            return self._render_media_tui(cols, rows, dt)
        finally:
            flush_duration = getattr(self._loop, "last_flush_duration", 0.0)
            if not isinstance(flush_duration, (int, float)):
                flush_duration = 0.0
            self.throttler.record_render_time(time.perf_counter() - render_started + flush_duration)

    def cycle_render_mode(self) -> str:
        """Cycles TUI rendering mode in real time: halfblock -> quadrant -> ascii -> halfblock."""
        if self.picture_viewer:
            return self.picture_viewer.cycle_renderer()

        cur = self.renderer.mode_name
        if cur == "halfblock":
            self.renderer = QuadrantRenderer()
        elif cur == "quadrant":
            self.renderer = ASCIIRenderer(color_profile="truecolor")
        elif cur == "ascii":
            if getattr(self, "caps", None) and self.caps.has_kitty:
                self.renderer = KittyRenderer()
            else:
                self.renderer = HalfBlockRenderer()
        else:
            self.renderer = HalfBlockRenderer()
        return self.renderer.mode_name

    def _video_decode_dimensions(
        self, cols: int, rows: int, native_w: int, native_h: int
    ) -> tuple[int, int]:
        """Decode only detail the active output can display; native windows keep HD."""
        width, height = self.quality_manager.get_target_dimensions(
            cols, rows, native_w=native_w, native_h=native_h, is_video=True
        )
        native_output = self.enable_native_window or (
            self.native_window and self.native_window.is_open
        )
        if native_output:
            if self.quality_manager.current_profile.id == "auto" and native_w and native_h:
                scale = min(1.0, 1280 / native_w, 720 / native_h)
                return max(16, int(native_w * scale) // 2 * 2), max(
                    16, int(native_h * scale) // 2 * 2
                )
            return width, height
        if self.renderer.is_pixel_native:
            max_w = min(1920, cols * self.caps.cell_width_px)
            max_h = min(1080, rows * self.caps.cell_height_px)
        else:
            max_w = cols * (2 if self.renderer.mode_name == "quadrant" else 1)
            max_h = rows * 2
        scale = min(1.0, max(16, max_w) / width, max(16, max_h) / height)
        return max(16, int(width * scale) // 2 * 2), max(16, int(height * scale) // 2 * 2)

    def _cycle_quality(self, cols: int, rows: int) -> None:
        """Cycles video quality profile and updates decoder dimensions."""
        canvas_rows = max(4, rows - 6)
        if self.video_decoder:
            self.quality_manager.cycle_profile()
            nat_w = self._current_meta.width if self._current_meta else 0
            nat_h = self._current_meta.height if self._current_meta else 0
            target_w, target_h = self._video_decode_dimensions(cols, canvas_rows, nat_w, nat_h)
            self.video_decoder.update_dimensions(
                target_w, target_h, start_time_sec=self.master_clock.get_time()
            )
            self._buffered_video_frame = None
            self._holding_future_frame = False
        elif self.turntable:
            self.fft_band_idx = (self.fft_band_idx + 1) % len(self.fft_band_options)

    def _render_with_fallback(
        self,
        img: Image.Image,
        target_cols: int,
        target_rows: int,
        exact_1to1: bool = False,
    ) -> str:
        """Renders an image via active renderer, automatically degrading on graphics errors."""
        try:
            if self.renderer.mode_name == "kitty" and not getattr(
                self.renderer, "is_native_active", False
            ):
                return self.renderer.render_braille(
                    img, target_cols=target_cols, target_rows=target_rows, exact_1to1=exact_1to1
                )
            return self.renderer.render_frame(
                img, target_cols=target_cols, target_rows=target_rows, exact_1to1=exact_1to1
            )
        except Exception as exc:
            old_mode = self.renderer.mode_name
            self.renderer = FallbackManager.degrade_renderer(self.renderer)
            logger.warning(
                f"Renderer error in mode '{old_mode}': {exc}. Degraded to '{self.renderer.mode_name}'"
            )
            try:
                return self.renderer.render_frame(
                    img, target_cols=target_cols, target_rows=target_rows, exact_1to1=exact_1to1
                )
            except Exception:
                return ""

    def _advance_track(self, delta: int, *, wrap: bool = False, manual: bool = False) -> None:
        """Transitions playback to next or previous playlist entry."""
        next_file = (
            self.playlist_manager.next_track(wrap=wrap, manual=manual)
            if delta > 0
            else self.playlist_manager.prev_track(wrap=wrap)
        )
        if not next_file:
            return
        self._teardown_media_components()
        self._current_meta = None
        try:
            self._current_meta = MediaProbe.probe(next_file)
        except Exception as exc:
            logger.warning("Cannot play %s: %s", next_file, exc)
            self.stop()
            return
        self._init_media_components()

    @staticmethod
    def _strip_ansi(s: str) -> str:
        return re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", s)

    def _build_responsive_header(self, cols: int, cur_name: str) -> str:
        cur_name = safe_text(cur_name)
        status_tag = "▶ PLAY" if self.transport.is_playing else "❚❚ PAUSE"
        is_video = bool(
            self.video_decoder is not None
            or (
                self._current_meta
                and self._current_meta.media_type == "video"
                and not getattr(self, "turntable", None)
            )
        )
        repeat_lbl = (
            "OFF"
            if self.playlist_manager.repeat_mode == "none"
            else self.playlist_manager.repeat_mode.upper()
        )
        vol_pct = int(self.transport.volume * 100) if not self.transport.is_muted else "MUTED"
        idx_str = f"[{self.playlist_manager.current_idx + 1}/{self.playlist_manager.total_tracks}]"
        icon = "🎬" if is_video else "🎵"

        # Line 1: Brand, status, track index, media name
        l1_prefix = f" 🔱 PINAK PLAYER │ {status_tag} {idx_str} {icon} "
        v_l1_prefix = len(self._strip_ansi(l1_prefix))
        avail_name = max(4, cols - v_l1_prefix - 2)
        disp_name = cur_name[: avail_name - 3] + "..." if len(cur_name) > avail_name else cur_name
        l1_left = f"{l1_prefix}{disp_name}"
        spaces_l1 = max(0, cols - len(self._strip_ansi(l1_left)))
        line1 = (
            f"\x1b[2K\x1b[48;2;22;34;52m\x1b[38;2;120;225;255;1m{l1_left}{' ' * spaces_l1}\x1b[0m"
        )

        # Line 2: Resolution/Quality/FFT, Mode, Volume, and Repeat setting
        if is_video:
            nat_w = self._current_meta.width if self._current_meta else 0
            nat_h = self._current_meta.height if self._current_meta else 0
            prof_lbl = (
                self.quality_manager.current_profile.label
                if hasattr(self, "quality_manager")
                else "Native"
            )
            orig_str = f"Original: {nat_w}x{nat_h} px │ " if (nat_w and nat_h) else ""
            sub_lbl = (
                self.subtitle_tracks[self.active_sub_idx].label
                if (
                    getattr(self, "subtitle_tracks", None)
                    and 0 <= self.active_sub_idx < len(self.subtitle_tracks)
                )
                else "OFF"
            )
            sub_str = f" │ CC: {sub_lbl}" if getattr(self, "subtitle_tracks", None) else ""
            l2_left = (
                f"   [Res: {prof_lbl} | {self.renderer.mode_name.upper()}]{sub_str} │ {orig_str}"
            )
        else:
            bands_lbl = (
                f"{self.fft_band_options[self.fft_band_idx]}B"
                if hasattr(self, "fft_band_options")
                else "32B"
            )
            l2_left = f"   [Audio Hi-Fi | Mode: {self.renderer.mode_name.upper()}] │ FFT: {bands_lbl} │ Vis: {self.current_vis_theme.title()}"

        vol_str = f"Vol: {vol_pct}%" if isinstance(vol_pct, int) else f"Vol: {vol_pct}"
        shuffle_lbl = "ON" if self.playlist_manager.is_shuffled else "OFF"
        l2_right = f"{vol_str} │ Rep: {repeat_lbl} │ Shuf: {shuffle_lbl} "
        v_l2_right = len(self._strip_ansi(l2_right))
        avail_l2_left = max(0, cols - v_l2_right - 1)
        if len(self._strip_ansi(l2_left)) > avail_l2_left:
            l2_left = l2_left[:avail_l2_left]
        spaces_l2 = max(1, cols - len(self._strip_ansi(l2_left)) - v_l2_right)
        line2 = f"\x1b[2K\x1b[48;2;18;28;44m\x1b[38;2;100;200;235m{l2_left}{' ' * spaces_l2}{l2_right}\x1b[0m"

        return f"{line1}\n{line2}"

    def _build_responsive_footer(self, cols: int) -> str:
        is_video = bool(
            self.video_decoder is not None
            or (
                self._current_meta
                and self._current_meta.media_type == "video"
                and not getattr(self, "turntable", None)
            )
        )
        if is_video:
            if cols >= 95:
                l1_left = " [Space] Play/Pause  [←/→] ±10s  [↑/↓] Vol  [Ctrl+M] Mute  [r] Repeat  [n/p] Next/Prev "
                l2_left = " [m] Mode  [q] Quality  [c] Subtitles  [w] GPU Window  [x/Esc] Quit "
            elif cols >= 70:
                l1_left = " [Space] Play  [←/→] ±10s  [↑/↓] Vol  [Ctrl+M] Mute  [r] Repeat "
                l2_left = " [m] Mode  [q] Qual  [c] Subs  [w] GPU Win  [x] Quit "
            else:
                l1_left = " [Space] Play  [Ctrl+M] Mute  [r] Repeat "
                l2_left = " [m] Mode  [q] Qual  [w] GPU  [x] Quit "
        else:
            if cols >= 95:
                l1_left = " [Space] Play/Pause  [←/→] ±10s  [↑/↓] Vol  [Ctrl+M] Mute  [r] Repeat  [n/p] Next/Prev "
                l2_left = " [m] Mode  [q] Bands  [v] Visualizer  [w] GPU Window  [x/Esc] Quit "
            elif cols >= 75:
                l1_left = " [Space] Play  [←/→] ±10s  [↑/↓] Vol  [Ctrl+M] Mute  [r] Repeat "
                l2_left = " [m] Mode  [q] Bands  [v] Visualizer  [w] GPU Win  [x] Quit "
            else:
                l1_left = " [Space] Play  [Ctrl+M] Mute  [r] Repeat "
                l2_left = " [m] Mode  [v] Visualizer  [w] GPU  [x] Quit "

        # Keep the shuffle toggle visible even when the first row is truncated.
        l2_left = " [s] Shuffle " + l2_left.lstrip()
        l2_left = l2_left[:cols]

        # Close button in bottom navigation bar
        close_btn = " [ ✕ Close Media ] " if cols >= 80 else " [✕] "
        v_close = len(self._strip_ansi(close_btn))
        avail_l1 = max(0, cols - v_close - 1)
        if len(l1_left) > avail_l1:
            l1_left = l1_left[:avail_l1]
        spaces_l1 = max(1, cols - len(l1_left) - v_close)
        line1 = f"\x1b[2K\x1b[48;2;28;34;46m\x1b[38;2;215;225;235m{l1_left}{' ' * spaces_l1}\x1b[1;31m{close_btn}\x1b[0m"

        spaces_l2 = max(0, cols - len(self._strip_ansi(l2_left)))
        line2 = f"\x1b[2K\x1b[48;2;24;28;38m\x1b[38;2;180;195;210m{l2_left}{' ' * spaces_l2}\x1b[0m"

        return f"{line1}\n{line2}"

    def _render_media_tui(self, cols: int, rows: int, dt: float) -> str:
        """Renders TUI frame for audio or video playback."""
        if cols < 40 or rows < 10:
            return "Terminal too small; resize to 40 × 10 (Esc to close)"[: max(0, cols)]
        cur_file = self.playlist_manager.get_current()
        cur_name = safe_text(cur_file.name) if cur_file else "Unknown"

        audio_error = getattr(self.audio_backend, "error", None)
        video_error = getattr(self.video_decoder, "error", None)
        if (
            isinstance(video_error, str)
            and video_error
            and not getattr(self.video_decoder, "_needs_software_fallback", False)
            and not getattr(self.video_decoder, "_frame_queue", None)
        ):
            logger.error("Video playback failed: %s", video_error)
            self.stop()
            return "Video output unavailable: " + safe_text(video_error)
        if isinstance(audio_error, str) and audio_error:
            if self.video_decoder is not None:
                if self.audio_backend:
                    self.audio_backend.stop()
                self.audio_backend = None
                self.master_clock = MasterAudioClock()
                self.master_clock.set_time(self.transport.current_pts)
                logger.warning("Continuing video without audio output: %s", audio_error)
            else:
                self.stop()
                return "Audio output unavailable: " + safe_text(audio_error)

        if (
            self.video_decoder is not None
            and self.audio_backend is not None
            and getattr(self.audio_backend, "is_eos", False) is True
            and self.master_clock.audio_backend is not None
        ):
            # A short/silent audio stream must not end or freeze a longer video.
            position = self.master_clock.get_time()
            self.master_clock = MasterAudioClock()
            self.master_clock.set_time(position)
            if not self.transport.is_playing:
                self.master_clock.pause()

        # Update Master Clock
        master_pts = self.master_clock.get_time()
        self.transport.current_pts = master_pts

        # Track completion, tone-arm parking, and auto-advance
        dur = self.transport.duration_sec
        is_completed = self.transport.is_playing and (
            (dur > 0 and master_pts >= dur)
            or (self.video_decoder is None and getattr(self.audio_backend, "is_eos", False) is True)
            or (
                getattr(self.video_decoder, "eof", False) is True
                and not getattr(self.video_decoder, "_frame_queue", None)
                and not self._holding_future_frame
                and (
                    self._last_frame_pts is None
                    or master_pts
                    >= self._last_frame_pts
                    + 1.0 / max(1.0, float(getattr(self.video_decoder, "target_fps", 30.0)))
                )
            )
        )
        is_video = bool(
            self.video_decoder is not None
            or (
                self._current_meta
                and self._current_meta.media_type == "video"
                and not getattr(self, "turntable", None)
            )
        )
        if is_completed:
            if self.turntable:
                self.turntable.set_parked(True)
            if self.playlist_manager.is_shuffled:
                if self.playlist_manager.has_next():
                    self._advance_track(delta=1)
                else:
                    self.transport.is_playing = False
                    if self.audio_backend:
                        self.audio_backend.pause()
                    self.master_clock.pause()
            elif is_video:
                if self.playlist_manager.has_next():
                    # Videos continue in sequence (under Repeat OFF, ALL, or SOLO)
                    self._advance_track(delta=1)
                else:
                    # In Repeat OFF ('none'): videos continue in sequence but do not repeat.
                    # After playing all videos, TUI leads to the first video and stops (paused).
                    # The user can start playback by clicking space.
                    self.playlist_manager.current_idx = 0
                    first_file = self.playlist_manager.get_current()
                    if first_file:
                        self._teardown_media_components()
                        self._current_meta = None
                        try:
                            self._current_meta = MediaProbe.probe(first_file)
                        except Exception as exc:
                            logger.warning("Cannot rewind playlist: %s", exc)
                            self.stop()
                            return "Unable to open the first playlist item"
                        self._init_media_components()
                    self.transport.is_playing = False
                    if self.audio_backend:
                        self.audio_backend.pause()
                    self.master_clock.pause()
            elif self._current_meta and self._current_meta.media_type == "audio":
                self._advance_track(delta=1, wrap=True)
            elif self.playlist_manager.has_next():
                self._advance_track(delta=1)
            else:
                self.transport.is_playing = False
                if self.audio_backend:
                    self.audio_backend.pause()

        # Check for window size change (maximize/minimize) to clear screen cleanly
        if not hasattr(self, "_last_term_size") or self._last_term_size != (cols, rows):
            self._last_term_size = (cols, rows)
            clear_prefix = "\x1b[2J\x1b[H"
        else:
            clear_prefix = ""

        # 1. Responsive Header Bar (2 lines)
        header_bar = self._build_responsive_header(cols, cur_name)

        # 2. Canvas Area - Allocate 2 rows header, 1 row timeline, 2 rows footer, 1 row safety margin
        show_gpu_tip = bool(
            self.video_decoder
            and not (self.native_window and self.native_window.is_open)
            and rows >= 10
        )
        tip_reserved = 1 if show_gpu_tip else 0
        canvas_rows = max(4, rows - 6 - tip_reserved)
        body_str = ""

        if self.turntable and self.audio_decoder:
            # Audio mode: Turntable + FFT Spectrum HUD Panel
            if self.transport.is_playing:
                self.turntable.update_physics(dt, True)
                prog = (master_pts / dur) if dur > 0 else 0.0
                turntable_img = self.turntable.render_turntable(progress_frac=prog)

                # Pull PCM samples for FFT synchronized with playback pts
                pcm_samples = self.audio_decoder.get_visualizer_samples(count=1024, pts=master_pts)
                bands, peaks = self.fft_engine.process_pcm(pcm_samples)
                self._frozen_visualizer_bands = bands
                self._frozen_visualizer_peaks = peaks
                self._frozen_visualizer_pcm = pcm_samples
                self._frozen_turntable_img = turntable_img
            else:
                # When paused, freeze visualizer completely (no moving graph, no peak decay, no wave advance)
                prog = (master_pts / dur) if dur > 0 else 0.0
                turntable_img = (
                    self._frozen_turntable_img
                    if self._frozen_turntable_img is not None
                    else self.turntable.render_turntable(progress_frac=prog)
                )
                bands = self._frozen_visualizer_bands or ([0.0] * 32)
                peaks = self._frozen_visualizer_peaks or ([0.0] * 32)
                pcm_samples = self._frozen_visualizer_pcm or ([0.0] * 1024)

            # Determine layout split
            # Left half: turntable; Right half: audio spectrum HUD panel
            left_w = max(20, min(cols // 2, cols - 24))
            right_w = max(16, cols - left_w - 1)

            tt_render = self._render_with_fallback(
                turntable_img, target_cols=left_w, target_rows=canvas_rows
            )
            tt_lines = tt_render.split("\n")

            panel_lines = SpectrumBarsRenderer.render_panel(
                bands,
                peaks,
                pcm_samples,
                max_cols=right_w,
                max_rows=canvas_rows,
                theme=self.current_vis_theme,
            )

            combined_lines = []
            for r_idx in range(canvas_rows):
                raw_left = tt_lines[r_idx] if r_idx < len(tt_lines) else ""
                cleaned_left = raw_left.replace("\x1b[2K", "")
                left_line = _fit_to_width(cleaned_left, left_w)
                raw_right = panel_lines[r_idx] if r_idx < len(panel_lines) else ""
                right_line = _fit_to_width(raw_right, right_w)
                combined_lines.append(f"{left_line} {right_line}")
            body_str = "\n".join(combined_lines)

            # For Music player: Show Album Art Thumbnail in GPU window if opened
            if self.native_window and self.native_window.is_open:
                if self._cached_audio_thumb is None:
                    if self._current_meta and self._current_meta.album_art_bytes:
                        try:
                            import io

                            self._cached_audio_thumb = Image.open(
                                io.BytesIO(self._current_meta.album_art_bytes)
                            ).convert("RGB")
                        except Exception:
                            self._cached_audio_thumb = None
                    if self._cached_audio_thumb is None:
                        self._cached_audio_thumb = turntable_img.convert("RGB")

                thumb_img = self._cached_audio_thumb or turntable_img.convert("RGB")
                osc_state = OSCState(
                    title=cur_name,
                    current_pts=master_pts,
                    duration_sec=self.transport.duration_sec,
                    is_playing=self.transport.is_playing,
                    volume=self.transport.volume,
                    is_muted=self.transport.is_muted,
                    subtitle_track_name="None",
                    quality_label="Audio Hi-Fi",
                    renderer_mode="GPU Native",
                )
                keys = self.native_window.show_frame(thumb_img, state=osc_state, osc=self.osc)
                if keys:
                    self._pending_window_keys.extend(keys)
        elif self.video_decoder:
            nat_w = self._current_meta.width if self._current_meta else 0
            nat_h = self._current_meta.height if self._current_meta else 0
            target_w, target_h = self._video_decode_dimensions(cols, canvas_rows, nat_w, nat_h)
            self.video_decoder.update_dimensions(target_w, target_h, start_time_sec=master_pts)

            target_fps = 30.0
            raw_fps = getattr(self.video_decoder, "target_fps", None)
            if isinstance(raw_fps, (int, float)):
                target_fps = max(1.0, float(raw_fps))
            frame_dur = 1.0 / target_fps
            frame_threshold = frame_dur * 0.75

            if self.transport.is_playing:
                # 1. Hard desync check: if current buffered frame or clock differs by > 0.35s
                if (
                    self._buffered_video_frame is not None
                    and hasattr(self._buffered_video_frame, "pts")
                    and isinstance(self._buffered_video_frame.pts, (int, float))
                ):
                    hard_drift = self._buffered_video_frame.pts - master_pts
                    # Normal rendering lag is recovered by dropping queued frames.
                    # Restart only after a large backward drift, with a cooldown;
                    # restarting each frame prevents the decoder from ever catching up.
                    now = time.monotonic()
                    if hard_drift < -2.0 and now - self._last_video_resync >= 2.0:
                        self._last_video_resync = now
                        self.video_decoder.seek(master_pts)
                        self._buffered_video_frame = self.video_decoder.read_frame()
                        self._last_frame_pts = master_pts
                        if (
                            self._buffered_video_frame is not None
                            and hasattr(self._buffered_video_frame, "width")
                            and isinstance(self._buffered_video_frame.width, int)
                            and isinstance(self._buffered_video_frame.height, int)
                            and isinstance(
                                getattr(self._buffered_video_frame, "rgb_data", None),
                                (bytes, bytearray),
                            )
                        ):
                            with contextlib.suppress(Exception):
                                self._last_video_img = Image.frombytes(
                                    "RGB",
                                    (
                                        self._buffered_video_frame.width,
                                        self._buffered_video_frame.height,
                                    ),
                                    self._buffered_video_frame.rgb_data,
                                )

                # 2. Check if initial frame or if audio master clock has advanced to the next frame
                need_next_frame = (
                    self._buffered_video_frame is None
                    or self._last_frame_pts is None
                    or self._last_frame_pts < 0.0
                    or (master_pts - self._last_frame_pts) >= frame_threshold
                )
                if self._buffered_video_frame is not None:
                    action, _ = VideoFrameScheduler.evaluate(
                        self._buffered_video_frame.pts, master_pts
                    )
                    if action == SyncAction.SLEEP_WAIT:
                        need_next_frame = False
                        self._holding_future_frame = True
                    elif action == SyncAction.DROP_FRAME:
                        self._holding_future_frame = False
                        need_next_frame = True
                    elif self._holding_future_frame or self._last_video_img is None:
                        frame = self._buffered_video_frame
                        self._last_video_img = Image.frombytes(
                            "RGB", (frame.width, frame.height), frame.rgb_data
                        )
                        self._last_frame_pts = frame.pts
                        self._holding_future_frame = False
                        need_next_frame = False

                if need_next_frame:
                    next_f = self.video_decoder.read_frame()
                    if next_f is not None:
                        # Drop lagging stale frames if audio master clock is ahead
                        dropped = 0
                        while (
                            next_f is not None
                            and hasattr(next_f, "pts")
                            and isinstance(next_f.pts, (int, float))
                            and (master_pts - next_f.pts) > frame_threshold
                            and dropped < 32
                        ):
                            dropped += 1
                            stale_drop = self.video_decoder.read_frame()
                            if stale_drop is None:
                                break
                            next_f = stale_drop

                        self._buffered_video_frame = next_f
                        if (
                            VideoFrameScheduler.evaluate(next_f.pts, master_pts)[0]
                            != SyncAction.SLEEP_WAIT
                            and self._buffered_video_frame is not None
                            and hasattr(self._buffered_video_frame, "width")
                            and isinstance(self._buffered_video_frame.width, int)
                            and isinstance(self._buffered_video_frame.height, int)
                            and isinstance(
                                getattr(self._buffered_video_frame, "rgb_data", None),
                                (bytes, bytearray),
                            )
                        ):
                            with contextlib.suppress(Exception):
                                self._last_video_img = Image.frombytes(
                                    "RGB",
                                    (
                                        self._buffered_video_frame.width,
                                        self._buffered_video_frame.height,
                                    ),
                                    self._buffered_video_frame.rgb_data,
                                )
                                self._last_frame_pts = self._buffered_video_frame.pts
                        if (
                            VideoFrameScheduler.evaluate(next_f.pts, master_pts)[0]
                            == SyncAction.SLEEP_WAIT
                        ):
                            self._holding_future_frame = True
            else:
                if self._last_video_img is None:
                    if self._buffered_video_frame is None:
                        self._buffered_video_frame = self.video_decoder.read_frame()
                    if (
                        self._buffered_video_frame is not None
                        and hasattr(self._buffered_video_frame, "width")
                        and isinstance(self._buffered_video_frame.width, int)
                        and isinstance(self._buffered_video_frame.height, int)
                        and isinstance(
                            getattr(self._buffered_video_frame, "rgb_data", None),
                            (bytes, bytearray),
                        )
                    ):
                        with contextlib.suppress(Exception):
                            self._last_video_img = Image.frombytes(
                                "RGB",
                                (
                                    self._buffered_video_frame.width,
                                    self._buffered_video_frame.height,
                                ),
                                self._buffered_video_frame.rgb_data,
                            )
                            self._last_frame_pts = self._buffered_video_frame.pts

            if self._last_video_img:
                display_img = self._last_video_img
                # Check for active subtitle cue
                active_cue = None
                if 0 <= self.active_sub_idx < len(self.subtitle_tracks):
                    active_cue = self.subtitle_tracks[self.active_sub_idx].get_cue_at(master_pts)

                if active_cue:
                    display_img = SubtitleRenderer.render_overlay_on_frame(
                        display_img, active_cue.text
                    )

                body_str = self._render_with_fallback(
                    display_img, target_cols=cols, target_rows=canvas_rows
                )

                # If native GPU window is open, blit frame with OSC overlay
                if self.native_window and self.native_window.is_open:
                    osc_state = OSCState(
                        title=cur_name,
                        current_pts=master_pts,
                        duration_sec=self.transport.duration_sec,
                        is_playing=self.transport.is_playing,
                        volume=self.transport.volume,
                        is_muted=self.transport.is_muted,
                        subtitle_track_name=(
                            self.subtitle_tracks[self.active_sub_idx].label
                            if 0 <= self.active_sub_idx < len(self.subtitle_tracks)
                            else "Off"
                        ),
                        quality_label=self.quality_manager.current_profile.label,
                        renderer_mode=self.renderer.mode_name.upper(),
                    )
                    keys = self.native_window.show_frame(display_img, state=osc_state, osc=self.osc)
                    if keys:
                        self._pending_window_keys.extend(keys)
            else:
                body_str = (
                    ("\n" * (canvas_rows // 2)) + " " * (cols // 4) + "[Buffering Video Stream...]"
                )
        else:
            body_str = ("\n" * (canvas_rows // 2)) + " " * (cols // 4) + f"Playing: {cur_name}"

        # 3. User Guidance Notification Ribbon (if viewing video in TUI and GPU window not open)
        tip_bar = ""
        if show_gpu_tip:
            if cols >= 95:
                tip_txt = (
                    " 💡 Video hard to see in TUI? Press [w] for excellent GPU Window view (HD) "
                )
            elif cols >= 65:
                tip_txt = " 💡 Video hard to see? Press [w] for excellent GPU Window "
            else:
                tip_txt = " 💡 Press [w] for GPU Win "
            v_tip = len(self._strip_ansi(tip_txt))
            pad_tip = " " * max(0, cols - v_tip)
            tip_bar = (
                f"\x1b[2K\x1b[48;2;22;36;54m\x1b[38;2;255;210;75;1m{tip_txt}{pad_tip}\x1b[0m\n"
            )

        # 4. Progress Bar & Timeline Scrubber
        timeline_bar = self.transport.get_progress_bar(width=cols)

        # 5. Responsive Footer Control Bar
        footer_bar = self._build_responsive_footer(cols)

        return f"{clear_prefix}{header_bar}\n{body_str}\n{tip_bar}{timeline_bar}\n{footer_bar}"
