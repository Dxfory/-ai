"""Independent Fenran training render service.

Fenran consumes an original artwork image plus an already-generated line draft.
It keeps the white-draft file immutable, prepares a color evidence bundle,
asks a GPT-image compatible model to do the teaching render, and preserves the
model's final teaching layout without re-overlaying the system line draft.
"""

from __future__ import annotations

import json
import math
import os
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

from .fenran_cache import build_fenran_cache_key, load_cached_manifest, save_cache_record
from .fenran_canvas import (
    _place_on_fenran_generation_canvas,
    _resolve_fenran_generation_canvas,
    _restore_from_fenran_generation_canvas,
)
from .fenran_generation import (
    FenranConfigurationError,
    FenranProviderError,
    _post_fenran_image_edit,
    render_fenran_image,
)
from .fenran_masks import build_subject_mask, composite_subject_only
from .fenran_plan import PROMPT_VERSION, build_fenran_teaching_plan
from .fenran_validation import FenranValidationThresholds, validate_fenran_stage

RENDERER_VERSION = "fenran-renderer-v3"
BAIMIAO_CONTRACT_VERSION = "baimiao-output-contract-v1"
TECHNIQUE_TEMPLATE_VERSION = "fenran-cumulative-teaching-v2"
DEFAULT_IMAGE_MODEL = "gpt-image-2"
DEFAULT_API_BASE = "https://api.openai.com/v1"


@dataclass
class FenranTrainingRenderResult:
    output_path: str
    width: int
    height: int
    parameters: dict
    status: str = "ready"
    stages: list[dict] = field(default_factory=list)
    cache_hit: bool = False
    failed_stage: str | None = None
    reasons: list[str] = field(default_factory=list)


