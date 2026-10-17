"""Native hardware-accelerated GUI video and picture window output (mpv vo_gpu style)."""

from __future__ import annotations

import contextlib
import logging
import os
from typing import TYPE_CHECKING, Any

from PIL import Image

if TYPE_CHECKING:
    from ..osc.controller import OnScreenController, OSCState

logger = logging.getLogger("pinak.media.window")


class NativeVideoWindow:
    """Displays native decoded frames in a screen-sized, aspect-correct window."""

    def __init__(self, title: str = "Pinak Media Player", initial_scale: float = 1.0) -> None:
        self.title = title
        self.initial_scale = initial_scale
        self.is_open = False
        self.is_fullscreen = False
        self._backend: str = "none"
        self._cv2_module: Any = None
        self._tk_module: Any = None
        self._imagetk_module: Any = None
        self._tk_root: Any = None
        self._tk_canvas: Any = None
        self._tk_photo_image: Any = None
        self._tk_pressed_keys: list[str] = []
        self._last_image_size: tuple[int, int] | None = None
        self._init_backend()

    def _init_backend(self, allow_cv2: bool = True) -> None:
        """Selects the best available GUI window backend (OpenCV or Tkinter)."""
        try:
            import cv2

            if allow_cv2 and hasattr(cv2, "imshow") and hasattr(cv2, "namedWindow"):
                self._cv2_module = cv2
                self._backend = "cv2"
                return
        except Exception:
            pass

        try:
            import tkinter as tk

            from PIL import ImageTk

            self._tk_module = tk
            self._imagetk_module = ImageTk
            self._backend = "tkinter"
            return
        except Exception:
            pass

        self._backend = "none"

    @property
    def backend_name(self) -> str:
        return self._backend

    MAX_COMPACT_WIDTH = 854
    MAX_COMPACT_HEIGHT = 480

    @staticmethod
    def _available_screen_size() -> tuple[int, int]:
        """Get display work area once; use a safe fallback on headless systems."""
        if os.name == "nt":
            try:
                import ctypes

                class Rect(ctypes.Structure):
                    _fields_ = [
                        (name, ctypes.c_long) for name in ("left", "top", "right", "bottom")
                    ]

                area = Rect()
                if ctypes.windll.user32.SystemParametersInfoW(0x30, 0, ctypes.byref(area), 0):
                    return area.right - area.left, area.bottom - area.top
            except Exception:
                pass
        try:
            import tkinter as tk

            root = tk.Tk()
            root.withdraw()
            try:
                return int(root.winfo_screenwidth()), int(root.winfo_screenheight())
            finally:
                root.destroy()
        except Exception:
            return 1280, 720

    @classmethod
    def compute_window_size(
        cls, src_w: int, src_h: int, screen_w: int, screen_h: int
    ) -> tuple[int, int]:
        """Fit an aspect-correct picture into most of the usable display."""
        src_w = max(1, src_w)
        src_h = max(1, src_h)
        available_w = max(320, int(screen_w * 0.9))
        available_h = max(240, int(screen_h * 0.85))
        scale = min(2.0, available_w / src_w, available_h / src_h)
        return min(available_w, max(1, round(src_w * scale))), min(
            available_h, max(1, round(src_h * scale))
        )

    def _opening_size(
        self, src_w: int, src_h: int, screen_w: int, screen_h: int
    ) -> tuple[int, int]:
        width, height = self.compute_window_size(src_w, src_h, screen_w, screen_h)
        return max(1, round(width * self.initial_scale)), max(1, round(height * self.initial_scale))

    @classmethod
    def compute_compact_size(
        cls,
        src_w: int,
        src_h: int,
        max_w: int = MAX_COMPACT_WIDTH,
        max_h: int = MAX_COMPACT_HEIGHT,
    ) -> tuple[int, int]:
        """Calculates a compact window size that fits neatly in a smaller area of the screen without covering the display."""
        if src_w <= 0 or src_h <= 0:
            return (max_w, max_h)
        if src_w <= max_w and src_h <= max_h:
            return (src_w, src_h)
        scale = min(max_w / src_w, max_h / src_h)
        return (max(1, int(src_w * scale)), max(1, int(src_h * scale)))

    def open(self, initial_size: tuple[int, int] | None = None) -> bool:
        """Open at a usable size fitted to the display work area."""
        if self._backend == "cv2" and self._cv2_module is not None:
            try:
                cv2 = self._cv2_module
                cv2.namedWindow(self.title, cv2.WINDOW_NORMAL)
                with contextlib.suppress(Exception):
                    cv2.setWindowProperty(
                        self.title, cv2.WND_PROP_ASPECT_RATIO, cv2.WINDOW_KEEPRATIO
                    )

                init_w, init_h = (
                    initial_size
                    if (initial_size and initial_size[0] > 0 and initial_size[1] > 0)
                    else (self.MAX_COMPACT_WIDTH, self.MAX_COMPACT_HEIGHT)
                )
                screen_w, screen_h = self._available_screen_size()
                win_w, win_h = self._opening_size(init_w, init_h, screen_w, screen_h)
                cv2.resizeWindow(self.title, win_w, win_h)
                self._last_image_size = (init_w, init_h)
                self.is_open = True
                return True
            except Exception as e:
                logger.warning(f"Failed to open native OpenCV window: {e}")
                with contextlib.suppress(Exception):
                    self._cv2_module.destroyWindow(self.title)
                self._init_backend(allow_cv2=False)

        if self._backend == "tkinter" and self._tk_module is not None:
            try:
                tk = self._tk_module
                root = tk.Tk()
                root.title(self.title)
                init_w, init_h = (
                    initial_size
                    if (initial_size and initial_size[0] > 0 and initial_size[1] > 0)
                    else (self.MAX_COMPACT_WIDTH, self.MAX_COMPACT_HEIGHT)
                )
                win_w, win_h = self._opening_size(
                    init_w, init_h, int(root.winfo_screenwidth()), int(root.winfo_screenheight())
                )
                root.geometry(f"{win_w}x{win_h}")
                root.configure(bg="black")

                canvas = tk.Canvas(root, bg="black", highlightthickness=0)
                canvas.pack(fill=tk.BOTH, expand=True)

                def _on_key(event: Any) -> None:
                    mapped = self._map_tk_key(event)
                    if mapped:
                        self._tk_pressed_keys.append(mapped)

                def _on_close() -> None:
                    self.close()

                root.bind("<KeyPress>", _on_key)
                root.protocol("WM_DELETE_WINDOW", _on_close)

                self._tk_root = root
                self._tk_canvas = canvas
                self._last_image_size = (init_w, init_h)
                self.is_open = True
                root.update_idletasks()
                root.update()
                return True
            except Exception as e:
                logger.warning(f"Failed to open native Tkinter window: {e}")
                self._backend = "none"

        return False

    def show_frame(
        self,
        frame_img: Image.Image,
        state: OSCState | None = None,
        osc: OnScreenController | None = None,
    ) -> list[str]:
        """
        Fit each frame to the current window while preserving its aspect ratio.
        Returns a list of key names pressed during this tick.
        """
        src_w, src_h = frame_img.size

        if not self.is_open and not self.open(initial_size=(src_w, src_h)):
            return []

        # If OSC overlay is enabled, draw it on the frame
        render_img = frame_img
        if osc is not None and state is not None:
            render_img = osc.render_overlay(frame_img, state)

        pressed_keys: list[str] = []

        if self._backend == "cv2" and self._cv2_module is not None:
            try:
                import numpy as np

                cv2 = self._cv2_module
                # Check if window was closed by the user clicking the OS close 'X' button
                try:
                    vis_prop = cv2.getWindowProperty(self.title, cv2.WND_PROP_VISIBLE)
                    if isinstance(vis_prop, (int, float)) and vis_prop < 1:
                        self.is_open = False
                        return []
                except Exception:
                    pass

                # Decoder resolution changes after opening must not shrink the
                # window or undo a size selected by the user.
                self._last_image_size = (src_w, src_h)

                # Query current client window dimensions
                try:
                    rect = cv2.getWindowImageRect(self.title)
                    if isinstance(rect, (tuple, list)) and len(rect) >= 4:
                        win_w, win_h = int(rect[2]), int(rect[3])
                    else:
                        win_w, win_h = src_w, src_h
                except Exception:
                    win_w, win_h = src_w, src_h

                if win_w <= 0 or win_h <= 0:
                    win_w, win_h = src_w, src_h

                # Convert PIL RGB to OpenCV BGR numpy array
                rgb_arr = np.array(render_img)
                bgr_arr = cv2.cvtColor(rgb_arr, cv2.COLOR_RGB2BGR)
                if not isinstance(bgr_arr, np.ndarray):
                    bgr_arr = rgb_arr

                scale = min(win_w / src_w, win_h / src_h)
                new_w = max(1, int(src_w * scale))
                new_h = max(1, int(src_h * scale))
                if (new_w, new_h) == (src_w, src_h):
                    resized = bgr_arr
                else:
                    resized = cv2.resize(
                        bgr_arr,
                        (new_w, new_h),
                        interpolation=cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LINEAR,
                    )
                canvas = np.zeros((win_h, win_w, 3), dtype=np.uint8)
                ox = (win_w - new_w) // 2
                oy = (win_h - new_h) // 2
                canvas[oy : oy + new_h, ox : ox + new_w] = resized
                final_arr = canvas

                cv2.imshow(self.title, final_arr)

                # Poll window events with 1ms timeout
                key_code = cv2.waitKeyEx(1)
                if key_code != -1:
                    mapped = self._map_key_code(key_code)
                    if mapped:
                        pressed_keys.append(mapped)
            except Exception as e:
                logger.warning(f"Native OpenCV window frame blit error; trying Tkinter: {e}")
                self.close()
                self._init_backend(allow_cv2=False)
                self.open(initial_size=(src_w, src_h))

        elif (
            self._backend == "tkinter" and self._tk_root is not None and self._tk_canvas is not None
        ):
            try:
                root = self._tk_root
                canvas = self._tk_canvas
                try:
                    if not root.winfo_exists():
                        self.is_open = False
                        return []
                except Exception:
                    self.is_open = False
                    return []

                self._last_image_size = (src_w, src_h)

                try:
                    win_w = canvas.winfo_width()
                    win_h = canvas.winfo_height()
                except Exception:
                    win_w, win_h = src_w, src_h

                if win_w <= 1 or win_h <= 1:
                    win_w, win_h = src_w, src_h

                scale = min(win_w / src_w, win_h / src_h)
                new_w = max(1, int(src_w * scale))
                new_h = max(1, int(src_h * scale))
                if (new_w, new_h) == (src_w, src_h):
                    scaled_img = render_img
                else:
                    scaled_img = render_img.resize((new_w, new_h), Image.Resampling.BILINEAR)

                photo = self._imagetk_module.PhotoImage(scaled_img)
                self._tk_photo_image = photo
                canvas.delete("all")
                canvas.create_image(win_w // 2, win_h // 2, image=photo, anchor="center")

                root.update_idletasks()
                root.update()

                if self._tk_pressed_keys:
                    pressed_keys.extend(self._tk_pressed_keys)
                    self._tk_pressed_keys.clear()
            except Exception as e:
                logger.debug(f"Native Tkinter window frame blit error: {e}")

        return pressed_keys

    def poll_events(self) -> list[str]:
        """Polls pending key events from the native window without rendering."""
        if not self.is_open:
            return []
        if self._backend == "cv2" and self._cv2_module is not None:
            try:
                cv2 = self._cv2_module
                try:
                    if cv2.getWindowProperty(self.title, cv2.WND_PROP_VISIBLE) < 1:
                        self.is_open = False
                        return []
                except Exception:
                    pass
                key_code = cv2.waitKeyEx(1)
                if key_code != -1:
                    mapped = self._map_key_code(key_code)
                    if mapped:
                        return [mapped]
            except Exception:
                pass
            return []
        elif self._backend == "tkinter" and self._tk_root is not None:
            try:
                if not self._tk_root.winfo_exists():
                    self.is_open = False
                    return []
                self._tk_root.update_idletasks()
                self._tk_root.update()
                if self._tk_pressed_keys:
                    keys = list(self._tk_pressed_keys)
                    self._tk_pressed_keys.clear()
                    return keys
            except Exception:
                pass
            return []
        return []

    def toggle_fullscreen(self) -> bool:
        """Toggles native window fullscreen."""
        if self._backend == "cv2" and self._cv2_module is not None and self.is_open:
            cv2 = self._cv2_module
            self.is_fullscreen = not self.is_fullscreen
            prop_val = cv2.WINDOW_FULLSCREEN if self.is_fullscreen else cv2.WINDOW_NORMAL
            cv2.setWindowProperty(self.title, cv2.WND_PROP_FULLSCREEN, prop_val)
            return self.is_fullscreen
        elif self._backend == "tkinter" and self._tk_root is not None and self.is_open:
            try:
                self.is_fullscreen = not self.is_fullscreen
                self._tk_root.attributes("-fullscreen", self.is_fullscreen)
                return self.is_fullscreen
            except Exception:
                pass
        return False

    def close(self) -> None:
        """Closes and releases the native GUI window."""
        if self.is_open:
            if self._backend == "cv2" and self._cv2_module is not None:
                with contextlib.suppress(Exception):
                    self._cv2_module.destroyWindow(self.title)
            elif self._backend == "tkinter" and self._tk_root is not None:
                with contextlib.suppress(Exception):
                    self._tk_root.destroy()
                self._tk_root = None
                self._tk_canvas = None
                self._tk_photo_image = None
                self._tk_pressed_keys.clear()
            self.is_open = False

    def _map_tk_key(self, event: Any) -> str | None:
        """Maps Tkinter key event to standard Pinak key names."""
        keysym = getattr(event, "keysym", "")
        char = getattr(event, "char", "")

        is_ctrl = bool(getattr(event, "state", 0) & 4)
        if keysym == "Escape":
            return "esc"
        if keysym in ("q", "Q") or char in ("q", "Q"):
            return "q"
        if is_ctrl and (
            keysym in ("m", "M", "Return", "KP_Enter") or char in ("m", "M", "\r", "\n")
        ):
            return "ctrl+m"
        if keysym == "space" or char == " ":
            return "space"
        if keysym in ("f", "F") or char in ("f", "F"):
            return "f"
        if keysym in ("m", "M") or char in ("m", "M"):
            return "m"
        if keysym in ("c", "C") or char in ("c", "C"):
            return "c"
        if keysym in ("r", "R") or char in ("r", "R"):
            return "r"
        if keysym in ("Left", "left"):
            return "left"
        if keysym in ("Right", "right"):
            return "right"
        if keysym in ("Up", "up"):
            return "up"
        if keysym in ("Down", "down"):
            return "down"
        if char and char.isalnum():
            return char.lower()
        return None

    def _map_key_code(self, code: int) -> str | None:
        """Maps platform-specific keycode to standard Pinak key names."""
        if code == 27:
            return "esc"
        if code in (ord("q"), ord("Q")):
            return "q"
        if code in (13, 10):  # Enter / Ctrl+M in OpenCV
            if os.name == "nt":
                try:
                    import ctypes

                    if (
                        hasattr(ctypes, "windll")
                        and hasattr(ctypes.windll, "user32")
                        and ctypes.windll.user32.GetAsyncKeyState(0x11) & 0x8000
                    ):
                        return "ctrl+m"
                except Exception:
                    pass
            return "enter"
        if code == 32:  # Space
            return "space"
        if code in (ord("f"), ord("F")):
            return "f"
        if code in (ord("m"), ord("M")):
            return "m"
        if code in (ord("c"), ord("C")):
            return "c"
        if code in (ord("r"), ord("R")):
            return "r"
        # Arrow keys in OpenCV Windows
        if code in (2424832, 65361):
            return "left"
        if code in (2555904, 2162688, 65363):
            return "right"
        if code in (2490368, 65362):
            return "up"
        if code in (2621440, 65364):
            return "down"
        if 0 <= code <= 0x10FFFF and chr(code).isalnum():
            return chr(code).lower()
        return None
