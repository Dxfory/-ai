from PIL import Image, ImageDraw, ImageOps

from backend.services.fenran_masks import build_subject_mask, composite_subject_only
from backend.services.fenran_validation import FenranValidationThresholds, validate_fenran_stage


def _inputs(size=(80, 60)):
    original = Image.new("RGB", size, "white")
    ImageDraw.Draw(original).ellipse((15, 10, 55, 48), fill=(155, 175, 120))
    baimiao = Image.new("L", size, 255)
    ImageDraw.Draw(baimiao).ellipse((15, 10, 55, 48), outline=0, width=2)
    return original, baimiao


def test_composite_preserves_every_pixel_outside_subject_mask():
    original, baimiao = _inputs()
    mask = build_subject_mask(baimiao, original)
    previous = Image.new("RGB", original.size, (248, 246, 238))
    generated = Image.new("RGB", original.size, (40, 80, 120))

    composited = composite_subject_only(generated, previous, mask, feather_radius=0)
    outside = ImageOps.invert(mask)

    assert Image.composite(composited, previous, outside).tobytes() == previous.tobytes()
    assert composited.getpixel((35, 30)) == (40, 80, 120)


def test_colored_paper_is_not_mistaken_for_full_canvas_subject():
    original = Image.new("RGB", (100, 80), (235, 225, 210))
    ImageDraw.Draw(original).ellipse((30, 20, 70, 60), fill=(120, 145, 95))
    baimiao = Image.new("L", original.size, 255)
    ImageDraw.Draw(baimiao).ellipse((30, 20, 70, 60), outline=0, width=2)

    mask = build_subject_mask(baimiao, original)
    covered = sum(mask.histogram()[128:]) / (mask.width * mask.height)

    assert mask.getpixel((5, 5)) == 0
    assert mask.getpixel((50, 40)) == 255
    assert covered < 0.65


def test_validation_fails_canvas_mismatch():
    original, baimiao = _inputs()
    mask = build_subject_mask(baimiao, original)

    result = validate_fenran_stage(
        stage_id="stage_01_first_fenran",
        previous=original,
        current=Image.new("RGB", (79, 60), "white"),
        expected_subject_mask=mask,
        canonical_size=original.size,
        thresholds=FenranValidationThresholds(),
    )

    assert result.passed is False
    assert result.canvas_match is False
    assert "canvas_size_mismatch" in result.reasons


def test_validation_fails_when_stage_does_not_change_subject():
    original, baimiao = _inputs()
    mask = build_subject_mask(baimiao, original)

    result = validate_fenran_stage(
        stage_id="stage_02_deepen_fenran",
        previous=original,
        current=original.copy(),
        expected_subject_mask=mask,
        canonical_size=original.size,
        thresholds=FenranValidationThresholds(min_stage_change_ratio=0.01),
    )

    assert result.passed is False
    assert "stage_change_below_threshold" in result.reasons


def test_validation_passes_changed_subject_with_stable_background():
    original, baimiao = _inputs()
    mask = build_subject_mask(baimiao, original)
    generated = Image.new("RGB", original.size, (80, 110, 95))
    current = composite_subject_only(generated, original, mask, feather_radius=0)

    result = validate_fenran_stage(
        stage_id="stage_01_first_fenran",
        previous=original,
        current=current,
        expected_subject_mask=mask,
        canonical_size=original.size,
        thresholds=FenranValidationThresholds(min_stage_change_ratio=0.01),
    )

    assert result.passed is True
    assert result.outside_subject_change_ratio == 0.0
    assert result.subject_bbox_iou >= 0.9


def test_validation_rejects_flat_fill_that_erases_internal_baimiao_structure():
    original, baimiao = _inputs()
    ImageDraw.Draw(baimiao).line((20, 30, 50, 30), fill=0, width=2)
    mask = build_subject_mask(baimiao, original)
    flat = composite_subject_only(Image.new("RGB", original.size, (80, 80, 80)), original, mask, feather_radius=0)

    result = validate_fenran_stage(
        stage_id="stage_01_first_fenran",
        previous=baimiao.convert("RGB"),
        current=flat,
        expected_subject_mask=mask,
        expected_line_mask=ImageOps.invert(baimiao),
        canonical_size=original.size,
        thresholds=FenranValidationThresholds(min_line_retention_ratio=0.45),
    )

    assert result.passed is False
    assert result.line_retention_ratio < 0.45
    assert "line_retention_below_threshold" in result.reasons
