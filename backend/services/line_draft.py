"""白描线稿生成服务"""

import base64
import os
from dataclasses import dataclass
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFilter, ImageOps

from .baimiao_knowledge import BAIMIAO_PROMPT


@dataclass
class LineDraftResult:
    output_path: str
    width: int
    height: int
    parameters: dict


@dataclass
class GenerationCanvas:
    request_size: str
    canvas_size: tuple[int, int]
    source_size: tuple[int, int]
    content_box: tuple[int, int, int, int]
    preserve_source_aspect: bool


@dataclass
class BBoxStats:
    bbox: tuple[int, int, int, int] | None
    size: tuple[int, int]
    center: tuple[float, float] | None
    coverage: float
    ratio: float | None


def generate_line_draft(
    source_path: str,
    output_dir: str,
    draft_id: str,
    line_strength: int = 3,
    detail_level: int = 3,
    preserve_texture: bool = True,
) -> LineDraftResult:
    """从用户上传图生成黑线白底白描稿。

    第一版强调稳定和可调，不冒充最终模型：通过灰度、自动对比度、
    边缘提取、阈值化和线条加深得到可打印的临摹底稿。
    """
    os.makedirs(output_dir, exist_ok=True)
    img = Image.open(source_path).convert("RGB")
    img.thumbnail((1800, 1800), Image.Resampling.LANCZOS)
    gray = ImageOps.grayscale(img)
    gray = ImageOps.autocontrast(gray)

    if preserve_texture:
        gray = gray.filter(ImageFilter.UnsharpMask(radius=1.4, percent=140, threshold=3))
    else:
        gray = gray.filter(ImageFilter.MedianFilter(size=3))

    edges = gray.filter(ImageFilter.FIND_EDGES)
    edges = ImageOps.autocontrast(edges)
    draft = ImageOps.invert(edges)

    threshold = max(90, min(245, 235 - detail_level * 24 + line_strength * 7))
    pixels = draft.load()
    width, height = draft.size
    for y in range(height):
        for x in range(width):
            value = pixels[x, y]
            pixels[x, y] = 0 if value < threshold else 255

    if line_strength >= 4:
        draft = draft.filter(ImageFilter.MinFilter(size=3))
    if line_strength <= 2:
        draft = draft.filter(ImageFilter.MaxFilter(size=3))

    out_path = Path(output_dir) / f"{draft_id}.png"
    draft.save(out_path)
    return LineDraftResult(
        output_path=str(out_path),
        width=width,
        height=height,
        parameters={
            "line_strength": line_strength,
            "detail_level": detail_level,
            "preserve_texture": preserve_texture,
            "threshold": threshold,
        },
    )


