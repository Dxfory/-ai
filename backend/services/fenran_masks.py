"""Deterministic subject and background protection masks."""

from __future__ import annotations

from PIL import Image, ImageChops, ImageFilter, ImageOps


def build_subject_mask(registered_baimiao: Image.Image, registered_original: Image.Image) -> Image.Image:
    if registered_baimiao.size != registered_original.size:
        raise ValueError("registered baimiao and original must share canonical size")

    line_signal = ImageOps.invert(registered_baimiao.convert("L")).point(lambda value: 255 if value > 24 else 0)
    rgb = registered_original.convert("RGB")
    paper_color = _estimate_paper_color(rgb)
    channels = rgb.split()
    non_paper = Image.new("L", rgb.size, 0)
    output = non_paper.load()
    red, green, blue = (channel.load() for channel in channels)
    for y in range(rgb.height):
        for x in range(rgb.width):
            distance = (
                abs(paper_color[0] - red[x, y])
                + abs(paper_color[1] - green[x, y])
                + abs(paper_color[2] - blue[x, y])
            )
            output[x, y] = 255 if distance > 36 else 0

    combined = ImageChops.lighter(non_paper, line_signal)
    combined = combined.filter(ImageFilter.MaxFilter(7)).filter(ImageFilter.MaxFilter(7))
    combined = combined.filter(ImageFilter.GaussianBlur(2)).point(lambda value: 255 if value >= 32 else 0)
    return combined


def _estimate_paper_color(image: Image.Image) -> tuple[int, int, int]:
    margin = max(3, min(image.size) // 20)
    pixels = image.load()
    samples = []
    for x_range, y_range in (
        (range(margin), range(margin)),
        (range(image.width - margin, image.width), range(margin)),
        (range(margin), range(image.height - margin, image.height)),
        (range(image.width - margin, image.width), range(image.height - margin, image.height)),
    ):
        for x in x_range:
            for y in y_range:
                samples.append(pixels[x, y])
    channels = list(zip(*samples))
    return tuple(sorted(channel)[len(channel) // 2] for channel in channels)  # type: ignore[return-value]


def build_background_mask(subject_mask: Image.Image) -> Image.Image:
    return ImageOps.invert(subject_mask.convert("L"))


def composite_subject_only(
    generated_stage: Image.Image,
    previous_stage: Image.Image,
    subject_mask: Image.Image,
    *,
    feather_radius: int = 2,
) -> Image.Image:
    if generated_stage.size != previous_stage.size or subject_mask.size != previous_stage.size:
        raise ValueError("generated stage, previous stage, and subject mask must share canonical size")
    mask = subject_mask.convert("L")
    if feather_radius > 0:
        mask = mask.filter(ImageFilter.GaussianBlur(radius=min(3, feather_radius)))
    return Image.composite(generated_stage.convert("RGB"), previous_stage.convert("RGB"), mask)
