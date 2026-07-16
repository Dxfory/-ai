"""Fail-closed validation for cumulative Fenran stages."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from PIL import Image, ImageChops, ImageFilter, ImageStat


@dataclass(frozen=True)
class FenranValidationThresholds:
    min_subject_bbox_iou: float = 0.90
    max_subject_center_shift_ratio: float = 0.02
    max_subject_size_change_ratio: float = 0.04
    min_subject_coverage: float = 0.92
    max_outside_subject_change_ratio: float = 0.01
    min_stage_change_ratio: float = 0.002
    min_validation_score: float = 0.80
    min_line_retention_ratio: float = 0.35


@dataclass
class FenranValidationResult:
    passed: bool
    score: float
    canvas_match: bool
    subject_bbox_iou: float
    subject_center_shift_ratio: float
    subject_width_change_ratio: float
    subject_height_change_ratio: float
    subject_coverage: float
    outside_subject_change_ratio: float
    stage_change_ratio: float
    line_retention_ratio: float
    mean_color_difference: float = 0.0
    mean_luminance_change: float = 0.0
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _ratio_changed(diff: Image.Image, mask: Image.Image, threshold: int = 5) -> float:
    diff_gray = diff.convert("L")
    mask_gray = mask.convert("L")
    changed = 0
    total = 0
    diff_pixels = diff_gray.load()
    mask_pixels = mask_gray.load()
    for y in range(diff.height):
        for x in range(diff.width):
            if mask_pixels[x, y] < 128:
                continue
            total += 1
            if diff_pixels[x, y] > threshold:
                changed += 1
    return changed / total if total else 0.0


def _bbox_iou(first: tuple[int, int, int, int] | None, second: tuple[int, int, int, int] | None) -> float:
    if not first or not second:
        return 0.0
    left = max(first[0], second[0])
    top = max(first[1], second[1])
    right = min(first[2], second[2])
    bottom = min(first[3], second[3])
    intersection = max(0, right - left) * max(0, bottom - top)
    first_area = max(0, first[2] - first[0]) * max(0, first[3] - first[1])
    second_area = max(0, second[2] - second[0]) * max(0, second[3] - second[1])
    union = first_area + second_area - intersection
    return intersection / union if union else 0.0


def validate_fenran_stage(
    *,
    stage_id: str,
    previous: Image.Image,
    current: Image.Image,
    expected_subject_mask: Image.Image,
    expected_line_mask: Image.Image | None = None,
    canonical_size: tuple[int, int],
    thresholds: FenranValidationThresholds,
) -> FenranValidationResult:
    if current.size != canonical_size or previous.size != canonical_size:
        return FenranValidationResult(
            passed=False,
            score=0.0,
            canvas_match=False,
            subject_bbox_iou=0.0,
            subject_center_shift_ratio=1.0,
            subject_width_change_ratio=1.0,
            subject_height_change_ratio=1.0,
            subject_coverage=0.0,
            outside_subject_change_ratio=1.0,
            stage_change_ratio=0.0,
            line_retention_ratio=0.0,
            reasons=["canvas_size_mismatch"],
        )

    previous_rgb = previous.convert("RGB")
    current_rgb = current.convert("RGB")
    diff = ImageChops.difference(previous_rgb, current_rgb)
    expected = expected_subject_mask.convert("L")
    background = expected.point(lambda value: 0 if value >= 128 else 255)
    stage_change_ratio = _ratio_changed(diff, expected)
    outside_change_ratio = _ratio_changed(diff, background)
    line_retention_ratio = 1.0
    if expected_line_mask is not None:
        expected_lines = expected_line_mask.convert("L").point(lambda value: 255 if value >= 64 else 0)
        current_edges = current_rgb.convert("L").filter(ImageFilter.FIND_EDGES)
        current_edges = current_edges.point(lambda value: 255 if value >= 12 else 0).filter(ImageFilter.MaxFilter(5))
        expected_pixels = expected_lines.load()
        edge_pixels = current_edges.load()
        retained = 0
        total_lines = 0
        for y in range(current.height):
            for x in range(current.width):
                if expected_pixels[x, y] < 128:
                    continue
                total_lines += 1
                if edge_pixels[x, y] >= 128:
                    retained += 1
        line_retention_ratio = retained / total_lines if total_lines else 1.0

    current_signal = current_rgb.convert("L").point(lambda value: 255 if value < 250 else 0)
    expected_bbox = expected.getbbox()
    observed_bbox = ImageChops.multiply(current_signal, expected).getbbox()
    bbox_iou = _bbox_iou(expected_bbox, observed_bbox)
    if expected_bbox and observed_bbox:
        expected_w = max(1, expected_bbox[2] - expected_bbox[0])
        expected_h = max(1, expected_bbox[3] - expected_bbox[1])
        observed_w = observed_bbox[2] - observed_bbox[0]
        observed_h = observed_bbox[3] - observed_bbox[1]
        expected_center = ((expected_bbox[0] + expected_bbox[2]) / 2, (expected_bbox[1] + expected_bbox[3]) / 2)
        observed_center = ((observed_bbox[0] + observed_bbox[2]) / 2, (observed_bbox[1] + observed_bbox[3]) / 2)
        center_shift = max(
            abs(observed_center[0] - expected_center[0]) / expected_w,
            abs(observed_center[1] - expected_center[1]) / expected_h,
        )
        width_change = abs(observed_w - expected_w) / expected_w
        height_change = abs(observed_h - expected_h) / expected_h
        coverage = min(1.0, observed_w * observed_h / max(1, expected_w * expected_h))
    else:
        center_shift = width_change = height_change = 1.0
        coverage = 0.0

    stats = ImageStat.Stat(diff, mask=expected)
    mean_color_difference = sum(stats.mean[:3]) / 3 if stats.mean else 0.0
    previous_l = ImageStat.Stat(previous_rgb.convert("L"), mask=expected).mean[0]
    current_l = ImageStat.Stat(current_rgb.convert("L"), mask=expected).mean[0]
    mean_luminance_change = current_l - previous_l

    reasons = []
    if bbox_iou < thresholds.min_subject_bbox_iou:
        reasons.append("subject_bbox_iou_below_threshold")
    if center_shift > thresholds.max_subject_center_shift_ratio:
        reasons.append("subject_center_shift_above_threshold")
    if max(width_change, height_change) > thresholds.max_subject_size_change_ratio:
        reasons.append("subject_size_change_above_threshold")
    if coverage < thresholds.min_subject_coverage:
        reasons.append("subject_coverage_below_threshold")
    if outside_change_ratio > thresholds.max_outside_subject_change_ratio:
        reasons.append("outside_subject_change_above_threshold")
    if stage_change_ratio < thresholds.min_stage_change_ratio:
        reasons.append("stage_change_below_threshold")
    if line_retention_ratio < thresholds.min_line_retention_ratio:
        reasons.append("line_retention_below_threshold")

    penalties = min(1.0, len(reasons) * 0.18)
    score = round(max(0.0, 1.0 - penalties), 4)
    passed = not reasons and score >= thresholds.min_validation_score
    return FenranValidationResult(
        passed=passed,
        score=score,
        canvas_match=True,
        subject_bbox_iou=round(bbox_iou, 4),
        subject_center_shift_ratio=round(center_shift, 4),
        subject_width_change_ratio=round(width_change, 4),
        subject_height_change_ratio=round(height_change, 4),
        subject_coverage=round(coverage, 4),
        outside_subject_change_ratio=round(outside_change_ratio, 6),
        stage_change_ratio=round(stage_change_ratio, 6),
        line_retention_ratio=round(line_retention_ratio, 4),
        mean_color_difference=round(mean_color_difference, 4),
        mean_luminance_change=round(mean_luminance_change, 4),
        reasons=reasons,
    )