def generate_ai_baimiao(
    source_path: str,
    output_dir: str,
    draft_id: str,
    prompt: str = "",
) -> LineDraftResult:
    """通过 OpenAI Images 兼容接口生成真正的 AI 白描稿。"""
    api_key = os.getenv("BAIMIAO_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing BAIMIAO_API_KEY or OPENAI_API_KEY")

    base_url = (
        os.getenv("BAIMIAO_API_BASE")
        or os.getenv("OPENAI_BASE_URL")
        or os.getenv("OPENAI_API_BASE")
        or "https://api.openai.com/v1"
    ).rstrip("/")
    if not base_url.endswith("/v1"):
        base_url = f"{base_url}/v1"

    model = os.getenv("BAIMIAO_IMAGE_MODEL", "gpt-image-1")
    final_prompt = prompt.strip() or BAIMIAO_PROMPT
    url = f"{base_url}/images/edits"
    headers = {"Authorization": f"Bearer {api_key}"}
    canvas = _resolve_generation_canvas(source_path)
    data = {
        "model": model,
        "prompt": final_prompt,
        "size": canvas.request_size,
    }

    os.makedirs(output_dir, exist_ok=True)
    output_path = Path(output_dir) / f"{draft_id}.png"
    raw_output_path = Path(output_dir) / f"{draft_id}_raw.png"
    api_input_path = Path(output_dir) / f"{draft_id}_api_input.jpg"
    guide_path = Path(output_dir) / f"{draft_id}_structure_guide.png"
    _prepare_api_image(source_path, str(api_input_path), canvas=canvas)
    _make_baimiao_structure_guide(source_path, str(guide_path), canvas=canvas)

    guide_used = False
    with httpx.Client(timeout=_image_timeout_seconds()) as client:
        payload, guide_used = _post_baimiao_edit(
            client=client,
            url=url,
            headers=headers,
            data=data,
            source_path=str(api_input_path),
            guide_path=str(guide_path),
        )

        image_data = payload.get("data", [{}])[0]
        if image_data.get("b64_json"):
            raw_output_path.write_bytes(base64.b64decode(image_data["b64_json"]))
        elif image_data.get("url"):
            image_response = client.get(image_data["url"])
            image_response.raise_for_status()
            raw_output_path.write_bytes(image_response.content)
        else:
            raise RuntimeError("Image API did not return b64_json or url")

    api_input_stats = _line_art_bbox_stats(str(api_input_path))
    guide_stats = _line_art_bbox_stats(str(guide_path))
    raw_stats = _line_art_bbox_stats(str(raw_output_path))
    _clean_ai_line_art(
        str(raw_output_path),
        str(output_path),
        original_path=str(api_input_path),
        canvas=canvas,
    )
    final_stats = _line_art_bbox_stats(str(output_path))
    composition_delta = _composition_delta(guide_stats, raw_stats)
    composition_warning = _composition_warning(composition_delta)
    with Image.open(output_path) as img:
        width, height = img.size
    repair_lines = _env_flag("BAIMIAO_REPAIR_LINES", True)
    clip_to_border = _env_flag("BAIMIAO_CLIP_TO_BORDER", True)
    clean_output = _env_flag("BAIMIAO_CLEAN_OUTPUT", True)
    smooth_junctions = _env_flag("BAIMIAO_SMOOTH_JUNCTIONS", True)
    return LineDraftResult(
        output_path=str(output_path),
        width=width,
        height=height,
        parameters={
            "provider": "ai_baimiao",
            "model": model,
            "base_url": base_url,
            "size": data["size"],
            "source_size": list(canvas.source_size),
            "api_canvas_size": list(canvas.canvas_size),
            "content_box": list(canvas.content_box),
            "prompt": final_prompt,
            "api_input_path": str(api_input_path),
            "raw_output_path": str(raw_output_path),
            "structure_guide_path": str(guide_path),
            "structure_guide_requested": _use_structure_guide(),
            "structure_guide_used": guide_used,
            "cleaned": clean_output,
            "clip_to_border": clip_to_border,
            "aspect_restored": canvas.preserve_source_aspect,
            "line_repaired": clean_output and repair_lines,
            "line_repair_max_gap": _line_repair_max_gap() if repair_lines else 0,
            "junctions_smoothed": clean_output and smooth_junctions,
            "max_junction_thickness": _max_junction_thickness() if smooth_junctions else 0,
            "api_input_bbox": _bbox_stats_to_dict(api_input_stats),
            "guide_bbox": _bbox_stats_to_dict(guide_stats),
            "raw_bbox": _bbox_stats_to_dict(raw_stats),
            "final_bbox": _bbox_stats_to_dict(final_stats),
            "composition_delta": composition_delta,
            "composition_warning": composition_warning,
        },
    )


def generate_overlay(reference_path: str, submission_path: str, output_path: str) -> dict:
    """生成参考图与用户作业的透明叠图。"""
    reference = Image.open(reference_path).convert("RGBA")
    submission = Image.open(submission_path).convert("RGBA")
    submission = ImageOps.contain(submission, reference.size, Image.Resampling.LANCZOS)

    canvas = Image.new("RGBA", reference.size, (255, 255, 255, 255))
    offset = (
        (reference.width - submission.width) // 2,
        (reference.height - submission.height) // 2,
    )

    ref_layer = reference.copy()
    ref_layer.putalpha(150)
    sub_layer = Image.new("RGBA", reference.size, (255, 255, 255, 0))
    sub_layer.alpha_composite(submission, offset)
    sub_layer.putalpha(135)

    canvas.alpha_composite(ref_layer)
    canvas.alpha_composite(sub_layer)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    canvas.convert("RGB").save(output_path)
    return {
        "reference_size": [reference.width, reference.height],
        "submission_size": [submission.width, submission.height],
        "offset": [offset[0], offset[1]],
    }


