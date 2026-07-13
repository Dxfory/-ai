"""Independent Fenran training render service.

Fenran consumes an original artwork image plus an already-generated line draft.
It keeps the white-draft file immutable, prepares a color evidence bundle,
asks a GPT-image compatible model to do the teaching render, and preserves the
model's final teaching layout without re-overlaying the system line draft.
"""

from __future__ import annotations

import base64
import json
import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import httpx
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

RENDERER_VERSION = "fenran-renderer-v2"
BAIMIAO_CONTRACT_VERSION = "baimiao-output-contract-v1"
TECHNIQUE_TEMPLATE_VERSION = "fenran-llm-teaching-v1"
DEFAULT_IMAGE_MODEL = "gpt-image-2"
DEFAULT_API_BASE = "https://api.openai.com/v1"


@dataclass
class FenranTrainingRenderResult:
    output_path: str
    width: int
    height: int
    parameters: dict


def generate_fenran_training_render(
    original_path: str,
    line_draft_path: str,
    output_dir: str,
    sample_id: str,
    teaching_goal: str = "",
    render_image: Callable[..., dict | str | None] | None = None,
) -> FenranTrainingRenderResult:
    os.makedirs(output_dir, exist_ok=True)

    original = ImageOps.exif_transpose(Image.open(original_path)).convert("RGB")
    line_draft = ImageOps.exif_transpose(Image.open(line_draft_path)).convert("L")
    canvas_size = line_draft.size

    aligned_original = _align_original_to_canvas(original, canvas_size)
    registered_original = aligned_original.copy()
    registered_baimiao = _normalize_line_draft(line_draft)
    color_mask = _build_color_mask(aligned_original)
    palette = _extract_palette(aligned_original)
    regions = _extract_regions(aligned_original, color_mask)
    registration = _build_registration(original, line_draft, canvas_size)
    evidence = _build_color_evidence(
        original=original,
        aligned_original=aligned_original,
        line_draft=registered_baimiao,
        palette=palette,
        regions=regions,
        registration=registration,
        teaching_goal=teaching_goal,
    )
    prompt_bundle = _build_prompt_bundle(evidence=evidence, teaching_goal=teaching_goal)
    image_size = _resolve_image_size(canvas_size)
    config = _resolve_config()

    artifact_dir = Path(output_dir) / sample_id
    artifact_dir.mkdir(parents=True, exist_ok=True)

    paths = {
        "registered_original": artifact_dir / "registered_original.png",
        "registered_baimiao": artifact_dir / "registered_baimiao.png",
        "registration_overlay": artifact_dir / "registration_overlay.png",
        "registration_json": artifact_dir / "registration.json",
        "color_evidence_json": artifact_dir / "color_evidence.json",
        "prompt_bundle": artifact_dir / "prompt_bundle.json",
        "api_registered_original": artifact_dir / "api_registered_original.jpg",
        "api_registered_baimiao": artifact_dir / "api_registered_baimiao.png",
        "api_reference_overlay": artifact_dir / "api_reference_overlay.jpg",
        "raw_model_output": artifact_dir / "raw_model_output.png",
        "final_teaching_preview": artifact_dir / "final_teaching_preview.png",
        "technique_graph": artifact_dir / "technique_graph.json",
        "render_manifest": artifact_dir / "render_manifest.json",
    }

    registered_original.save(paths["registered_original"])
    registered_baimiao.save(paths["registered_baimiao"])
    _registration_overlay(registered_original, registered_baimiao).save(paths["registration_overlay"])
    _prepare_fenran_api_inputs(
        registered_original=registered_original,
        registered_baimiao=registered_baimiao,
        original_path=paths["api_registered_original"],
        baimiao_path=paths["api_registered_baimiao"],
        overlay_path=paths["api_reference_overlay"],
    )
    _write_json(paths["registration_json"], registration)
    _write_json(paths["color_evidence_json"], evidence)
    _write_json(paths["prompt_bundle"], prompt_bundle)

    request = {
        "model": config.model,
        "prompt": prompt_bundle["user_prompt"],
        "size": image_size,
        "image_paths": [str(paths["registered_original"]), str(paths["registered_baimiao"])],
        "api_image_paths": [str(paths["api_registered_original"]), str(paths["api_registered_baimiao"])],
        "fallback_image_path": str(paths["api_reference_overlay"]),
        "evidence": evidence,
        "output_path": str(paths["raw_model_output"]),
    }

    if render_image is None:
        _render_fenran_with_openai_compatible_api(
            request=request,
            api_key=config.api_key,
            base_url=config.base_url,
        )
    else:
        injected_request = {
            key: request[key]
            for key in ("model", "prompt", "size", "image_paths", "evidence", "output_path")
        }
        result = render_image(**injected_request)
        if isinstance(result, str):
            request["output_path"] = result
        elif isinstance(result, dict) and result.get("raw_output_path"):
            request["output_path"] = str(result["raw_output_path"])

    raw_model_output_path = Path(request["output_path"])
    if not raw_model_output_path.exists():
        raise RuntimeError("Fenran render did not produce a model output file")

    model_output = ImageOps.exif_transpose(Image.open(raw_model_output_path)).convert("RGB")
    model_output = _fit_to_canvas(model_output, canvas_size)
    final = model_output
    final.save(paths["final_teaching_preview"])
    if raw_model_output_path != paths["raw_model_output"]:
        raw_model_output_path.replace(paths["raw_model_output"])

    technique_graph = {
        "version": TECHNIQUE_TEMPLATE_VERSION,
        "layers": [
            {"id": "registration", "mode": "contain_resize", "status": "done"},
            {"id": "color_evidence", "mode": "lab_palette_and_regions", "status": "done"},
            {"id": "llm_teaching_render", "mode": "gpt-image-compatible", "model": config.model},
            {"id": "line_relay", "mode": "line_draft_input_only", "status": "skipped_final_overlay"},
        ],
        "requires_review": bool(registration["requires_review"]),
    }
    _write_json(paths["technique_graph"], technique_graph)

    manifest = {
        "sample_id": sample_id,
        "created_at": _utc_now(),
        "renderer_version": RENDERER_VERSION,
        "baimiao_version": BAIMIAO_CONTRACT_VERSION,
        "technique_template_version": TECHNIQUE_TEMPLATE_VERSION,
        "model": config.model,
        "api_base": config.base_url,
        "line_draft_modified": False,
        "line_overlay_applied": False,
        "needs_review": bool(registration["requires_review"]),
        "artifacts": {key: str(path) for key, path in paths.items()},
        "palette": palette,
        "teaching_goal": teaching_goal,
    }
    _write_json(paths["render_manifest"], manifest)

    return FenranTrainingRenderResult(
        output_path=str(paths["final_teaching_preview"]),
        width=final.width,
        height=final.height,
        parameters={
            "source": "original_plus_line_draft",
            "original_size": [original.width, original.height],
            "line_draft_size": [line_draft.width, line_draft.height],
            "aligned_size": [aligned_original.width, aligned_original.height],
            "line_draft_modified": False,
            "line_overlay_applied": False,
            "palette": palette,
            "evidence": evidence,
            "model": config.model,
            "api_base": config.base_url,
            "image_size": image_size,
            "renderer_version": RENDERER_VERSION,
            "baimiao_version": BAIMIAO_CONTRACT_VERSION,
            "technique_template_version": TECHNIQUE_TEMPLATE_VERSION,
            "artifacts": {key: str(path) for key, path in paths.items()},
        },
    )