def generate_fenran_training_render(
    original_path: str,
    registered_baimiao_path: str | None = None,
    output_dir: str = "",
    sample_id: str = "",
    registration: dict | None = None,
    teaching_goal: str = "",
    include_base_color: bool = False,
    force_regenerate: bool = False,
    max_attempts: int | None = None,
    render_image: Callable[..., dict | str | None] | None = None,
    line_draft_path: str | None = None,
) -> FenranTrainingRenderResult:
    registered_baimiao_path = registered_baimiao_path or line_draft_path
    if not registered_baimiao_path:
        raise FenranConfigurationError("registered_baimiao_path is required")
    if not output_dir or not sample_id:
        raise FenranConfigurationError("output_dir and sample_id are required")

    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    original = ImageOps.exif_transpose(Image.open(original_path)).convert("RGB")
    registered_baimiao = _normalize_line_draft(
        ImageOps.exif_transpose(Image.open(registered_baimiao_path)).convert("L")
    )
    canonical_size = registered_baimiao.size
    if original.size != canonical_size:
        raise FenranConfigurationError(
            f"Approved original and registered baimiao must share canonical size: {original.size} != {canonical_size}"
        )

    registered_original = original.copy()
    registration = dict(registration or {})
    registration.setdefault("registration_id", "legacy-approved-input")
    registration.setdefault("status", "approved")
    registration.setdefault("requires_review", False)
    teaching_plan = build_fenran_teaching_plan(include_base_color=include_base_color)
    try:
        config = _resolve_config()
        if not config.fail_closed:
            raise FenranConfigurationError("FENRAN_FAIL_CLOSED must remain true for incomplete-result safety")
        if not config.preserve_canonical_coordinates:
            raise FenranConfigurationError("FENRAN_PRESERVE_CANONICAL_COORDINATES must remain true")
        canvas = _resolve_fenran_generation_canvas(
            canonical_size,
            image_size=config.image_size,
            max_side=config.api_max_image_side,
        )
    except (TypeError, ValueError) as exc:
        raise FenranConfigurationError(f"Invalid FENRAN configuration: {exc}") from exc
    try:
        thresholds = _resolve_validation_thresholds()
    except (TypeError, ValueError) as exc:
        raise FenranConfigurationError(f"Invalid FENRAN validation configuration: {exc}") from exc
    attempts_limit = max(1, min(5, max_attempts or config.max_attempts))
    cache_key = build_fenran_cache_key(
        original_path=original_path,
        registered_baimiao_path=registered_baimiao_path,
        registration_id=str(registration.get("registration_id", "")),
        include_base_color=include_base_color,
        teaching_plan_version=teaching_plan.version,
        prompt_version=PROMPT_VERSION,
        model=config.model,
        image_size=canvas.request_size,
        teaching_goal=teaching_goal,
        renderer_version=RENDERER_VERSION,
        api_base=config.base_url,
        validation_signature=json.dumps(asdict(thresholds), sort_keys=True),
        runtime_signature=(
            f"fallback={config.allow_single_reference_fallback}|"
            f"fail_closed={config.fail_closed}|canonical={config.preserve_canonical_coordinates}"
        ),
    )
    cache_root = output_root / ".cache"
    if config.enable_cache and not force_regenerate:
        cached_manifest_path = load_cached_manifest(cache_root, cache_key)
        if cached_manifest_path:
            return _result_from_manifest(cached_manifest_path, cache_hit=True)

    artifact_dir = output_root / sample_id
    artifact_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "registered_original": artifact_dir / "registered_original.png",
        "registered_baimiao": artifact_dir / "registered_baimiao.png",
        "generation_canvas": artifact_dir / "generation_canvas.json",
        "subject_mask": artifact_dir / "subject_mask.png",
        "teaching_plan": artifact_dir / "teaching_plan.json",
        "color_evidence_json": artifact_dir / "color_evidence.json",
        "prompt_bundle": artifact_dir / "prompt_bundle.json",
        "technique_graph": artifact_dir / "technique_graph.json",
        "render_manifest": artifact_dir / "render_manifest.json",
    }
    registered_original.save(paths["registered_original"])
    registered_baimiao.save(paths["registered_baimiao"])

    color_mask = _build_color_mask(registered_original)
    palette = _extract_palette(registered_original)
    regions = _extract_regions(registered_original, color_mask)
    evidence = _build_color_evidence(
        original=original,
        aligned_original=registered_original,
        line_draft=registered_baimiao,
        palette=palette,
        regions=regions,
        registration=registration,
        teaching_goal=teaching_goal,
    )
    subject_mask = build_subject_mask(registered_baimiao, registered_original)
    expected_line_mask = ImageOps.invert(registered_baimiao)
    subject_mask.save(paths["subject_mask"])
    prompt_bundle = {
        "prompt_version": PROMPT_VERSION,
        "teaching_goal": teaching_goal,
        "stages": {stage.stage_id: stage.prompt for stage in teaching_plan.stages},
    }
    _write_json(paths["generation_canvas"], canvas.to_dict())
    _write_json(paths["teaching_plan"], teaching_plan.to_dict())
    _write_json(paths["color_evidence_json"], evidence)
    _write_json(paths["prompt_bundle"], prompt_bundle)

    selected_stages: list[dict] = []
    previous_path = paths["registered_baimiao"]
    previous_image = registered_baimiao.convert("RGB")
    provider_modes: list[dict] = []

    for stage in teaching_plan.stages:
        stage_dir = artifact_dir / stage.stage_id
        stage_dir.mkdir(parents=True, exist_ok=True)
        passed_attempts: list[tuple[float, Path, dict]] = []
        best_failed: tuple[float, Path, dict] | None = None
        for attempt_number in range(1, attempts_limit + 1):
            prefix = f"attempt_{attempt_number:02d}"
            raw_path = stage_dir / f"{prefix}_raw.png"
            restored_path = stage_dir / f"{prefix}_restored.png"
            composited_path = stage_dir / f"{prefix}_composited.png"
            validation_path = stage_dir / f"{prefix}_validation.json"
            canonical_inputs = [str(previous_path), str(paths["registered_original"])]
            canonical_images = [previous_image, registered_original]
            if stage.stage_id != "stage_00_base_color":
                canonical_inputs.append(str(paths["registered_baimiao"]))
                canonical_images.append(registered_baimiao)
            provider_inputs = _write_provider_inputs(
                stage_dir=stage_dir,
                prefix=prefix,
                canonical_inputs=canonical_images,
                canvas=canvas,
            )
            prompt = f"{stage.prompt}\n用户教学目标：{teaching_goal or '分染教学'}\n颜色证据：{json.dumps(evidence, ensure_ascii=False)}"
            if render_image is None:
                request_meta = render_fenran_image(
                    model=config.model,
                    prompt=prompt,
                    size=canvas.request_size,
                    image_paths=provider_inputs,
                    output_path=str(raw_path),
                    api_key=config.api_key,
                    base_url=config.base_url,
                    timeout_seconds=config.timeout_seconds,
                )
            else:
                injected = render_image(
                    model=config.model,
                    prompt=prompt,
                    size=canvas.request_size,
                    image_paths=canonical_inputs,
                    evidence=evidence,
                    output_path=str(raw_path),
                )
                request_meta = injected if isinstance(injected, dict) else {}
                if isinstance(injected, str):
                    raw_path = Path(injected)
                elif isinstance(injected, dict) and injected.get("raw_output_path"):
                    raw_path = Path(str(injected["raw_output_path"]))
            provider_modes.append({
                "stage_id": stage.stage_id,
                "attempt": attempt_number,
                "request_mode": request_meta.get("request_mode", "multi_image"),
                "input_image_count": len(canonical_inputs),
                "fallback_used": bool(request_meta.get("fallback_used", False)),
            })
            if not raw_path.exists():
                raise FenranProviderError("Fenran render did not produce a model output file")

            model_output = ImageOps.exif_transpose(Image.open(raw_path)).convert("RGB")
            if model_output.size == canvas.canvas_size:
                restored = _restore_from_fenran_generation_canvas(model_output, canvas)
            else:
                raise FenranProviderError(
                    f"Image provider returned {model_output.size}, expected canvas size {canvas.canvas_size}"
                )
            restored.save(restored_path)
            composited = composite_subject_only(restored, previous_image, subject_mask, feather_radius=0)
            composited.save(composited_path)
            validation = validate_fenran_stage(
                stage_id=stage.stage_id,
                previous=previous_image,
                current=composited,
                expected_subject_mask=subject_mask,
                expected_line_mask=expected_line_mask,
                canonical_size=canonical_size,
                thresholds=thresholds,
            )
            validation_payload = validation.to_dict()
            validation_payload["attempt"] = attempt_number
            _write_json(validation_path, validation_payload)
            candidate = (validation.score, composited_path, validation_payload)
            if validation.passed:
                passed_attempts.append(candidate)
            if best_failed is None or candidate[0] > best_failed[0]:
                best_failed = candidate
            if validation.passed:
                break

        if not passed_attempts:
            best_attempt_url = str(best_failed[1]) if best_failed else ""
            reasons = best_failed[2].get("reasons", []) if best_failed else ["no_attempt_output"]
            manifest = _build_manifest(
                sample_id=sample_id,
                status="review_required",
                output_path=best_attempt_url,
                canonical_size=canonical_size,
                stages=selected_stages,
                failed_stage=stage.stage_id,
                reasons=reasons,
                cache_key=cache_key,
                paths=paths,
                palette=palette,
                teaching_goal=teaching_goal,
                config=config,
                registration=registration,
                provider_modes=provider_modes,
            )
            _write_json(paths["render_manifest"], manifest)
            return _result_from_manifest(paths["render_manifest"], cache_hit=False)

        _, selected_source, selected_validation = max(passed_attempts, key=lambda item: item[0])
        selected_path = stage_dir / "selected.png"
        shutil.copyfile(selected_source, selected_path)
        previous_path = selected_path
        previous_image = Image.open(selected_path).convert("RGB")
        selected_stages.append({
            "stage_id": stage.stage_id,
            "title": stage.title,
            "technique": stage.technique,
            "pigments": list(stage.pigments),
            "output_path": str(selected_path),
            "status": "ready",
            "validation": selected_validation,
        })

    technique_graph = {
        "version": TECHNIQUE_TEMPLATE_VERSION,
        "stages": [{"stage_id": stage["stage_id"], "status": stage["status"]} for stage in selected_stages],
        "line_overlay_applied": False,
    }
    _write_json(paths["technique_graph"], technique_graph)
    manifest = _build_manifest(
        sample_id=sample_id,
        status="ready",
        output_path=str(previous_path),
        canonical_size=canonical_size,
        stages=selected_stages,
        failed_stage=None,
        reasons=[],
        cache_key=cache_key,
        paths=paths,
        palette=palette,
        teaching_goal=teaching_goal,
        config=config,
        registration=registration,
        provider_modes=provider_modes,
    )
    _write_json(paths["render_manifest"], manifest)
    if config.enable_cache:
        save_cache_record(cache_root, cache_key, paths["render_manifest"])
    return _result_from_manifest(paths["render_manifest"], cache_hit=False)