def _guess_mime(path: str) -> str:
    ext = path.rsplit(".", 1)[-1].lower()
    if ext in {"jpg", "jpeg"}:
        return "image/jpeg"
    if ext == "webp":
        return "image/webp"
    return "image/png"


def _resolve_image_size(source_path: str) -> str:
    requested = os.getenv("BAIMIAO_IMAGE_SIZE", "auto").strip()
    if requested and requested.lower() != "auto":
        return requested
    with Image.open(source_path) as img:
        width, height = img.size
    ratio = width / max(1, height)
    if ratio >= 1.05:
        return "1536x1024"
    if ratio <= 0.95:
        return "1024x1536"
    return "1024x1024"


def _resolve_generation_canvas(source_path: str) -> GenerationCanvas:
    request_size = _resolve_image_size(source_path)
    canvas_size = _parse_image_size(request_size)
    with ImageOps.exif_transpose(Image.open(source_path)) as img:
        source_size = img.size

    preserve_source_aspect = _env_flag("BAIMIAO_PRESERVE_SOURCE_ASPECT", True)
    if not preserve_source_aspect:
        return GenerationCanvas(
            request_size=request_size,
            canvas_size=canvas_size,
            source_size=source_size,
            content_box=(0, 0, canvas_size[0], canvas_size[1]),
            preserve_source_aspect=False,
        )

    content_width, content_height = _contain_size(source_size, canvas_size)
    left = (canvas_size[0] - content_width) // 2
    top = (canvas_size[1] - content_height) // 2
    return GenerationCanvas(
        request_size=request_size,
        canvas_size=canvas_size,
        source_size=source_size,
        content_box=(left, top, left + content_width, top + content_height),
        preserve_source_aspect=True,
    )


def _parse_image_size(size: str) -> tuple[int, int]:
    try:
        width_text, height_text = size.lower().split("x", 1)
        width = int(width_text)
        height = int(height_text)
    except (ValueError, AttributeError) as exc:
        raise ValueError(f"Unsupported BAIMIAO_IMAGE_SIZE: {size}") from exc
    if width <= 0 or height <= 0:
        raise ValueError(f"Unsupported BAIMIAO_IMAGE_SIZE: {size}")
    return width, height


def _contain_size(source_size: tuple[int, int], target_size: tuple[int, int]) -> tuple[int, int]:
    source_width, source_height = source_size
    target_width, target_height = target_size
    scale = min(target_width / max(1, source_width), target_height / max(1, source_height))
    width = max(1, round(source_width * scale))
    height = max(1, round(source_height * scale))
    return width, height


def _image_timeout_seconds() -> float:
    return float(os.getenv("BAIMIAO_IMAGE_TIMEOUT_SECONDS", "240"))


def _prepare_api_image(source_path: str, output_path: str, canvas: GenerationCanvas | None = None) -> None:
    img = ImageOps.exif_transpose(Image.open(source_path)).convert("RGB")
    if canvas and canvas.preserve_source_aspect:
        img = _place_on_generation_canvas(img, canvas)
    else:
        max_side = int(os.getenv("BAIMIAO_API_MAX_IMAGE_SIDE", "1024"))
        img.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    suffix = Path(output_path).suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        img.save(output_path, quality=92, optimize=True)
    else:
        img.save(output_path)


