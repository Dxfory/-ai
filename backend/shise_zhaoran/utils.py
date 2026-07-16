"""Filesystem and quality helpers for Shise Zhaoran."""

import json
from pathlib import Path

from PIL import Image, ImageChops, ImageFilter, ImageOps, ImageStat

from .schemas import QualityResult


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def validate_output(upstream_path: str, output_path: str) -> QualityResult:
    source = ImageOps.exif_transpose(Image.open(upstream_path)).convert("RGB")
    output = ImageOps.exif_transpose(Image.open(output_path)).convert("RGB")
    same_dimensions = source.size == output.size
    source_edge = ImageOps.grayscale(source).filter(ImageFilter.FIND_EDGES)
    output_edge = ImageOps.grayscale(output).filter(ImageFilter.FIND_EDGES)
    if output_edge.size != source_edge.size:
        output_edge = output_edge.resize(source_edge.size)
    edge_diff = ImageStat.Stat(ImageChops.difference(source_edge, output_edge)).mean[0] / 255
    tone_diff = sum(ImageStat.Stat(ImageChops.difference(source, output)).mean) / (3 * 255)
    structure_preserved = edge_diff < 0.34
    not_flat_filter = tone_diff > 0.002
    not_overpainted = tone_diff < 0.48
    checks: dict[str, bool | float] = {
        "same_dimensions": same_dimensions,
        "structure_preserved": structure_preserved,
        "not_flat_filter": not_flat_filter,
        "not_overpainted": not_overpainted,
        "edge_difference": round(edge_diff, 4),
        "tone_difference": round(tone_diff, 4),
    }
    warnings: list[str] = []
    if not structure_preserved:
        warnings.append("输出与上一阶段结构差异过大，疑似改变构图或对象造型")
    if not not_flat_filter:
        warnings.append("输出变化过小，可能未形成有效石色罩染")
    if not not_overpainted:
        warnings.append("输出整体变化过大，可能覆盖过厚或发生整体重绘")
    passed = same_dimensions and structure_preserved and not_flat_filter and not_overpainted
    return QualityResult(passed=passed, checks=checks, warnings=warnings)


def upload_url(path: str, upload_root: str) -> str | None:
    try:
        relative = Path(path).resolve().relative_to(Path(upload_root).resolve())
    except ValueError:
        return None
    return f"/uploads/{relative.as_posix()}"