@dataclass
class _FenranConfig:
    api_key: str | None
    base_url: str
    model: str
    image_size: str
    timeout_seconds: float
    max_attempts: int
    api_max_image_side: int
    enable_cache: bool
    fail_closed: bool
    allow_single_reference_fallback: bool
    preserve_canonical_coordinates: bool


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
    return _FenranConfig(
        api_key=api_key,
        base_url=base_url,
        model=model,
        image_size=os.getenv("FENRAN_IMAGE_SIZE", "auto").strip() or "auto",
        timeout_seconds=float(os.getenv("FENRAN_IMAGE_TIMEOUT_SECONDS", "240")),
        max_attempts=max(1, min(5, int(os.getenv("FENRAN_MAX_ATTEMPTS", "3")))),
        api_max_image_side=max(1024, int(os.getenv("FENRAN_API_MAX_IMAGE_SIDE", "1536"))),
        enable_cache=_env_bool("FENRAN_ENABLE_CACHE", True),
        fail_closed=_env_bool("FENRAN_FAIL_CLOSED", True),
        allow_single_reference_fallback=_env_bool("FENRAN_ALLOW_SINGLE_REFERENCE_FALLBACK", False),
        preserve_canonical_coordinates=_env_bool("FENRAN_PRESERVE_CANONICAL_COORDINATES", True),
    )


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _resolve_validation_thresholds() -> FenranValidationThresholds:
    return FenranValidationThresholds(
        min_subject_bbox_iou=float(os.getenv("FENRAN_MIN_SUBJECT_BBOX_IOU", "0.90")),
        max_subject_center_shift_ratio=float(os.getenv("FENRAN_MAX_SUBJECT_CENTER_SHIFT_RATIO", "0.02")),
        max_subject_size_change_ratio=float(os.getenv("FENRAN_MAX_SUBJECT_SIZE_CHANGE_RATIO", "0.04")),
        min_subject_coverage=float(os.getenv("FENRAN_MIN_SUBJECT_COVERAGE", "0.92")),
        max_outside_subject_change_ratio=float(os.getenv("FENRAN_MAX_OUTSIDE_SUBJECT_CHANGE_RATIO", "0.01")),
        min_validation_score=float(os.getenv("FENRAN_MIN_VALIDATION_SCORE", "0.80")),
        min_line_retention_ratio=float(os.getenv("FENRAN_MIN_LINE_RETENTION_RATIO", "0.35")),
    )