def _post_baimiao_edit(
    client: httpx.Client,
    url: str,
    headers: dict,
    data: dict,
    source_path: str,
    guide_path: str,
) -> tuple[dict, bool]:
    try:
        response, guide_used = _post_baimiao_edit_without_status_check(
            client=client,
            url=url,
            headers=headers,
            data=data,
            source_path=source_path,
            guide_path=guide_path,
        )
        response.raise_for_status()
        return response.json(), guide_used
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(_format_image_api_error(exc.response)) from exc
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Image API request failed: {exc}") from exc


def _post_baimiao_edit_without_status_check(
    client: httpx.Client,
    url: str,
    headers: dict,
    data: dict,
    source_path: str,
    guide_path: str,
) -> tuple[httpx.Response, bool]:
    if not _use_structure_guide():
        return _post_single_image_edit(client, url, headers, data, source_path), False

    try:
        with open(source_path, "rb") as source_file, open(guide_path, "rb") as guide_file:
            files = [
                ("image", (Path(source_path).name, source_file, _guess_mime(source_path))),
                ("image", (Path(guide_path).name, guide_file, "image/png")),
            ]
            response = client.post(url, headers=headers, data=data, files=files)
    except httpx.HTTPError:
        return _post_single_image_edit(client, url, headers, data, source_path), False
    if response.status_code in {400, 413, 415, 422}:
        return _post_single_image_edit(client, url, headers, data, source_path), False
    return response, True


def _post_single_image_edit(
    client: httpx.Client,
    url: str,
    headers: dict,
    data: dict,
    source_path: str,
) -> httpx.Response:
    attempts = max(1, int(os.getenv("BAIMIAO_API_RETRIES", "2")))
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            with open(source_path, "rb") as source_file:
                files = {"image": (Path(source_path).name, source_file, _guess_mime(source_path))}
                response = client.post(url, headers=headers, data=data, files=files)
            if response.status_code not in {500, 502, 503, 504, 524} or attempt == attempts - 1:
                return response
        except httpx.HTTPError as exc:
            last_error = exc
            if attempt == attempts - 1:
                raise
    if last_error:
        raise last_error
    raise RuntimeError("Image API request failed without a response")


def _place_on_generation_canvas(img: Image.Image, canvas: GenerationCanvas) -> Image.Image:
    source = img.convert("RGB")
    target = Image.new("RGB", canvas.canvas_size, "white")
    left, top, right, bottom = canvas.content_box
    resized = source.resize((right - left, bottom - top), Image.Resampling.LANCZOS)
    target.paste(resized, (left, top))
    return target


def _make_baimiao_structure_guide(
    source_path: str,
    output_path: str,
    canvas: GenerationCanvas | None = None,
) -> None:
    img = ImageOps.exif_transpose(Image.open(source_path)).convert("RGB")
    if canvas and canvas.preserve_source_aspect:
        img = _place_on_generation_canvas(img, canvas)
    else:
        img.thumbnail((1536, 1536), Image.Resampling.LANCZOS)
    gray = ImageOps.grayscale(img)
    gray = ImageOps.autocontrast(gray)
    smooth = gray.filter(ImageFilter.MedianFilter(size=3))
    edges = smooth.filter(ImageFilter.FIND_EDGES)
    edges = ImageOps.autocontrast(edges)
    guide = ImageOps.invert(edges)
    guide = guide.point(lambda value: 0 if value < 210 else 255)
    guide = guide.filter(ImageFilter.MinFilter(size=3))
    guide = _remove_tiny_specks(guide)
    artwork_mask = _detect_artwork_region_mask(img)
    if artwork_mask:
        guide = guide.convert("L")
        guide = _clear_outside_artwork_mask(guide, artwork_mask)
        guide.paste(0, mask=_mask_outline(artwork_mask))
    guide.save(output_path)


