"""Image loader supporting high-res static images, animated GIFs, EXIF rotation, and viewport cropping."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageOps, ImageSequence


@dataclass
class LoadedImage:
    """Represents an ingested image asset."""

    frames: list[Image.Image] = field(default_factory=list)
    durations: list[float] = field(default_factory=list)
    width: int = 0
    height: int = 0
    is_animated: bool = False

    def get_frame(self, elapsed_seconds: float) -> Image.Image:
        """Returns the appropriate frame for animated images based on elapsed time."""
        if not self.is_animated or not self.durations or len(self.frames) <= 1:
            return self.frames[0]

        total_duration = sum(self.durations)
        if total_duration <= 0:
            return self.frames[0]

        t = elapsed_seconds % total_duration
        cumulative = 0.0
        for idx, d in enumerate(self.durations):
            cumulative += d
            if t < cumulative:
                return self.frames[idx]
        return self.frames[-1]


class ImageLoader:
    MAX_CANVAS_DIMENSION: int = 4096  # Max dimension for RAM safety on gigapixel images
    MAX_SAFE_IMAGE_PIXELS: int = 128_000_000  # Strict 128 Megapixel ceiling against DoS bombs
    MAX_DECODED_BYTES: int = 128 * 1024 * 1024
    MAX_FRAMES: int = 256

    @classmethod
    def create_placeholder(
        cls, message: str = "Image Unavailable", width: int = 640, height: int = 480
    ) -> LoadedImage:
        """Generates a clean fallback image card with informational message."""
        from PIL import ImageDraw

        img = Image.new("RGB", (width, height), (26, 32, 44))
        draw = ImageDraw.Draw(img)
        draw.rectangle([4, 4, width - 5, height - 5], outline=(70, 90, 130), width=2)
        draw.text((width // 2, height // 2), message, fill=(200, 220, 245), anchor="mm")
        return LoadedImage(
            frames=[img],
            durations=[1.0],
            width=width,
            height=height,
            is_animated=False,
        )

    @classmethod
    def load(cls, file_path: str | Path) -> LoadedImage:
        path = Path(file_path).resolve()
        try:
            with Image.open(path) as raw_img:
                w, h = raw_img.size
                if w * h > cls.MAX_SAFE_IMAGE_PIXELS:
                    raise Image.DecompressionBombError("Image exceeds the pixel budget")
                # draft is metadata-only for JPEG; never decode/copy a giant source
                # merely to make a small thumbnail.
                if w * h * 8 > cls.MAX_DECODED_BYTES:
                    raw_img.draft("RGB", (cls.MAX_CANVAS_DIMENSION, cls.MAX_CANVAS_DIMENSION))
                    if raw_img.width * raw_img.height * 8 > cls.MAX_DECODED_BYTES:
                        raise Image.DecompressionBombError("Image exceeds the memory budget")
                return cls._extract_frames(raw_img)
        except (Image.DecompressionBombError, MemoryError):
            # Enforce strict upper memory ceiling to prevent OOM panics on decompression bombs
            return cls.create_placeholder(f"Decompression Bomb Blocked: {path.name}", 640, 480)
        except Exception:
            return cls.create_placeholder(f"Image Unavailable: {path.name}", 640, 480)

    @classmethod
    def _prepare_base_image(cls, raw_img: Image.Image) -> Image.Image:
        """Handles EXIF orientation and downsamples gigapixel images."""
        transposed = ImageOps.exif_transpose(raw_img)
        base = transposed if transposed is not None else raw_img
        w, h = base.size
        if w > cls.MAX_CANVAS_DIMENSION or h > cls.MAX_CANVAS_DIMENSION:
            scale = min(
                cls.MAX_CANVAS_DIMENSION / max(1, w),
                cls.MAX_CANVAS_DIMENSION / max(1, h),
            )
            safe_w, safe_h = max(1, int(w * scale)), max(1, int(h * scale))
            return base.resize((safe_w, safe_h), Image.Resampling.LANCZOS)
        return base

    @classmethod
    def _extract_frames(cls, base_img: Image.Image) -> LoadedImage:
        """Extracts individual frames and durations from static or animated image."""
        frames: list[Image.Image] = []
        durations: list[float] = []

        is_animated = getattr(base_img, "is_animated", False)
        if is_animated:
            total_bytes = 0
            for frame in ImageSequence.Iterator(base_img):
                prepared = cls._prepare_base_image(frame).convert("RGB")
                total_bytes += prepared.width * prepared.height * 3
                if len(frames) >= cls.MAX_FRAMES or total_bytes > cls.MAX_DECODED_BYTES:
                    raise Image.DecompressionBombError("Animation exceeds the memory budget")
                dur_ms = frame.info.get("duration", 100)
                durations.append(max(0.02, dur_ms / 1000.0))
                frames.append(prepared)
        else:
            frames.append(cls._prepare_base_image(base_img).convert("RGB"))
            durations.append(1.0)

        w, h = frames[0].size
        return LoadedImage(
            frames=frames,
            durations=durations,
            width=w,
            height=h,
            is_animated=is_animated,
        )

    @classmethod
    def crop_and_scale(
        cls,
        img: Image.Image,
        target_w: int,
        target_h: int,
        zoom: float = 1.0,
        pan_x: float = 0.0,
        pan_y: float = 0.0,
        rotation_deg: int = 0,
    ) -> Image.Image:
        """
        Applies rotation, center-anchored zoom, pan offsets, and scales to target pixel dimensions.
        """
        # 1. Apply lossless 90° rotation
        rot = rotation_deg % 360
        if rot == 90:
            current = img.transpose(Image.Transpose.ROTATE_270)
        elif rot == 180:
            current = img.transpose(Image.Transpose.ROTATE_180)
        elif rot == 270:
            current = img.transpose(Image.Transpose.ROTATE_90)
        else:
            current = img

        src_w, src_h = current.size
        z = max(0.1, min(10.0, zoom))

        if abs(z - 1.0) < 1e-3 and abs(pan_x) < 1e-3 and abs(pan_y) < 1e-3:
            if target_w <= 0 or target_h <= 0 or (src_w == target_w and src_h == target_h):
                return current
            return current.resize((target_w, target_h), Image.Resampling.LANCZOS)

        # 2. Compute cropped viewport in source image space
        visible_w = src_w / z
        visible_h = src_h / z

        center_x = (src_w / 2.0) - (pan_x / z)
        center_y = (src_h / 2.0) - (pan_y / z)

        left = max(0.0, center_x - (visible_w / 2.0))
        top = max(0.0, center_y - (visible_h / 2.0))
        right = min(float(src_w), left + visible_w)
        bottom = min(float(src_h), top + visible_h)

        # Ensure valid non-empty box
        if right <= left:
            left, right = 0.0, float(src_w)
        if bottom <= top:
            top, bottom = 0.0, float(src_h)

        cropped = current.crop((int(left), int(top), int(right), int(bottom)))

        # 3. Scale to target viewport dimensions
        if target_w <= 0 or target_h <= 0:
            return cropped

        return cropped.resize((target_w, target_h), Image.Resampling.LANCZOS)
