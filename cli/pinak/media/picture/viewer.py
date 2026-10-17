"""Interactive Picture Viewer with deep zoom, pan, and rotation."""

from __future__ import annotations

import re
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from PIL import Image

from ...text_safety import safe_text
from ..core.input_parser import KeyEvent, MouseEvent
from ..decoders.image_loader import ImageLoader, LoadedImage
from ..renderers.ascii_retro import ASCIIRenderer
from ..renderers.base import BaseRenderer
from ..renderers.halfblock import HalfBlockRenderer
from ..renderers.pixel_kitty import KittyRenderer
from ..renderers.quadrant import QuadrantRenderer
from ..sync.fallback_manager import FallbackManager


class PictureViewer:
    SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tiff"}

    def __init__(
        self,
        image_paths: Sequence[str | Path] | list[Any],
        initial_index: int = 0,
        renderer: BaseRenderer | None = None,
    ) -> None:
        candidates = [Path(p).resolve() for p in image_paths if Path(p).is_file()]
        # Prioritize true picture extensions to prevent crashing on mixed playlists
        picture_candidates = [
            p for p in candidates if p.suffix.lower() in self.SUPPORTED_EXTENSIONS
        ]
        self.image_paths = picture_candidates if picture_candidates else candidates
        if not self.image_paths:
            raise ValueError("No valid image files provided to PictureViewer")

        self.current_index = (
            max(0, initial_index % len(self.image_paths)) if self.image_paths else 0
        )
        self.renderer: BaseRenderer = renderer or QuadrantRenderer()
        self.scale_mode: str = "native_1to1"  # "native_1to1" (actual size) or "fit"
        self.is_native_window_open: bool = False
        self.zoom: float = 1.0
        self.pan_x: float = 0.0
        self.pan_y: float = 0.0
        self.rotation_deg: int = 0
        self._last_term_size: tuple[int, int] | None = None
        self._current_loaded: LoadedImage | None = None
        self._load_current_image()

    def _load_current_image(self) -> None:
        if not self.image_paths:
            self._current_loaded = None
            return
        path = self.image_paths[self.current_index]
        try:
            self._current_loaded = ImageLoader.load(path)
        except Exception:
            self._current_loaded = ImageLoader.create_placeholder(f"Image Unavailable: {path.name}")
        self.reset_viewport()

    def reset_viewport(self) -> None:
        self.zoom = 1.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.rotation_deg = 0

    def toggle_scale_mode(self) -> str:
        """Toggles between fit-to-window and 1:1 exact native resolution pixel mapping."""
        if self.scale_mode == "fit":
            self.scale_mode = "native_1to1"
            self.zoom = 1.0
        else:
            self.scale_mode = "fit"
        return self.scale_mode

    def get_current_display_image(self) -> Image.Image | None:
        """Returns the current image frame with rotation applied for native GPU window."""
        if not self._current_loaded or not self._current_loaded.frames:
            return None
        cur_frame = self._current_loaded.get_frame(time.perf_counter())
        rot = self.rotation_deg % 360
        if rot == 90:
            return cur_frame.transpose(Image.Transpose.ROTATE_270)
        elif rot == 180:
            return cur_frame.transpose(Image.Transpose.ROTATE_180)
        elif rot == 270:
            return cur_frame.transpose(Image.Transpose.ROTATE_90)
        return cur_frame

    def zoom_in(self) -> None:
        self.scale_mode = "fit"
        self.zoom = min(10.0, self.zoom * 1.25)

    def zoom_out(self) -> None:
        self.scale_mode = "fit"
        self.zoom = max(0.1, self.zoom * 0.8)

    def pan(self, dx: float, dy: float) -> None:
        self.pan_x += dx
        self.pan_y += dy

    def rotate_cw(self) -> None:
        self.rotation_deg = (self.rotation_deg + 90) % 360

    def rotate_ccw(self) -> None:
        self.rotation_deg = (self.rotation_deg - 90) % 360

    def next_image(self) -> None:
        """Advances to the next image with circular modulo wrap-around."""
        if not self.image_paths:
            return
        self.current_index = (self.current_index + 1) % len(self.image_paths)
        self._load_current_image()

    def prev_image(self) -> None:
        """Returns to previous image with circular modulo wrap-around."""
        if not self.image_paths:
            return
        self.current_index = (self.current_index - 1) % len(self.image_paths)
        self._load_current_image()

    def toggle_fullscreen(self) -> None:
        """Deprecated compatibility method; native windows own fullscreen state."""
        import warnings

        warnings.warn("Use NativeVideoWindow.toggle_fullscreen()", DeprecationWarning, stacklevel=2)

    def cycle_renderer(self) -> str:
        if self.renderer.mode_name == "halfblock":
            self.renderer = QuadrantRenderer()
        elif self.renderer.mode_name == "quadrant":
            self.renderer = ASCIIRenderer(color_profile="truecolor")
        elif self.renderer.mode_name == "ascii":
            self.renderer = KittyRenderer()
        else:
            self.renderer = HalfBlockRenderer()
        return self.renderer.mode_name

    def cycle_zoom_preset(self) -> float:
        """Cycles through resolution and magnification scale presets."""
        self.scale_mode = "fit"
        presets = [1.0, 1.5, 2.0, 3.0, 0.5, 0.75]
        for p in presets:
            if p > self.zoom + 0.05:
                self.zoom = p
                return self.zoom
        self.zoom = presets[0]
        return self.zoom

    def handle_input(self, event: KeyEvent | MouseEvent) -> bool:
        """Processes input event. Returns True if event was handled."""
        if isinstance(event, KeyEvent):
            k = event.key.lower()
            if k in ("1", "z"):
                self.toggle_scale_mode()
                return True
            if k in ("+", "="):
                self.zoom_in()
                return True
            if k in ("-", "_"):
                self.zoom_out()
                return True
            if k in ("0", "home"):
                self.reset_viewport()
                return True
            if k in ("up", "k"):
                self.pan(0, -25)
                return True
            if k in ("down", "j"):
                self.pan(0, 25)
                return True
            if k in ("left", "h"):
                self.pan(-25, 0)
                return True
            if k in ("right", "l"):
                self.pan(25, 0)
                return True
            if k == "s":
                self.pan(0, 25)
                return True
            if k == "a":
                self.pan(-25, 0)
                return True
            if k == "d":
                self.pan(25, 0)
                return True
            if event.key == "R" or (k == "r" and event.shift) or k == "shift+r":
                self.rotate_ccw()
                return True
            if k == "r":
                self.rotate_cw()
                return True
            if k in ("n", "pagedown"):
                self.next_image()
                return True
            if k in ("p", "pageup"):
                self.prev_image()
                return True
            if k == "m":
                self.cycle_renderer()
                return True
        elif isinstance(event, MouseEvent):
            if event.button == 64:  # Wheel Up
                self.zoom_in()
                return True
            if event.button == 65:  # Wheel Down
                self.zoom_out()
                return True
        return False

    def render_tui(self, cols: int, rows: int, elapsed_sec: float) -> str:
        """Renders the full-screen Picture Viewer TUI frame."""
        if not self._current_loaded or not self._current_loaded.frames:
            return "No image loaded."

        if cols < 40 or rows < 10:
            return "Terminal too small; resize to 40 × 10 (Esc to close)"[: max(0, cols)]
        cur_path = self.image_paths[self.current_index]
        cur_frame = self._current_loaded.get_frame(elapsed_sec)

        # Allocate 2 rows for Header, 2 rows for Footer, 1 row safety buffer to prevent scrolling
        canvas_rows = max(4, rows - 5)

        # Handle lossless rotation
        rot = self.rotation_deg % 360
        if rot == 90:
            rotated = cur_frame.transpose(Image.Transpose.ROTATE_270)
        elif rot == 180:
            rotated = cur_frame.transpose(Image.Transpose.ROTATE_180)
        elif rot == 270:
            rotated = cur_frame.transpose(Image.Transpose.ROTATE_90)
        else:
            rotated = cur_frame

        src_w, src_h = rotated.size

        if abs(self.zoom - 1.0) < 1e-3 and abs(self.pan_x) < 1e-3 and abs(self.pan_y) < 1e-3:
            transformed = rotated
        else:
            transformed = ImageLoader.crop_and_scale(
                cur_frame,
                target_w=cur_frame.width,
                target_h=cur_frame.height,
                zoom=self.zoom,
                pan_x=self.pan_x,
                pan_y=self.pan_y,
                rotation_deg=self.rotation_deg,
            )

        # In TUI: show picture as it is with accurate aspect ratio.
        # Smaller images are shown in their own actual size without upscaling or stretching to fit the window.
        # Larger images are scaled down smoothly to fit the canvas, displaying the complete picture.
        try:
            if self.renderer.mode_name == "kitty" and not getattr(
                self.renderer, "is_native_active", False
            ):
                canvas_str = self.renderer.render_braille(
                    transformed, cols, canvas_rows, exact_1to1=(self.scale_mode == "native_1to1")
                )
            else:
                canvas_str = self.renderer.render_frame(
                    transformed, cols, canvas_rows, exact_1to1=(self.scale_mode == "native_1to1")
                )
        except Exception:
            self.renderer = FallbackManager.degrade_renderer(self.renderer)
            canvas_str = self.renderer.render_frame(
                transformed, cols, canvas_rows, exact_1to1=(self.scale_mode == "native_1to1")
            )

        if self.scale_mode == "native_1to1":
            scale_lbl = f"[ACTUAL 1:1 SIZE] {src_w}x{src_h} px"
        else:
            scale_lbl = f"[FIT] {int(self.zoom * 100)}%"

        # Build Sub-density badge
        if self.renderer.mode_name == "quadrant":
            sub_density = " (2x2 Quad)"
        elif self.renderer.mode_name == "kitty":
            sub_density = (
                " (APC)" if getattr(self.renderer, "is_native_active", False) else " (2x4 Matrix)"
            )
        else:
            sub_density = ""

        # Check for window size change (maximize/minimize) to clear screen cleanly
        if not hasattr(self, "_last_term_size") or self._last_term_size != (cols, rows):
            self._last_term_size = (cols, rows)
            clear_prefix = "\x1b[2J\x1b[H"
        else:
            clear_prefix = ""

        # Build Responsive 2-Line Header bar
        def _strip(s: str) -> str:
            return re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", s)

        idx_str = f"[{self.current_index + 1}/{len(self.image_paths)}]"
        gpu_badge = " [GPU-WIN]" if self.is_native_window_open else ""

        # Header Line 1: Brand, Index, Name, Original Dimensions
        orig_str = f" │ Original: {cur_frame.width}x{cur_frame.height} px"
        orig_display = orig_str if cols >= 70 else ""
        v_orig_len = len(_strip(orig_display))
        l1_prefix = f" 🔱 PINAK VIEWER │ {idx_str} 🖼 "
        v_l1_prefix = len(_strip(l1_prefix))
        avail_name = max(4, cols - v_l1_prefix - v_orig_len - 2)
        name_str = safe_text(cur_path.name)
        name_disp = name_str[: avail_name - 3] + "..." if len(name_str) > avail_name else name_str
        l1_left = f"{l1_prefix}{name_disp}{orig_display}"
        spaces_l1 = max(0, cols - len(_strip(l1_left)))
        hdr_line1 = (
            f"\x1b[2K\x1b[48;2;24;36;56m\x1b[38;2;120;225;255;1m{l1_left}{' ' * spaces_l1}\x1b[0m"
        )

        # Header Line 2: Scale, Rotation, Renderer Mode
        l2_left = f" Scale: {scale_lbl} │ Rot: {self.rotation_deg}°"
        l2_right = f"Mode: {self.renderer.mode_name.upper()}{sub_density}{gpu_badge} "
        v_l2_right = len(_strip(l2_right))
        avail_l2 = max(0, cols - v_l2_right - 1)
        if len(_strip(l2_left)) > avail_l2:
            l2_left = l2_left[:avail_l2]
        spaces_l2 = max(1, cols - len(_strip(l2_left)) - v_l2_right)
        hdr_line2 = f"\x1b[2K\x1b[48;2;18;28;44m\x1b[38;2;100;200;235m{l2_left}{' ' * spaces_l2}{l2_right}\x1b[0m"
        header_bar = f"{hdr_line1}\n{hdr_line2}"

        # Build Responsive 2-Line Footer bar
        if cols >= 95:
            f1_left = " [n/p] Next/Prev  [+/-] Zoom  [Arrows/WASD] Pan  [0] Reset  [1/z] Fit/1:1 "
            f2_left = " [r/R] Rotate  [m] Mode  [w] GPU Window  [x/Esc] Quit "
        elif cols >= 75:
            f1_left = " [n/p] Next/Prev  [+/-] Zoom  [WASD] Pan  [1] 1:1 "
            f2_left = " [r] Rotate  [m] Mode  [w] GPU  [x] Quit "
        else:
            f1_left = " [n/p] Next  [+/-] Zoom  [1] 1:1 "
            f2_left = " [r] Rot  [m] Mode  [w] GPU  [x] Quit "

        f1_right = " [ ✕ Close Media ] " if cols >= 80 else " [✕] "
        v_f1_right = len(_strip(f1_right))
        avail_f1 = max(0, cols - v_f1_right - 1)
        if len(f1_left) > avail_f1:
            f1_left = f1_left[:avail_f1]
        spaces_f1 = max(1, cols - len(f1_left) - v_f1_right)
        ftr_line1 = f"\x1b[2K\x1b[48;2;30;35;48m\x1b[38;2;220;225;235m{f1_left}{' ' * spaces_f1}\x1b[1;31m{f1_right}\x1b[0m"

        spaces_f2 = max(0, cols - len(f2_left))
        ftr_line2 = (
            f"\x1b[2K\x1b[48;2;24;28;38m\x1b[38;2;180;195;210m{f2_left}{' ' * spaces_f2}\x1b[0m"
        )
        footer_bar = f"{ftr_line1}\n{ftr_line2}"

        return f"{clear_prefix}{header_bar}\n{canvas_str}\n{footer_bar}"