def _clean_ai_line_art(
    source_path: str,
    output_path: str,
    original_path: str | None = None,
    canvas: GenerationCanvas | None = None,
) -> None:
    if not _env_flag("BAIMIAO_CLEAN_OUTPUT", True):
        clean = Image.open(source_path).convert("L")
        clean = _restore_source_aspect(clean, canvas)
        clean.save(output_path)
        return

    threshold = int(os.getenv("BAIMIAO_CLEAN_THRESHOLD", "225"))
    blur_radius = int(os.getenv("BAIMIAO_BACKGROUND_BLUR", "31"))
    img = Image.open(source_path).convert("L")
    background = img.filter(ImageFilter.GaussianBlur(radius=blur_radius))
    source_pixels = img.load()
    background_pixels = background.load()
    width, height = img.size
    clean = Image.new("L", img.size, 255)
    clean_pixels = clean.load()
    for y in range(height):
        for x in range(width):
            normalized = min(255, int(source_pixels[x, y] * 255 / max(1, background_pixels[x, y])))
            clean_pixels[x, y] = 0 if normalized < threshold else 255
    if os.getenv("BAIMIAO_SOLIDIFY_LINES", "false").lower() in {"1", "true", "yes"}:
        clean = _solidify_line_art(clean)
    if _env_flag("BAIMIAO_REPAIR_LINES", True):
        clean = _repair_short_line_gaps(clean, _line_repair_max_gap())
    if _env_flag("BAIMIAO_SMOOTH_JUNCTIONS", True):
        clean = _smooth_junction_blobs(clean, _max_junction_thickness())
    if original_path and _env_flag("BAIMIAO_CLIP_TO_BORDER", True):
        clean = _restore_round_border_from_original(clean, original_path)
    clean = _restore_source_aspect(clean, canvas)
    clean = clean.point(lambda value: 0 if value < 128 else 255)
    clean.save(output_path)


def _restore_source_aspect(img: Image.Image, canvas: GenerationCanvas | None) -> Image.Image:
    if not canvas or not canvas.preserve_source_aspect:
        return img
    width, height = img.size
    canvas_width, canvas_height = canvas.canvas_size
    left, top, right, bottom = canvas.content_box
    scaled_box = (
        max(0, min(width - 1, round(left * width / canvas_width))),
        max(0, min(height - 1, round(top * height / canvas_height))),
        max(1, min(width, round(right * width / canvas_width))),
        max(1, min(height, round(bottom * height / canvas_height))),
    )
    if scaled_box[2] <= scaled_box[0] or scaled_box[3] <= scaled_box[1]:
        return img.resize(canvas.source_size, Image.Resampling.LANCZOS)
    cropped = img.crop(scaled_box)
    if cropped.size == canvas.source_size:
        return cropped
    return cropped.resize(canvas.source_size, Image.Resampling.LANCZOS)


def _repair_short_line_gaps(img: Image.Image, max_gap: int) -> Image.Image:
    max_gap = max(0, min(6, max_gap))
    if max_gap <= 0:
        return img.convert("L")

    source = img.convert("L").point(lambda value: 0 if value < 128 else 255)
    pixels = source.load()
    width, height = source.size
    additions: set[tuple[int, int]] = set()
    directions = ((1, 0), (0, 1), (1, 1), (1, -1))

    for y in range(height):
        for x in range(width):
            if pixels[x, y] != 0:
                continue
            for dx, dy in directions:
                for gap in range(1, max_gap + 1):
                    end_x = x + dx * (gap + 1)
                    end_y = y + dy * (gap + 1)
                    if end_x < 0 or end_x >= width or end_y < 0 or end_y >= height:
                        break
                    if pixels[end_x, end_y] != 0:
                        continue
                    between: list[tuple[int, int]] = []
                    clear = True
                    for step in range(1, gap + 1):
                        mid_x = x + dx * step
                        mid_y = y + dy * step
                        if pixels[mid_x, mid_y] == 0:
                            clear = False
                            break
                        between.append((mid_x, mid_y))
                    if clear:
                        additions.update(between)
                    break

    result = source.copy()
    result_pixels = result.load()
    for x, y in additions:
        result_pixels[x, y] = 0
    return result


def _line_repair_max_gap() -> int:
    return max(0, int(os.getenv("BAIMIAO_LINE_REPAIR_MAX_GAP", "3")))


def _max_junction_thickness() -> int:
    return max(1, int(os.getenv("BAIMIAO_MAX_JUNCTION_THICKNESS", "3")))


