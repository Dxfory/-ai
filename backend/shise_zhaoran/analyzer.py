"""Readiness and lightweight reference-color analysis."""

from pathlib import Path

from PIL import Image, ImageOps, ImageStat

from .rules import fixing_required
from .schemas import ReadinessResult


def analyze_readiness(upstream_image: str, medium: str, fixing_applied: bool) -> ReadinessResult:
    reasons: list[str] = []
    checks = {
        "upstream_exists": False,
        "line_structure_present": False,
        "tonal_structure_present": False,
        "water_color_base_present": False,
        "fixing_condition_met": False,
    }
    path = Path(upstream_image)
    if not path.is_file():
        reasons.append("上一阶段完成图不存在或不可读取")
        return ReadinessResult(
            status="not_ready",
            ready=False,
            medium=medium,
            fixing_required=fixing_required(medium),
            fixing_applied=fixing_applied,
            checks=checks,
            reasons=reasons,
        )

    checks["upstream_exists"] = True
    try:
        image = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
        gray = ImageOps.grayscale(image)
        gray_stat = ImageStat.Stat(gray)
        extrema = gray.getextrema()
        sample_size = (min(256, image.width), min(256, image.height))
        sample_pixels = max(1, sample_size[0] * sample_size[1])
        dark_ratio = sum(gray.resize(sample_size).histogram()[:130])
        saturation = image.convert("HSV").getchannel("S")
        color_ratio = sum(saturation.resize(sample_size).histogram()[19:])
        checks["line_structure_present"] = dark_ratio / sample_pixels > 0.001 or extrema[0] < 100
        checks["tonal_structure_present"] = gray_stat.stddev[0] >= 4.0
        checks["water_color_base_present"] = color_ratio / sample_pixels > 0.005
    except Exception:
        reasons.append("上一阶段文件不是有效图像")

    if not checks["line_structure_present"]:
        reasons.append("未检测到可保留的墨线或结构边界")
    if not checks["tonal_structure_present"]:
        reasons.append("未检测到分染形成的明暗结构")
    if not checks["water_color_base_present"]:
        reasons.append("未检测到水色罩染的综合色基础")

    required = fixing_required(medium)
    checks["fixing_condition_met"] = fixing_applied or not required
    if required and not fixing_applied:
        reasons.append("绢本进入石色罩染前必须完成胶矾水固定并待干")

    ready = all(checks.values())
    return ReadinessResult(
        status="ready" if ready else "not_ready",
        ready=ready,
        medium=medium,
        fixing_required=required,
        fixing_applied=fixing_applied,
        checks=checks,
        reasons=reasons,
    )


def infer_reference_pigments(reference_image: str | None) -> dict[str, tuple[str, str]]:
    if not reference_image or not Path(reference_image).is_file():
        return {}
    image = ImageOps.exif_transpose(Image.open(reference_image)).convert("RGB")
    sample = image.resize((96, 96))
    green_lightness = [
        (r + g + b) / 3
        for r, g, b in sample.getdata()
        if g > r * 1.05 and g > b * 1.03 and max(r, g, b) - min(r, g, b) > 12
    ]
    if not green_lightness:
        return {}
    mean_lightness = sum(green_lightness) / len(green_lightness)
    front = "three_green" if mean_lightness < 165 else "four_green"
    back = "four_green" if mean_lightness < 205 else "five_green"
    reason = f"参考图绿色区域平均明度 {mean_lightness:.1f}"
    return {"front_leaf": (front, reason), "back_leaf": (back, reason)}