@dataclass
class _FenranConfig:
    api_key: str | None
    base_url: str
    model: str


def _resolve_config() -> _FenranConfig:
    api_key = os.getenv("FENRAN_API_KEY") or os.getenv("OPENAI_API_KEY")
    base_url = (
        os.getenv("FENRAN_API_BASE")
        or os.getenv("OPENAI_BASE_URL")
        or os.getenv("OPENAI_API_BASE")
        or DEFAULT_API_BASE
    ).rstrip("/")
    if not base_url.endswith("/v1"):
        base_url = f"{base_url}/v1"
    model = os.getenv("FENRAN_IMAGE_MODEL", DEFAULT_IMAGE_MODEL).strip() or DEFAULT_IMAGE_MODEL
    return _FenranConfig(api_key=api_key, base_url=base_url, model=model)


def _render_fenran_with_openai_compatible_api(*, request: dict, api_key: str | None, base_url: str) -> dict:
    if not api_key:
        raise RuntimeError("Missing FENRAN_API_KEY or OPENAI_API_KEY")

    url = f"{base_url}/images/edits"
    headers = {"Authorization": f"Bearer {api_key}"}
    data = {
        "model": request["model"],
        "prompt": request["prompt"],
        "size": request["size"],
    }
    image_paths = request.get("api_image_paths") or request["image_paths"]

    with httpx.Client(timeout=_image_timeout_seconds()) as client:
        response = _post_fenran_multi_image_edit(client, url, headers, data, image_paths)
        if response.status_code >= 400 and _should_try_single_reference_fallback(response):
            fallback_path = request.get("fallback_image_path")
            if fallback_path:
                fallback_response = _post_fenran_single_reference_edit(client, url, headers, data, fallback_path)
                if fallback_response.status_code < 400:
                    response = fallback_response
        if response.status_code >= 400:
            raise RuntimeError(_format_image_api_error(response))
        payload = response.json()

        image_data = payload.get("data", [{}])[0]
        raw_output_path = Path(request["output_path"])
        if image_data.get("b64_json"):
            raw_output_path.write_bytes(base64.b64decode(image_data["b64_json"]))
        elif image_data.get("url"):
            image_response = client.get(image_data["url"])
            image_response.raise_for_status()
            raw_output_path.write_bytes(image_response.content)
        else:
            raise RuntimeError("Image API did not return b64_json or url")

    return {"raw_output_path": str(request["output_path"]), "provider": "gpt-image-compatible"}