def _write_provider_inputs(*, stage_dir: Path, prefix: str, canonical_inputs: list[Image.Image], canvas) -> list[str]:
    paths = []
    for index, image in enumerate(canonical_inputs):
        destination = stage_dir / f"{prefix}_input_{index + 1}.png"
        resampling = Image.Resampling.NEAREST if image.mode == "L" else Image.Resampling.LANCZOS
        _place_on_fenran_generation_canvas(image, canvas, resample=resampling).save(destination)
        paths.append(str(destination))
    return paths


def _build_manifest(
    *,
    sample_id: str,
    status: str,
    output_path: str,
    canonical_size: tuple[int, int],
    stages: list[dict],
    failed_stage: str | None,
    reasons: list[str],
    cache_key: str,
    paths: dict,
    palette: list[str],
    teaching_goal: str,
    config: _FenranConfig,
    registration: dict,
    provider_modes: list[dict],
) -> dict:
    return {
        "sample_id": sample_id,
        "created_at": _utc_now(),
        "status": status,
        "output_path": output_path,
        "canonical_width": canonical_size[0],
        "canonical_height": canonical_size[1],
        "stages": stages,
        "failed_stage": failed_stage,
        "reasons": reasons,
        "cache_key": cache_key,
        "renderer_version": RENDERER_VERSION,
        "baimiao_version": BAIMIAO_CONTRACT_VERSION,
        "technique_template_version": TECHNIQUE_TEMPLATE_VERSION,
        "prompt_version": PROMPT_VERSION,
        "model": config.model,
        "api_base": config.base_url,
        "line_draft_modified": False,
        "registered_baimiao_modified": False,
        "line_overlay_applied": False,
        "fallback_used": any(item["fallback_used"] for item in provider_modes),
        "fail_closed": config.fail_closed,
        "preserve_canonical_coordinates": config.preserve_canonical_coordinates,
        "requests": provider_modes,
        "registration": registration,
        "artifacts": {key: str(path) for key, path in paths.items()},
        "palette": palette,
        "teaching_goal": teaching_goal,
    }


