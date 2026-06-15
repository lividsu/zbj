"""Utilities for keeping edited images aligned with their source dimensions."""

from io import BytesIO
import math
from pathlib import Path
from typing import Tuple

from PIL import Image, ImageOps


STANDARD_ASPECT_RATIOS = (
    ("1:1", 1 / 1),
    ("2:3", 2 / 3),
    ("3:2", 3 / 2),
    ("3:4", 3 / 4),
    ("4:3", 4 / 3),
    ("4:5", 4 / 5),
    ("5:4", 5 / 4),
    ("9:16", 9 / 16),
    ("16:9", 16 / 9),
    ("21:9", 21 / 9),
)

EXTREME_ASPECT_RATIOS = (
    ("1:4", 1 / 4),
    ("1:8", 1 / 8),
    ("4:1", 4 / 1),
    ("8:1", 8 / 1),
)


def get_display_size(image_path: str) -> Tuple[int, int]:
    """Return image dimensions after applying EXIF orientation."""
    with Image.open(image_path) as image:
        return ImageOps.exif_transpose(image).size


def closest_supported_aspect_ratio(
    width: int,
    height: int,
    allow_extreme: bool = False,
) -> str:
    """Choose the model aspect ratio closest to the source image."""
    if width <= 0 or height <= 0:
        raise ValueError("Image dimensions must be positive")

    actual_ratio = width / height
    supported_ratios = STANDARD_ASPECT_RATIOS
    if allow_extreme:
        supported_ratios += EXTREME_ASPECT_RATIOS
    return min(
        supported_ratios,
        key=lambda item: abs(math.log(actual_ratio / item[1])),
    )[0]


def recommended_image_size(width: int, height: int) -> str:
    """Request enough model resolution to avoid unnecessary upscaling."""
    longest_edge = max(width, height)
    if longest_edge <= 1024:
        return "1K"
    if longest_edge <= 2048:
        return "2K"
    return "4K"


def restore_source_dimensions(
    image_bytes: bytes,
    source_image_path: str,
) -> tuple[bytes, Tuple[int, int], Tuple[int, int]]:
    """Resize generated image bytes to the source image's exact dimensions."""
    source_path = Path(source_image_path)
    if not source_path.is_file():
        raise FileNotFoundError(f"Source image does not exist: {source_image_path}")

    with Image.open(source_path) as source:
        source = ImageOps.exif_transpose(source)
        target_size = source.size
        source_dpi = source.info.get("dpi")

    with Image.open(BytesIO(image_bytes)) as generated:
        generated = ImageOps.exif_transpose(generated)
        generated.load()
        generated_size = generated.size

        if generated_size != target_size:
            generated = generated.resize(target_size, Image.Resampling.LANCZOS)

        output = BytesIO()
        save_options = {"format": "PNG"}
        if source_dpi:
            save_options["dpi"] = source_dpi
        generated.save(output, **save_options)

    return output.getvalue(), target_size, generated_size
