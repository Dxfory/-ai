"""白描线稿生成服务"""

import base64
import os
from dataclasses import dataclass
from pathlib import Path

import httpx
from PIL import Image, ImageFilter, ImageOps


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

必须遵守：
1. 构图方向、主体位置、对象数量、枝叶走势、花果/鸟体位置必须忠实原图。
2. 只提取原画里可见的花瓣边线、叶缘、主叶脉、必要侧脉、枝干骨架、果实外轮廓、鸟体外形、羽组边界、遮挡断续线、转折包裹线。
3. 不要发明新枝条、新叶脉、新花瓣、新羽毛、新果实，不要为了好看重新组织画面。
4. 不要把照片光影、纸纹、扫描阴影、背景纹理、脏点、绢本纹、色块晕染边缘机械转成线。
5. 线条要符合工笔白描逻辑：骨架线清楚，轮廓线稳定，叶脉和纹理线有取舍，遮挡处允许断线但要笔断意连，疏密和虚实服从原作。
6. 输出纯白背景、黑色线条，尽量少灰度、少阴影、少噪声。

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

    with open(source_path, "rb") as image_file:
        files = {"image": (Path(source_path).name, image_file, _guess_mime(source_path))}
        with httpx.Client(timeout=120) as client:
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

    _clean_ai_line_art(str(raw_output_path), str(output_path))
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
            "raw_output_path": str(raw_output_path),
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

    with open(source_path, "rb") as source_file, open(line_draft_path, "rb") as draft_file:
        files = [
            ("image", (Path(source_path).name, source_file, _guess_mime(source_path))),
            ("image", (Path(line_draft_path).name, draft_file, _guess_mime(line_draft_path))),
        ]
        with httpx.Client(timeout=180) as client:
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


def _clean_ai_line_art(source_path: str, output_path: str) -> None:
    """将 AI 输出里的灰底、渐变和轻微阴影清成白底黑线。"""
    threshold = int(os.getenv("BAIMIAO_CLEAN_THRESHOLD", "215"))
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
    clean.save(output_path)


def _normalize_step_image(source_path: str, output_path: str) -> None:
    img = Image.open(source_path).convert("RGB")
    img.save(output_path)
