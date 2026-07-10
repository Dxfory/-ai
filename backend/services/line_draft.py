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
    data = {
        "model": model,
        "prompt": final_prompt,
        "size": _resolve_image_size(source_path),
    }

    os.makedirs(output_dir, exist_ok=True)
    output_path = Path(output_dir) / f"{draft_id}.png"
    raw_output_path = Path(output_dir) / f"{draft_id}_raw.png"
    api_input_path = Path(output_dir) / f"{draft_id}_api_input.jpg"
    guide_path = Path(output_dir) / f"{draft_id}_structure_guide.png"
    _prepare_api_image(source_path, str(api_input_path))
    _make_baimiao_structure_guide(source_path, str(guide_path))

    with httpx.Client(timeout=_image_timeout_seconds()) as client:
        payload = _post_baimiao_edit(
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

    _clean_ai_line_art(str(raw_output_path), str(output_path), original_path=source_path)
    with Image.open(output_path) as img:
        width, height = img.size
    return LineDraftResult(
        output_path=str(output_path),
        width=width,
        height=height,
        parameters={
            "provider": "ai_baimiao",
            "model": model,
            "base_url": base_url,
            "size": data["size"],
            "prompt": final_prompt,
            "api_input_path": str(api_input_path),
            "raw_output_path": str(raw_output_path),
            "structure_guide_path": str(guide_path),
            "cleaned": True,
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
    if ratio >= 1.2:
        return "1536x1024"
    if ratio <= 0.83:
        return "1024x1536"
    return "1024x1024"


def _image_timeout_seconds() -> float:
    return float(os.getenv("BAIMIAO_IMAGE_TIMEOUT_SECONDS", "240"))


def _prepare_api_image(source_path: str, output_path: str) -> None:
    max_side = int(os.getenv("BAIMIAO_API_MAX_IMAGE_SIDE", "1024"))
    img = ImageOps.exif_transpose(Image.open(source_path)).convert("RGB")
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
) -> dict:
    try:
        response = _post_baimiao_edit_without_status_check(
            client=client,
            url=url,
            headers=headers,
            data=data,
            source_path=source_path,
            guide_path=guide_path,
        )
        response.raise_for_status()
        return response.json()
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
) -> httpx.Response:
    if os.getenv("BAIMIAO_USE_STRUCTURE_GUIDE", "false").lower() not in {"1", "true", "yes"}:
        return _post_single_image_edit(client, url, headers, data, source_path)

    try:
        with open(source_path, "rb") as source_file, open(guide_path, "rb") as guide_file:
            files = [
                ("image", (Path(source_path).name, source_file, _guess_mime(source_path))),
                ("image", (Path(guide_path).name, guide_file, "image/png")),
            ]
            response = client.post(url, headers=headers, data=data, files=files)
    except httpx.HTTPError:
        return _post_single_image_edit(client, url, headers, data, source_path)
    if response.status_code in {400, 413, 415, 422}:
        return _post_single_image_edit(client, url, headers, data, source_path)
    return response


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


def _make_baimiao_structure_guide(source_path: str, output_path: str) -> None:
    img = Image.open(source_path).convert("RGB")
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
        guide.paste(0, mask=_mask_outline(artwork_mask))
    guide.save(output_path)


def _clean_ai_line_art(source_path: str, output_path: str, original_path: str | None = None) -> None:
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
    if original_path:
        clean = _restore_round_border_from_original(clean, original_path)
    clean.save(output_path)


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
    rgb = img.convert("RGB")
    width, height = rgb.size
    pixels = rgb.load()
    min_row_pixels = max(12, round(width * 0.035))
    row_spans: list[tuple[int, int, int]] = []
    for y in range(height):
        xs: list[int] = []
        for x in range(width):
            r, g, b = pixels[x, y]
            if _is_warm_artwork_ground(r, g, b):
                xs.append(x)
        if len(xs) >= min_row_pixels:
            left_index = max(0, round(len(xs) * 0.02) - 1)
            right_index = min(len(xs) - 1, round(len(xs) * 0.98))
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
    )


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