def _use_structure_guide() -> bool:
    return _env_flag("BAIMIAO_USE_STRUCTURE_GUIDE", True)


def _env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _line_art_bbox_stats(path: str | Path, threshold: int = 245) -> BBoxStats:
    return _image_bbox_stats(Image.open(path).convert("L"), threshold=threshold)


def _image_bbox_stats(img: Image.Image, threshold: int = 245) -> BBoxStats:
    source = img.convert("L")
    width, height = source.size
    pixels = source.load()
    left = width
    top = height
    right = -1
    bottom = -1
    count = 0
    for y in range(height):
        for x in range(width):
            if pixels[x, y] < threshold:
                count += 1
                left = min(left, x)
                top = min(top, y)
                right = max(right, x)
                bottom = max(bottom, y)
    if right < left or bottom < top:
        return BBoxStats(bbox=None, size=(width, height), center=None, coverage=0.0, ratio=None)

    bbox = (left, top, right + 1, bottom + 1)
    bbox_width = bbox[2] - bbox[0]
    bbox_height = bbox[3] - bbox[1]
    center = ((bbox[0] + bbox[2]) / 2 / width, (bbox[1] + bbox[3]) / 2 / height)
    coverage = (bbox_width * bbox_height) / max(1, width * height)
    ratio = bbox_width / max(1, bbox_height)
    return BBoxStats(bbox=bbox, size=(width, height), center=center, coverage=coverage, ratio=ratio)


def _bbox_stats_to_dict(stats: BBoxStats) -> dict:
    return {
        "bbox": list(stats.bbox) if stats.bbox else None,
        "size": list(stats.size),
        "center": [round(stats.center[0], 5), round(stats.center[1], 5)] if stats.center else None,
        "coverage": round(stats.coverage, 6),
        "ratio": round(stats.ratio, 6) if stats.ratio is not None else None,
    }


def _composition_delta(reference: BBoxStats, candidate: BBoxStats) -> dict:
    if not reference.bbox or not candidate.bbox or not reference.center or not candidate.center:
        return {
            "ratio_delta": None,
            "center_delta": None,
            "coverage_delta": None,
        }
    ratio_delta = abs((candidate.ratio or 0) - (reference.ratio or 0)) / max(0.001, reference.ratio or 0)
    center_delta = max(
        abs(candidate.center[0] - reference.center[0]),
        abs(candidate.center[1] - reference.center[1]),
    )
    coverage_delta = abs(candidate.coverage - reference.coverage) / max(0.001, reference.coverage)
    return {
        "ratio_delta": round(ratio_delta, 6),
        "center_delta": round(center_delta, 6),
        "coverage_delta": round(coverage_delta, 6),
    }


def _composition_warning(delta: dict) -> bool:
    ratio_delta = delta.get("ratio_delta")
    center_delta = delta.get("center_delta")
    coverage_delta = delta.get("coverage_delta")
    if ratio_delta is None or center_delta is None or coverage_delta is None:
        return True
    return bool(ratio_delta > 0.04 or center_delta > 0.03 or coverage_delta > 0.05)


def _smooth_junction_blobs(img: Image.Image, max_thickness: int) -> Image.Image:
    clean = img.convert("L").point(lambda value: 0 if value < 128 else 255)
    width, height = clean.size
    pixels = clean.load()
    result = clean.copy()
    result_pixels = result.load()
    max_thickness = max(1, min(7, max_thickness))
    required_black = 8 if max_thickness <= 3 else 7
    corner_offsets = ((-1, -1), (1, -1), (-1, 1), (1, 1))

    for y in range(1, height - 1):
        for x in range(1, width - 1):
            black_count = 0
            for ny in range(y - 1, y + 2):
                for nx in range(x - 1, x + 2):
                    if pixels[nx, ny] == 0:
                        black_count += 1
            if black_count < required_black:
                continue
            for dx, dy in corner_offsets:
                cx = x + dx
                cy = y + dy
                if pixels[cx, cy] != 0:
                    continue
                horizontal = pixels[cx - dx, cy] == 0 and 0 <= cx + dx < width and pixels[cx + dx, cy] == 0
                vertical = pixels[cx, cy - dy] == 0 and 0 <= cy + dy < height and pixels[cx, cy + dy] == 0
                if not horizontal and not vertical:
                    result_pixels[cx, cy] = 255
    return result


