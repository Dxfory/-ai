"""白描线稿生成服务"""

import base64
import os
from dataclasses import dataclass
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFilter, ImageOps


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


BAIMIAO_PROMPT = """请把输入原画转换成中国工笔白描稿。任务不是创作新画，而是从输入原画中提取已经存在、可见的原作者墨线、结构边界和真实物象关系。

硬性禁令：
1. 严禁添加输入图中没有的任何对象。原图没有鸟，就绝对不要画鸟；原图没有动物，就绝对不要画动物。
2. 严禁新增枝条、叶片、花瓣、花苞、叶脉、羽毛、果实、题跋、印章、装饰纹样或原图没有的画面边框。
3. 严禁根据“工笔花鸟”题材常识补画、想象、重组画面。
4. 不要补全被遮挡、模糊到不可辨认或原图不可见的结构。

提取规则：
1. 构图方向、画芯边框、主体位置、对象数量、枝叶走势、花瓣遮挡关系必须忠实原图。
2. 只提取原画里可见的花瓣边线、叶缘、主叶脉、必要侧脉、枝干骨架、花梗、花蕊真实边界、遮挡断续线和转折包裹线；只有当动物在输入图中真实可见时，才允许提取其外形和内部结构线。
3. 如果原画有圆形、扇面、册页或其他画芯边缘，这个边缘是严格裁切边界：边界形状、位置、大小必须复刻原图，任何花、叶、枝、鸟、线条都不得越过边界外侧。
4. 参考已学习教材白描逻辑：骨架线清楚，轮廓线稳定，叶脉和纹理有取舍，遮挡处笔断意连，疏密虚实服从原作。
5. 不要把纸纹、扫描阴影、背景噪声、色块晕染边缘机械转成线。
6. 输出纯白背景、黑色清晰线条，尽量少灰度、少阴影、少噪声。

输出一张白底黑线 PNG。"""


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
    border = _detect_round_artwork_border(img)
    if border:
        guide = guide.convert("L")
        draw = ImageDraw.Draw(guide)
        draw.ellipse(border, outline=0, width=max(2, round(min(guide.size) * 0.0025)))
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
    original = Image.open(original_path).convert("RGB")
    original.thumbnail(clean.size, Image.Resampling.LANCZOS)
    border = _detect_round_artwork_border(original)
    if not border:
        return clean

    result = clean.convert("L")
    x_scale = result.width / original.width
    y_scale = result.height / original.height
    scaled = (
        round(border[0] * x_scale),
        round(border[1] * y_scale),
        round(border[2] * x_scale),
        round(border[3] * y_scale),
    )
    result = _clear_outside_ellipse(result, scaled)
    draw = ImageDraw.Draw(result)
    draw.ellipse(scaled, outline=0, width=max(2, round(min(result.size) * 0.0025)))
    return result


def _clear_outside_ellipse(img: Image.Image, ellipse: tuple[int, int, int, int]) -> Image.Image:
    result = img.convert("L")
    mask = Image.new("L", result.size, 0)
    draw = ImageDraw.Draw(mask)
    inset = max(1, round(min(result.size) * 0.0015))
    inner = (
        ellipse[0] + inset,
        ellipse[1] + inset,
        ellipse[2] - inset,
        ellipse[3] - inset,
    )
    draw.ellipse(inner, fill=255)
    white = Image.new("L", result.size, 255)
    white.paste(result, mask=mask)
    return white


def _detect_round_artwork_border(img: Image.Image) -> tuple[int, int, int, int] | None:
    rgb = img.convert("RGB")
    width, height = rgb.size
    pixels = rgb.load()
    sample_step = max(1, min(width, height) // 240)
    candidates: list[tuple[int, int]] = []
    for y in range(0, height, sample_step):
        for x in range(0, width, sample_step):
            r, g, b = pixels[x, y]
            if _is_warm_artwork_ground(r, g, b):
                candidates.append((x, y))
    if not candidates:
        return None

    xs = [p[0] for p in candidates]
    ys = [p[1] for p in candidates]
    left, right = min(xs), max(xs)
    top, bottom = min(ys), max(ys)
    box_w = right - left
    box_h = bottom - top
    if box_w < width * 0.55 or box_h < height * 0.55:
        return None
    if abs(box_w - box_h) > min(box_w, box_h) * 0.18:
        return None

    pad = max(2, round(min(width, height) * 0.005))
    return (
        max(0, left - pad),
        max(0, top - pad),
        min(width - 1, right + pad),
        min(height - 1, bottom + pad),
    )


def _is_warm_artwork_ground(r: int, g: int, b: int) -> bool:
    return r > 135 and g > 95 and b < 135 and r > b + 35 and g > b + 10


def _format_image_api_error(response: httpx.Response) -> str:
    body = response.text.strip().replace("\n", " ")
    if len(body) > 500:
        body = f"{body[:500]}..."
    return f"Image API returned HTTP {response.status_code}: {body or response.reason_phrase}"