def _post_fenran_multi_image_edit(client: httpx.Client, url: str, headers: dict, data: dict, image_paths: list[str]) -> httpx.Response:
    with open(image_paths[0], "rb") as first, open(image_paths[1], "rb") as second:
        files = [
            ("image", (Path(image_paths[0]).name, first, _guess_mime(image_paths[0]))),
            ("image", (Path(image_paths[1]).name, second, _guess_mime(image_paths[1]))),
        ]
        return client.post(url, headers=headers, data=data, files=files)


def _post_fenran_single_reference_edit(client: httpx.Client, url: str, headers: dict, data: dict, fallback_path: str) -> httpx.Response:
    with open(fallback_path, "rb") as reference_file:
        files = {"image": (Path(fallback_path).name, reference_file, _guess_mime(fallback_path))}
        return client.post(url, headers=headers, data=data, files=files)


def _should_try_single_reference_fallback(response: httpx.Response) -> bool:
    return response.status_code in {400, 413, 415, 422, 524}


def _align_original_to_canvas(original: Image.Image, canvas_size: tuple[int, int]) -> Image.Image:
    if original.size == canvas_size:
        return original.copy()
    contained = ImageOps.contain(original, canvas_size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", canvas_size, "white")
    offset = ((canvas_size[0] - contained.width) // 2, (canvas_size[1] - contained.height) // 2)
    canvas.paste(contained, offset)
    return canvas


def _fit_to_canvas(img: Image.Image, canvas_size: tuple[int, int]) -> Image.Image:
    if img.size == canvas_size:
        return img.copy()
    contained = ImageOps.contain(img, canvas_size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", canvas_size, "white")
    offset = ((canvas_size[0] - contained.width) // 2, (canvas_size[1] - contained.height) // 2)
    canvas.paste(contained, offset)
    return canvas


def _prepare_fenran_api_inputs(
    *,
    registered_original: Image.Image,
    registered_baimiao: Image.Image,
    original_path: Path,
    baimiao_path: Path,
    overlay_path: Path,
) -> None:
    max_side = max(256, int(os.getenv("FENRAN_API_MAX_IMAGE_SIDE", "1024")))
    target_size = _contain_size(registered_original.size, (max_side, max_side))
    original_api = registered_original.convert("RGB").resize(target_size, Image.Resampling.LANCZOS)
    baimiao_api = registered_baimiao.convert("L").resize(target_size, Image.Resampling.LANCZOS)
    baimiao_api = baimiao_api.point(lambda value: 0 if value < 200 else 255)
    overlay = _registration_overlay(original_api, baimiao_api)

    original_api.save(original_path, quality=90, optimize=True)
    baimiao_api.save(baimiao_path)
    overlay.save(overlay_path, quality=90, optimize=True)


def _contain_size(source_size: tuple[int, int], target_size: tuple[int, int]) -> tuple[int, int]:
    source_width, source_height = source_size
    target_width, target_height = target_size
    scale = min(target_width / max(1, source_width), target_height / max(1, source_height), 1.0)
    return max(1, round(source_width * scale)), max(1, round(source_height * scale))


def _guess_mime(path: str | Path) -> str:
    ext = str(path).rsplit(".", 1)[-1].lower()
    if ext in {"jpg", "jpeg"}:
        return "image/jpeg"
    if ext == "webp":
        return "image/webp"
    return "image/png"


def _build_color_mask(original: Image.Image) -> Image.Image:
    gray = ImageOps.grayscale(original)
    mask = gray.point(lambda value: 255 if value < 246 else 0)
    mask = mask.filter(ImageFilter.MaxFilter(size=3))
    return mask.filter(ImageFilter.GaussianBlur(radius=max(1.0, min(original.size) / 140)))


def _normalize_line_draft(line_draft: Image.Image) -> Image.Image:
    clean = line_draft.convert("L")
    return clean.point(lambda value: 0 if value < 200 else 255)


def _registration_overlay(original: Image.Image, line_draft: Image.Image) -> Image.Image:
    base = original.convert("RGBA")
    lines = Image.new("RGBA", line_draft.size, (0, 0, 0, 0))
    alpha = ImageOps.invert(line_draft).point(lambda value: min(255, max(0, value)))
    lines.putalpha(alpha)
    base.alpha_composite(lines)
    return base.convert("RGB")


def _overlay_line_draft(wash: Image.Image, line_draft: Image.Image) -> Image.Image:
    base = wash.convert("RGBA")
    line_overlay = Image.new("RGBA", line_draft.size, (0, 0, 0, 0))
    alpha = ImageOps.invert(line_draft).point(lambda value: min(255, max(0, value)))
    line_overlay.putalpha(alpha)
    base.alpha_composite(line_overlay)
    return base.convert("RGB")


def _build_registration(
    original: Image.Image,
    line_draft: Image.Image,
    canvas_size: tuple[int, int],
) -> dict:
    size_match = original.size == line_draft.size
    ratio_original = original.width / max(1, original.height)
    ratio_line = line_draft.width / max(1, line_draft.height)
    ratio_delta = abs(ratio_original - ratio_line) / max(0.001, ratio_line)
    requires_review = (not size_match) or ratio_delta > 0.05
    return {
        "registration_id": f"fenran-{original.width}x{original.height}-{canvas_size[0]}x{canvas_size[1]}",
        "global_transform": {
            "type": "contain_resize_to_line_draft_canvas",
            "original_size": [original.width, original.height],
            "canvas_size": [canvas_size[0], canvas_size[1]],
        },
        "local_transform_uri": None,
        "registration_score": 1.0 if not requires_review else round(max(0.55, 1.0 - ratio_delta), 4),
        "mean_boundary_error_px": 0.0 if size_match else None,
        "max_boundary_error_px": 0.0 if size_match else None,
        "requires_review": requires_review,
        "version": "fenran-registration-v1",
    }


def _build_color_evidence(
    *,
    original: Image.Image,
    aligned_original: Image.Image,
    line_draft: Image.Image,
    palette: list[str],
    regions: list[dict],
    registration: dict,
    teaching_goal: str,
) -> dict:
    paper_lab = _rgb_to_lab((255, 255, 255))
    palette_entries = []
    for index, color in enumerate(palette, start=1):
        rgb = _hex_to_rgb(color)
        lab = _rgb_to_lab(rgb)
        palette_entries.append(
            {
                "rank": index,
                "hex": color,
                "rgb": list(rgb),
                "lab": [round(v, 4) for v in lab],
                "delta_e00_to_paper": round(_delta_e2000(lab, paper_lab), 4),
            }
        )

    return {
        "teacher_goal": teaching_goal,
        "original_size": [original.width, original.height],
        "aligned_size": [aligned_original.width, aligned_original.height],
        "line_draft_size": [line_draft.width, line_draft.height],
        "paper_lab": [round(v, 4) for v in paper_lab],
        "palette": palette_entries,
        "regions": regions,
        "registration": registration,
        "review": {
            "needs_review": bool(registration["requires_review"]),
            "notes": ["preserve_line_draft", "no_crop", "no_resize_asymmetric"],
        },
        "contract_version": BAIMIAO_CONTRACT_VERSION,
    }


def _build_prompt_bundle(*, evidence: dict, teaching_goal: str) -> dict:
    system_prompt = (
        "你是一位工笔花鸟分染教学老师。"
        "你的任务不是重画白描，也不是改变构图，而是根据原画和白描，"
        "生成一张适合教学的分染示范图。"
    )
    user_prompt = f"""
请按照以下要求生成工笔花鸟分染教学图：
1. 只做分染教学，不改白描结构，不改构图，不裁切，不拉伸。
2. 保留纸白、线稿和主体轮廓，颜色必须来自原画可见色。
3. 按浅染 -> 加深 -> 局部提染的顺序组织画面。
4. 避免背景脏色、漂移、越界上色和随机噪点。
5. 让教学意图清楚：先看颜色，再看层次，再看线稿关系。
6. 用户教学目标：{teaching_goal or '分染教学'}

颜色证据：
{json.dumps(evidence, ensure_ascii=False, indent=2)}
""".strip()
    return {
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
        "teaching_goal": teaching_goal,
        "evidence_contract": BAIMIAO_CONTRACT_VERSION,
        "prompt_version": TECHNIQUE_TEMPLATE_VERSION,
    }


def _extract_palette(original: Image.Image, colors: int = 5) -> list[str]:
    quantized = original.quantize(colors=colors, method=Image.Quantize.MEDIANCUT)
    palette = quantized.getpalette() or []
    counts = quantized.getcolors() or []
    ranked: list[tuple[int, tuple[int, int, int]]] = []
    for count, index in counts:
        base = index * 3
        if base + 2 >= len(palette):
            continue
        rgb = (palette[base], palette[base + 1], palette[base + 2])
        if _is_near_white(rgb):
            continue
        ranked.append((count, rgb))
    ranked.sort(key=lambda item: item[0], reverse=True)
    if not ranked:
        ranked.append((1, _sample_center_color(original)))
    return [_rgb_to_hex(rgb) for _, rgb in ranked[:colors]]


def _extract_regions(original: Image.Image, color_mask: Image.Image) -> list[dict]:
    source = original.convert("RGB")
    mask = color_mask.convert("L")
    width, height = source.size
    pixels = source.load()
    mask_pixels = mask.load()

    visited = bytearray(width * height)
    regions: list[dict] = []
    for start_y in range(height):
        for start_x in range(width):
            start_index = start_y * width + start_x
            if visited[start_index] or mask_pixels[start_x, start_y] < 128:
                continue

            stack = [start_index]
            visited[start_index] = 1
            component: list[int] = []
            left = width
            top = height
            right = 0
            bottom = 0
            while stack:
                idx = stack.pop()
                component.append(idx)
                x = idx % width
                y = idx // width
                left = min(left, x)
                top = min(top, y)
                right = max(right, x)
                bottom = max(bottom, y)
                for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                    if nx < 0 or ny < 0 or nx >= width or ny >= height:
                        continue
                    nidx = ny * width + nx
                    if visited[nidx] or mask_pixels[nx, ny] < 128:
                        continue
                    visited[nidx] = 1
                    stack.append(nidx)

            if len(component) < max(30, (width * height) // 80):
                continue

            rgb_values = [pixels[idx % width, idx // width] for idx in component]
            mean_rgb = tuple(sum(channel) // len(rgb_values) for channel in zip(*rgb_values))
            mean_lab = _rgb_to_lab(mean_rgb)
            regions.append(
                {
                    "instance_id": f"region_{len(regions) + 1}",
                    "bbox": [left, top, right + 1, bottom + 1],
                    "area_px": len(component),
                    "mean_rgb": list(mean_rgb),
                    "mean_lab": [round(v, 4) for v in mean_lab],
                    "confidence": round(min(0.99, len(component) / max(1, width * height)), 4),
                    "requires_review": False,
                }
            )
            if len(regions) >= 4:
                return regions
    return regions


def _resolve_image_size(canvas_size: tuple[int, int]) -> str:
    requested = os.getenv("FENRAN_IMAGE_SIZE", "auto").strip()
    if requested and requested.lower() != "auto":
        return requested
    width, height = canvas_size
    ratio = width / max(1, height)
    if ratio >= 1.05:
        return "1536x1024"
    if ratio <= 0.95:
        return "1024x1536"
    return "1024x1024"


def _image_timeout_seconds() -> float:
    return float(os.getenv("FENRAN_IMAGE_TIMEOUT_SECONDS", "240"))


def _write_json(path: Path, payload: dict) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    tmp_path.replace(path)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sample_center_color(original: Image.Image) -> tuple[int, int, int]:
    x = original.width // 2
    y = original.height // 2
    return original.getpixel((x, y))


def _is_near_white(rgb: tuple[int, int, int]) -> bool:
    return sum(rgb) >= 720 or min(rgb) >= 242


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))  # type: ignore[return-value]


def _rgb_to_lab(rgb: tuple[int, int, int]) -> tuple[float, float, float]:
    def pivot(value: float) -> float:
        return ((value + 0.055) / 1.055) ** 2.4 if value > 0.04045 else value / 12.92

    r, g, b = (pivot(channel / 255.0) for channel in rgb)
    x = r * 0.4124564 + g * 0.3575761 + b * 0.1804375
    y = r * 0.2126729 + g * 0.7151522 + b * 0.0721750
    z = r * 0.0193339 + g * 0.1191920 + b * 0.9503041

    x /= 0.95047
    y /= 1.0
    z /= 1.08883

    def f(value: float) -> float:
        return value ** (1 / 3) if value > 0.008856 else (7.787 * value) + (16 / 116)

    fx, fy, fz = f(x), f(y), f(z)
    l = (116 * fy) - 16
    a = 500 * (fx - fy)
    b = 200 * (fy - fz)
    return l, a, b


def _delta_e2000(lab1: tuple[float, float, float], lab2: tuple[float, float, float]) -> float:
    l1, a1, b1 = lab1
    l2, a2, b2 = lab2

    avg_lp = (l1 + l2) / 2.0
    c1 = math.sqrt(a1 * a1 + b1 * b1)
    c2 = math.sqrt(a2 * a2 + b2 * b2)
    avg_c = (c1 + c2) / 2.0
    g = 0.5 * (1 - math.sqrt((avg_c ** 7) / ((avg_c ** 7) + (25 ** 7))))
    a1p = (1 + g) * a1
    a2p = (1 + g) * a2
    c1p = math.sqrt(a1p * a1p + b1 * b1)
    c2p = math.sqrt(a2p * a2p + b2 * b2)
    avg_cp = (c1p + c2p) / 2.0

    def hp(ap: float, b: float) -> float:
        if ap == 0 and b == 0:
            return 0.0
        angle = math.degrees(math.atan2(b, ap))
        return angle + 360 if angle < 0 else angle

    h1p = hp(a1p, b1)
    h2p = hp(a2p, b2)

    delta_lp = l2 - l1
    delta_cp = c2p - c1p

    if c1p * c2p == 0:
        delta_hp = 0.0
    elif abs(h2p - h1p) <= 180:
        delta_hp = h2p - h1p
    elif h2p <= h1p:
        delta_hp = h2p - h1p + 360
    else:
        delta_hp = h2p - h1p - 360
    delta_hp = 2 * math.sqrt(c1p * c2p) * math.sin(math.radians(delta_hp / 2.0))

    avg_hp = 0.0
    if c1p * c2p == 0:
        avg_hp = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        avg_hp = (h1p + h2p) / 2.0
    elif (h1p + h2p) < 360:
        avg_hp = (h1p + h2p + 360) / 2.0
    else:
        avg_hp = (h1p + h2p - 360) / 2.0

    t = (
        1
        - 0.17 * math.cos(math.radians(avg_hp - 30))
        + 0.24 * math.cos(math.radians(2 * avg_hp))
        + 0.32 * math.cos(math.radians(3 * avg_hp + 6))
        - 0.20 * math.cos(math.radians(4 * avg_hp - 63))
    )
    delta_theta = 30 * math.exp(-(((avg_hp - 275) / 25) ** 2))
    rc = 2 * math.sqrt((avg_cp ** 7) / ((avg_cp ** 7) + (25 ** 7)))
    sl = 1 + ((0.015 * ((avg_lp - 50) ** 2)) / math.sqrt(20 + ((avg_lp - 50) ** 2)))
    sc = 1 + 0.045 * avg_cp
    sh = 1 + 0.015 * avg_cp * t
    rt = -math.sin(math.radians(2 * delta_theta)) * rc

    dl = delta_lp / sl
    dc = delta_cp / sc
    dh = delta_hp / sh
    return math.sqrt(dl * dl + dc * dc + dh * dh + rt * dc * dh)


def _format_image_api_error(response: httpx.Response) -> str:
    body = response.text.strip().replace("\n", " ")
    if len(body) > 500:
        body = f"{body[:500]}..."
    return f"Image API returned HTTP {response.status_code}: {body or response.reason_phrase}"