def _solidify_line_art(img: Image.Image) -> Image.Image:
    clean = img.convert("L")
    black = ImageOps.invert(clean)
    black = black.filter(ImageFilter.MaxFilter(size=3))
    return ImageOps.invert(black).point(lambda value: 0 if value < 235 else 255)


def _remove_tiny_specks(img: Image.Image) -> Image.Image:
    filtered = img.convert("L").filter(ImageFilter.MedianFilter(size=3))
    return filtered.point(lambda value: 0 if value < 128 else 255)


def _restore_round_border_from_original(clean: Image.Image, original_path: str) -> Image.Image:
    original = Image.open(original_path).convert("RGB").resize(clean.size, Image.Resampling.LANCZOS)
    artwork_mask = _detect_artwork_region_mask(original)
    if not artwork_mask:
        return clean

    result = clean.convert("L")
    result = _clear_outside_artwork_mask(result, artwork_mask)
    result.paste(0, mask=_mask_outline(artwork_mask))
    return result


def _clear_outside_artwork_mask(img: Image.Image, mask: Image.Image) -> Image.Image:
    result = img.convert("L")
    inner_mask = mask.convert("L").filter(ImageFilter.MinFilter(size=3))
    white = Image.new("L", result.size, 255)
    white.paste(result, mask=inner_mask)
    return white