def _result_from_manifest(manifest_path: Path, *, cache_hit: bool) -> FenranTrainingRenderResult:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    output_path = manifest.get("output_path", "")
    parameters = {key: value for key, value in manifest.items() if key not in {"stages", "output_path"}}
    parameters["artifacts"] = manifest.get("artifacts", {}) | {"render_manifest": str(manifest_path)}
    return FenranTrainingRenderResult(
        output_path=output_path,
        width=int(manifest["canonical_width"]),
        height=int(manifest["canonical_height"]),
        parameters=parameters,
        status=manifest.get("status", "review_required"),
        stages=manifest.get("stages", []),
        cache_hit=cache_hit,
        failed_stage=manifest.get("failed_stage"),
        reasons=manifest.get("reasons", []),
    )


def _render_fenran_with_openai_compatible_api(*, request: dict, api_key: str | None, base_url: str) -> dict:
    return render_fenran_image(
        model=request["model"],
        prompt=request["prompt"],
        size=request["size"],
        image_paths=request.get("api_image_paths") or request["image_paths"],
        output_path=request["output_path"],
        api_key=api_key,
        base_url=base_url,
        timeout_seconds=_image_timeout_seconds(),
        fallback_image_path=request.get("fallback_image_path"),
    )


def _post_fenran_multi_image_edit(client: httpx.Client, url: str, headers: dict, data: dict, image_paths: list[str]) -> httpx.Response:
    return _post_fenran_image_edit(client, url, headers, data, image_paths)


def _build_color_mask(original: Image.Image) -> Image.Image:
    gray = ImageOps.grayscale(original)
    mask = gray.point(lambda value: 255 if value < 246 else 0)
    mask = mask.filter(ImageFilter.MaxFilter(size=3))
    return mask.filter(ImageFilter.GaussianBlur(radius=max(1.0, min(original.size) / 140)))


def _normalize_line_draft(line_draft: Image.Image) -> Image.Image:
    clean = line_draft.convert("L")
    return clean.point(lambda value: 0 if value < 200 else 255)


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
                "needs_review": bool(registration.get("requires_review", False)),
            "notes": ["preserve_line_draft", "no_crop", "no_resize_asymmetric"],
        },
        "contract_version": BAIMIAO_CONTRACT_VERSION,
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
