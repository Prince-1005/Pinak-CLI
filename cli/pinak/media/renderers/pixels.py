"""Typed RGB pixel access after Pillow mode validation."""

from __future__ import annotations

from typing import Protocol, cast

from PIL import Image


class RGBPixels(Protocol):
    def __getitem__(self, position: tuple[int, int]) -> tuple[int, int, int]: ...
    def __setitem__(self, position: tuple[int, int], value: tuple[int, int, int]) -> None: ...


def rgb_pixels(image: Image.Image) -> RGBPixels:
    if image.mode != "RGB":
        raise ValueError("RGB pixel access requires an RGB image")
    pixels = image.load()
    if pixels is None:
        raise ValueError("Image has no pixel buffer")
    return cast(RGBPixels, pixels)
