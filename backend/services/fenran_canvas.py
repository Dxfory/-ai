"""Canonical-to-provider canvas transforms for Fenran rendering."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from PIL import Image


@dataclass(frozen=True)
class FenranGenerationCanvas:
    request_size: str
    canvas_size: tuple[int, int]
    canonical_size: tuple[int, int]
    content_box: tuple[int, int, int, int]

    def to_dict(self) -> dict:
        payload = asdict(self)
        return {key: list(value) if isinstance(value, tuple) else value for key, value in payload.items()}


def _resolve_fenran_generation_canvas(
    canonical_size: tuple[int, int],
    *,
    image_size: str = "auto",
    max_side: int = 1536,
) -> FenranGenerationCanvas:
    width, height = canonical_size
    if width <= 0 or height <= 0:
        raise ValueError("canonical size must be positive")

    if image_size and image_size != "auto":
        try:
            canvas_size = tuple(int(part) for part in image_size.lower().split("x", 1))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Unsupported FENRAN_IMAGE_SIZE: {image_size}") from exc
        if len(canvas_size) != 2 or min(canvas_size) <= 0:
            raise ValueError(f"Unsupported FENRAN_IMAGE_SIZE: {image_size}")
        request_size = f"{canvas_size[0]}x{canvas_size[1]}"
    else:
        long_side = min(1536, max(1024, int(max_side)))
        short_side = min(1024, long_side)
        ratio = width / height
        if ratio > 1.2:
            canvas_size = (long_side, short_side)
        elif ratio < (1 / 1.2):
            canvas_size = (short_side, long_side)
        else:
            canvas_size = (short_side, short_side)
        request_size = f"{canvas_size[0]}x{canvas_size[1]}"

    canvas_width, canvas_height = canvas_size
    scale = min(canvas_width / width, canvas_height / height)
    content_width = max(1, min(canvas_width, round(width * scale)))
    content_height = max(1, min(canvas_height, round(height * scale)))
    left = (canvas_width - content_width) // 2
    top = (canvas_height - content_height) // 2
    content_box = (left, top, left + content_width, top + content_height)
    return FenranGenerationCanvas(request_size, canvas_size, canonical_size, content_box)


def _place_on_fenran_generation_canvas(
    image: Image.Image,
    canvas: FenranGenerationCanvas,
    *,
    resample: Image.Resampling = Image.Resampling.LANCZOS,
) -> Image.Image:
    if image.size != canvas.canonical_size:
        raise ValueError(f"image size {image.size} does not match canonical size {canvas.canonical_size}")
    left, top, right, bottom = canvas.content_box
    target_size = (right - left, bottom - top)
    mode = "L" if image.mode == "L" else "RGB"
    background = 255 if mode == "L" else (255, 255, 255)
    result = Image.new(mode, canvas.canvas_size, background)
    result.paste(image.convert(mode).resize(target_size, resample), (left, top))
    return result


def _restore_from_fenran_generation_canvas(
    image: Image.Image,
    canvas: FenranGenerationCanvas,
    *,
    resample: Image.Resampling = Image.Resampling.LANCZOS,
) -> Image.Image:
    if image.size != canvas.canvas_size:
        raise ValueError(f"provider image size {image.size} does not match request canvas {canvas.canvas_size}")
    restored = image.crop(canvas.content_box).resize(canvas.canonical_size, resample)
    if restored.size != canvas.canonical_size:
        raise ValueError("failed to restore canonical size")
    return restored

