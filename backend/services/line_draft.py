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


BAIMIAO_PROMPT = """请把输入原画转换成中国工笔花鸟白描稿。

核心目标：
学习并提取原画中已经存在的作者勾线、墨线、结构线和可见设色边界中的真实结构关系，输出可打印临摹的白底黑线稿。

输入说明：
如果同时提供两张图，第一张是原画，第二张是本地结构锁定参考图。第二张不代表最终风格，但它锁定构图、画芯边框、枝干走势、花叶位置和主要边界，不得忽略。

必须遵守：
1. 构图方向、主体位置、对象数量、枝叶走势、花果/鸟体位置必须忠实原图。
2. 只提取原画里可见的花瓣边线、叶缘、主叶脉、必要侧脉、枝干骨架、花梗、果实外轮廓、鸟体外形、羽组边界、遮挡断续线、转折包裹线。
3. 不要发明新枝条、新叶脉、新花瓣、新羽毛、新果实，不要为了好看重新组织画面。
4. 不要把照片光影、纸纹、扫描阴影、背景纹理、脏点、绢本纹、色块晕染边缘机械转成线。
5. 线条要符合工笔白描逻辑：骨架线清楚，轮廓线稳定，叶脉和纹理线有取舍，遮挡处允许断线但要笔断意连，疏密和虚实服从原作。
6. 如果原画存在圆形、扇面、册页或其他画芯边框，边框属于作品结构，必须保留为完整干净的外轮廓线。
7. 枝干和花梗是连接全画的骨架，必须完整保留；不能只画花叶而丢掉枝干。
8. 大花瓣必须保持完整外轮廓和互相遮挡关系，不能缺瓣、断瓣、把花心改成不属于原图的毛刺团。
9. 输出纯白背景、黑色线条，线条应实、清楚、连续；不要虚线、点线、中空线、灰线、阴影或噪声。

输出一张白底黑线 PNG。"""


FENRAN_KNOWLEDGE = """已学习的工笔花鸟分染/罩染规则摘要：
- 分染不是完整上色成品，而是在白描骨架上以淡墨、淡色建立体积、明暗和前后层次。
- 所有色层都要薄、透、少量多次，必须保留白描线，不可压死线条。
- 正叶常用花青、汁绿、三绿系统分染或罩染；主叶脉附近要保留水线，叶脉醒提必须顺原有叶脉结构。
- 反叶常用赭石加少量藤黄、四绿或汁绿处理，颜色比正叶更灰、更柔，不可与正叶混成同一色相。
- 枝干多用淡墨、赭墨、赭石加藤黄干笔皴染，保留节疤、转折和干笔质感。
- 果实用赭粉、赭石、藤黄、淡胭红、胭脂等依体积分染，边缘和遮挡处建立层次，不机械涂满。
- 鸟体先按头、身、尾和胸腹明暗关系分染，羽毛只顺已有羽组关系淡淡建立蓬松感，不新增羽毛。
- 花瓣和花脉分染要轻，白粉/蛤粉只用于提亮或醒提，不扩大成装饰纹样。
- 分染图应看起来像“步骤图”：颜色未完成但关系清楚，过渡自然，白底或淡底，不能变成最终浓彩完成稿。
"""


FENRAN_PROMPT = f"""请根据输入原画和白描稿生成中国工笔花鸟“分染步骤图”。

任务定义：
输出的是白描之后的第一层或中前期分染示范图，不是完成稿。请在白描骨架上添加淡墨、淡色分染，让用户知道下一步如何建立体积、明暗、正反叶、枝干、花果和鸟体层次。

{FENRAN_KNOWLEDGE}

必须遵守：
1. 构图、方向、主体位置、对象数量、枝叶走势、花果/鸟体位置必须完全跟随输入白描稿和原画。
2. 白描线必须清楚保留，不要被颜色盖住；不要重画、改画或新增结构。
3. 颜色参考原画，但只做淡层分染：透明、自然、渐变柔和，不要做成饱和厚涂或完整成品。
4. 分染应体现国画逻辑：正叶/反叶区别、叶脉水线、果实体积、枝干干笔质感、鸟体部位明暗、遮挡前后层次。
5. 不要加入纸纹、扫描阴影、背景脏点、照片光影和无关装饰。
6. 输出干净白底或极淡底色的 PNG 步骤图。
"""


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


