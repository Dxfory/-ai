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


BAIMIAO_PROMPT = """请将输入图片转写成中国工笔花鸟白描临摹稿。
要求：
1. 纯白背景，黑色线条，不要灰度、阴影、纸纹、污渍、色块或背景纹理。
2. 只保留花瓣、叶片、枝干、鸟体等可临摹结构线。
3. 线条要像专业工笔白描稿，干净、流畅、有主次和轻重。
4. 不要机械边缘检测，不要把原图明暗、布纹、扇面纹、老纸噪声变成线。
5. 构图和主体位置尽量忠实原图，但可以为临摹清晰度补全必要结构线。
输出一张可打印、可临摹的白底黑线 PNG。"""


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
        "size": os.getenv("BAIMIAO_IMAGE_SIZE", "1024x1024"),
    }

    os.makedirs(output_dir, exist_ok=True)
    output_path = Path(output_dir) / f"{draft_id}.png"

    with open(source_path, "rb") as image_file:
        files = {"image": (Path(source_path).name, image_file, _guess_mime(source_path))}
        with httpx.Client(timeout=120) as client:
            response = client.post(url, headers=headers, data=data, files=files)
            response.raise_for_status()
            payload = response.json()

            image_data = payload.get("data", [{}])[0]
            if image_data.get("b64_json"):
                output_path.write_bytes(base64.b64decode(image_data["b64_json"]))
            elif image_data.get("url"):
                image_response = client.get(image_data["url"])
                image_response.raise_for_status()
                output_path.write_bytes(image_response.content)
            else:
                raise RuntimeError("Image API did not return b64_json or url")

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
            "prompt": final_prompt,
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