def _detect_artwork_region_mask(img: Image.Image) -> Image.Image | None:
    original_size = img.size
    rgb = img.convert("RGB")
    max_side = 512
    if max(rgb.size) > max_side:
        rgb.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    width, height = rgb.size
    component_mask = _largest_warm_artwork_component(rgb)
    if not component_mask:
        return None

    pixels = component_mask.load()
    min_row_pixels = max(6, round(width * 0.02))
    row_spans: list[tuple[int, int, int]] = []
    for y in range(height):
        xs: list[int] = []
        for x in range(width):
            if pixels[x, y]:
                xs.append(x)
        if len(xs) >= min_row_pixels:
            left_index = max(0, round(len(xs) * 0.01) - 1)
            right_index = min(len(xs) - 1, round(len(xs) * 0.99))
            row_spans.append((y, xs[left_index], xs[right_index]))
    if len(row_spans) < max(20, height * 0.2):
        return None

    top = row_spans[0][0]
    bottom = row_spans[-1][0]
    left = min(span[1] for span in row_spans)
    right = max(span[2] for span in row_spans)
    box_w = right - left + 1
    box_h = bottom - top + 1
    if box_w < width * 0.55 or box_h < height * 0.55:
        return None

    mask = Image.new("L", rgb.size, 0)
    draw = ImageDraw.Draw(mask)
    smooth_window = max(3, round(height * 0.008))
    if smooth_window % 2 == 0:
        smooth_window += 1
    half = smooth_window // 2
    for index, (y, _, _) in enumerate(row_spans):
        window = row_spans[max(0, index - half): min(len(row_spans), index + half + 1)]
        smoothed_left = sorted(span[1] for span in window)[len(window) // 2]
        smoothed_right = sorted(span[2] for span in window)[len(window) // 2]
        draw.line((smoothed_left, y, smoothed_right, y), fill=255)
    blur_radius = max(1.0, min(width, height) / 260)
    return (
        mask
        .filter(ImageFilter.MaxFilter(size=3))
        .filter(ImageFilter.GaussianBlur(radius=blur_radius))
        .point(lambda value: 255 if value >= 128 else 0)
        .filter(ImageFilter.MedianFilter(size=3))
        .resize(original_size, Image.Resampling.LANCZOS)
        .point(lambda value: 255 if value >= 128 else 0)
    )


def _largest_warm_artwork_component(rgb: Image.Image) -> Image.Image | None:
    width, height = rgb.size
    source_pixels = rgb.load()
    background = _estimate_background_color(rgb)
    artwork = bytearray(width * height)
    for y in range(height):
        row_offset = y * width
        for x in range(width):
            r, g, b = source_pixels[x, y]
            if _is_artwork_region_pixel(r, g, b, background):
                artwork[row_offset + x] = 1

    visited = bytearray(width * height)
    best_pixels: list[int] = []
    best_score = 0.0
    min_pixels = max(100, round(width * height * 0.04))
    for start, is_artwork in enumerate(artwork):
        if not is_artwork or visited[start]:
            continue
        stack = [start]
        visited[start] = 1
        component: list[int] = []
        left = width
        right = 0
        top = height
        bottom = 0
        while stack:
            idx = stack.pop()
            component.append(idx)
            x = idx % width
            y = idx // width
            left = min(left, x)
            right = max(right, x)
            top = min(top, y)
            bottom = max(bottom, y)
            for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if nx < 0 or nx >= width or ny < 0 or ny >= height:
                    continue
                nidx = ny * width + nx
                if artwork[nidx] and not visited[nidx]:
                    visited[nidx] = 1
                    stack.append(nidx)

        component_width = right - left + 1
        component_height = bottom - top + 1
        if len(component) < min_pixels:
            continue
        if component_width < width * 0.45 or component_height < height * 0.45:
            continue
        center_bonus = 1.2 if left < width * 0.55 and right > width * 0.45 else 1.0
        score = len(component) * center_bonus
        if score > best_score:
            best_score = score
            best_pixels = component

    if not best_pixels:
        return None

    mask = Image.new("L", rgb.size, 0)
    mask_pixels = mask.load()
    for idx in best_pixels:
        mask_pixels[idx % width, idx // width] = 255
    return mask


def _estimate_background_color(rgb: Image.Image) -> tuple[int, int, int]:
    width, height = rgb.size
    pixels = rgb.load()
    margin = max(3, min(width, height) // 32)
    samples: list[tuple[int, int, int]] = []
    for x_range, y_range in (
        (range(0, margin), range(0, margin)),
        (range(width - margin, width), range(0, margin)),
        (range(0, margin), range(height - margin, height)),
        (range(width - margin, width), range(height - margin, height)),
    ):
        for x in x_range:
            for y in y_range:
                samples.append(pixels[x, y])
    if not samples:
        return (255, 255, 255)
    channels = list(zip(*samples))
    return tuple(sorted(channel)[len(channel) // 2] for channel in channels)  # type: ignore[return-value]


def _is_artwork_region_pixel(r: int, g: int, b: int, background: tuple[int, int, int]) -> bool:
    bg_r, bg_g, bg_b = background
    color_distance = abs(r - bg_r) + abs(g - bg_g) + abs(b - bg_b)
    if color_distance < 42:
        return False
    brightness = (r + g + b) / 3
    if brightness > 246:
        return False
    return True


def _mask_outline(mask: Image.Image) -> Image.Image:
    expanded = mask.filter(ImageFilter.MaxFilter(size=3))
    contracted = mask.filter(ImageFilter.MinFilter(size=3))
    outline = Image.new("L", mask.size, 0)
    expanded_pixels = expanded.load()
    contracted_pixels = contracted.load()
    outline_pixels = outline.load()
    width, height = mask.size
    for y in range(height):
        for x in range(width):
            outline_pixels[x, y] = 255 if expanded_pixels[x, y] != contracted_pixels[x, y] else 0
    return outline


def _is_warm_artwork_ground(r: int, g: int, b: int) -> bool:
    return r > 135 and g > 95 and b < 135 and r > b + 35 and g > b + 10


def _format_image_api_error(response: httpx.Response) -> str:
    body = response.text.strip().replace("\n", " ")
    if len(body) > 500:
        body = f"{body[:500]}..."
    return f"Image API returned HTTP {response.status_code}: {body or response.reason_phrase}"