def generate_ai_fenran(
    source_path: str,
    line_draft_path: str,
    output_dir: str,
    step_id: str,
    prompt: str = "",
) -> LineDraftResult:
    """通过 OpenAI Images 兼容接口生成工笔分染步骤图。"""
    api_key = os.getenv("FENRAN_API_KEY") or os.getenv("BAIMIAO_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing FENRAN_API_KEY, BAIMIAO_API_KEY, or OPENAI_API_KEY")

    base_url = (
        os.getenv("FENRAN_API_BASE")
        or os.getenv("BAIMIAO_API_BASE")
        or os.getenv("OPENAI_BASE_URL")
        or os.getenv("OPENAI_API_BASE")
        or "https://api.openai.com/v1"
    ).rstrip("/")
    if not base_url.endswith("/v1"):
        base_url = f"{base_url}/v1"

    model = os.getenv("FENRAN_IMAGE_MODEL") or os.getenv("BAIMIAO_IMAGE_MODEL", "gpt-image-1")
    final_prompt = prompt.strip() or FENRAN_PROMPT
    url = f"{base_url}/images/edits"
    headers = {"Authorization": f"Bearer {api_key}"}
    data = {
        "model": model,
        "prompt": final_prompt,
        "size": _resolve_image_size(source_path),
    }

    os.makedirs(output_dir, exist_ok=True)
    output_path = Path(output_dir) / f"{step_id}.png"
    raw_output_path = Path(output_dir) / f"{step_id}_raw.png"
    api_source_path = Path(output_dir) / f"{step_id}_source_api_input.jpg"
    api_draft_path = Path(output_dir) / f"{step_id}_draft_api_input.png"
    _prepare_api_image(source_path, str(api_source_path))
    _prepare_api_image(line_draft_path, str(api_draft_path))

    with open(api_source_path, "rb") as source_file, open(api_draft_path, "rb") as draft_file:
        files = [
            ("image", (Path(api_source_path).name, source_file, _guess_mime(str(api_source_path)))),
            ("image", (Path(api_draft_path).name, draft_file, _guess_mime(str(api_draft_path)))),
        ]
        with httpx.Client(timeout=_image_timeout_seconds()) as client:
            response = client.post(url, headers=headers, data=data, files=files)
            response.raise_for_status()
            payload = response.json()

            image_data = payload.get("data", [{}])[0]
            if image_data.get("b64_json"):
                raw_output_path.write_bytes(base64.b64decode(image_data["b64_json"]))
            elif image_data.get("url"):
                image_response = client.get(image_data["url"])
                image_response.raise_for_status()
                raw_output_path.write_bytes(image_response.content)
            else:
                raise RuntimeError("Image API did not return b64_json or url")

    _normalize_step_image(str(raw_output_path), str(output_path))
    with Image.open(output_path) as img:
        width, height = img.size
    return LineDraftResult(
        output_path=str(output_path),
        width=width,
        height=height,
        parameters={
            "provider": "ai_fenran",
            "model": model,
            "base_url": base_url,
            "size": data["size"],
            "prompt": final_prompt,
            "raw_output_path": str(raw_output_path),
            "knowledge": "book_001_fenran_rules",
        },
    )


def generate_local_fenran_preview(
    source_path: str,
    line_draft_path: str,
    output_dir: str,
    step_id: str,
) -> LineDraftResult:
    """本地淡彩预览，用于验证流程，不作为最终分染模型质量。"""
    os.makedirs(output_dir, exist_ok=True)
    source = Image.open(source_path).convert("RGB")
    source.thumbnail((1800, 1800), Image.Resampling.LANCZOS)
    line = Image.open(line_draft_path).convert("L")
    line = ImageOps.contain(line, source.size, Image.Resampling.LANCZOS)

    base = ImageOps.autocontrast(source)
    base = base.filter(ImageFilter.GaussianBlur(radius=5))
    base = ImageOps.solarize(base, threshold=236)
    base = Image.blend(Image.new("RGB", base.size, "white"), base, 0.28)

    canvas = Image.new("RGB", source.size, "white")
    offset = ((source.width - line.width) // 2, (source.height - line.height) // 2)
    canvas.paste(base)

    line_layer = Image.new("RGB", source.size, "white")
    line_layer.paste(line.convert("RGB"), offset)
    line_mask = ImageOps.invert(line)
    mask_canvas = Image.new("L", source.size, 0)
    mask_canvas.paste(line_mask, offset)
    ink = Image.new("RGB", source.size, (34, 34, 30))
    canvas.paste(ink, mask=mask_canvas.point(lambda v: 230 if v > 30 else 0))

    out_path = Path(output_dir) / f"{step_id}.png"
    canvas.save(out_path)
    return LineDraftResult(
        output_path=str(out_path),
        width=canvas.width,
        height=canvas.height,
        parameters={
            "provider": "local_fenran_preview",
            "source": "algorithmic_preview",
            "note": "本地预览只验证流程，真实分染质量以后由 AI/训练模型负责。",
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
    return float(os.getenv("BAIMIAO_IMAGE_TIMEOUT_SECONDS", "120"))


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
    if os.getenv("BAIMIAO_USE_STRUCTURE_GUIDE", "false").lower() not in {"1", "true", "yes"}:
        response = _post_single_image_edit(client, url, headers, data, source_path)
        response.raise_for_status()
        return response.json()

    try:
        with open(source_path, "rb") as source_file, open(guide_path, "rb") as guide_file:
            files = [
                ("image", (Path(source_path).name, source_file, _guess_mime(source_path))),
                ("image", (Path(guide_path).name, guide_file, "image/png")),
            ]
            response = client.post(url, headers=headers, data=data, files=files)
    except httpx.HTTPError:
        response = _post_single_image_edit(client, url, headers, data, source_path)
    else:
        if response.status_code in {400, 413, 415, 422}:
            response = _post_single_image_edit(client, url, headers, data, source_path)
    response.raise_for_status()
    return response.json()


def _post_single_image_edit(
    client: httpx.Client,
    url: str,
    headers: dict,
    data: dict,
    source_path: str,
) -> httpx.Response:
    attempts = max(1, int(os.getenv("BAIMIAO_API_RETRIES", "1")))
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
    """将 AI 输出里的灰底、渐变和轻微阴影清成白底黑线。"""
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
    draw = ImageDraw.Draw(result)
    draw.ellipse(scaled, outline=0, width=max(2, round(min(result.size) * 0.0025)))
    return result


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


def _normalize_step_image(source_path: str, output_path: str) -> None:
    img = Image.open(source_path).convert("RGB")
    img.save(output_path)
