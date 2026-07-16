"""Fenran training API."""

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from PIL import Image, ImageOps
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import LineDraftModel, ReferenceUploadModel
from ..schemas import FenranStageRenderSchema, FenranTrainingRenderRequest, FenranTrainingRenderSchema, LineDraftSchema
from ..services.fenran import generate_fenran_training_render
from ..services.fenran_generation import FenranConfigurationError, FenranProviderError
from shared.utils import generate_uuid, validate_image_format

router = APIRouter(prefix="/api/v1", tags=["fenran-training"])


class RegistrationApproveRequest(BaseModel):
    registration_id: str


@router.post("/line-drafts/upload", response_model=LineDraftSchema)
def upload_line_draft(
    reference_upload_id: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    reference = db.query(ReferenceUploadModel).filter(ReferenceUploadModel.id == reference_upload_id).first()
    if not reference:
        raise HTTPException(status_code=404, detail="Reference upload not found")
    if not file.filename or not validate_image_format(file.filename):
        raise HTTPException(status_code=400, detail="Unsupported image format")

    draft_id = generate_uuid()
    ext = file.filename.rsplit(".", 1)[-1].lower()
    rel_dir = Path("line_drafts")
    file_path = Path(settings.UPLOAD_DIR) / rel_dir / f"{draft_id}.{ext}"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with file_path.open("wb") as out:
        out.write(file.file.read())

    with Image.open(file_path) as img:
        width, height = img.size

    draft = LineDraftModel(
        id=draft_id,
        reference_upload_id=reference.id,
        file_path=str(file_path),
        file_url=f"/uploads/{rel_dir.as_posix()}/{draft_id}.{ext}",
        line_strength=3,
        detail_level=3,
        preserve_texture=True,
        provider="user_upload",
        status="ready",
        metadata_={
            "source": "user_upload",
            "original_filename": file.filename,
            "content_type": file.content_type or "",
            "width": width,
            "height": height,
        },
    )
    db.add(draft)
    db.commit()
    db.refresh(draft)
    return LineDraftSchema(
        id=draft.id,
        reference_upload_id=draft.reference_upload_id,
        file_url=draft.file_url,
        line_strength=draft.line_strength,
        detail_level=draft.detail_level,
        preserve_texture=draft.preserve_texture,
        provider=draft.provider,
        status=draft.status,
        metadata=draft.metadata_ or {},
        created_at=draft.created_at,
    )


@router.post("/registrations/line-drafts/{line_draft_id}/auto")
def create_line_draft_registration(line_draft_id: str, db: Session = Depends(get_db)):
    line_draft = db.query(LineDraftModel).filter(LineDraftModel.id == line_draft_id).first()
    if not line_draft:
        raise HTTPException(status_code=404, detail="Line draft not found")
    reference = db.query(ReferenceUploadModel).filter(ReferenceUploadModel.id == line_draft.reference_upload_id).first()
    if not reference:
        raise HTTPException(status_code=404, detail="Reference upload not found")

    registration = _write_registration_candidate(reference, line_draft)
    metadata = dict(line_draft.metadata_ or {})
    candidates = dict(metadata.get("registration_candidates") or {})
    candidates[registration["registration_id"]] = registration
    metadata["registration_candidates"] = candidates
    metadata["registration_review"] = registration
    line_draft.metadata_ = metadata
    db.add(line_draft)
    db.commit()
    return registration


@router.post("/registrations/line-drafts/{line_draft_id}/approve")
def approve_line_draft_registration(
    line_draft_id: str,
    req: RegistrationApproveRequest,
    db: Session = Depends(get_db),
):
    line_draft = db.query(LineDraftModel).filter(LineDraftModel.id == line_draft_id).first()
    if not line_draft:
        raise HTTPException(status_code=404, detail="Line draft not found")

    metadata = dict(line_draft.metadata_ or {})
    candidates = metadata.get("registration_candidates") or {}
    registration = dict(candidates.get(req.registration_id) or {})
    if not registration:
        raise HTTPException(status_code=404, detail="Registration candidate not found")
    registered_path = Path(registration.get("registered_baimiao_path", ""))
    if not registered_path.exists():
        raise HTTPException(status_code=400, detail="Registered baimiao artifact is missing")

    registration["status"] = "approved"
    registration["requires_review"] = False
    metadata["registration"] = registration
    metadata["registration_review"] = registration
    line_draft.metadata_ = metadata
    db.add(line_draft)
    db.commit()
    return registration


@router.post("/fenran/training-renders", response_model=FenranTrainingRenderSchema)
def create_fenran_training_render(req: FenranTrainingRenderRequest, db: Session = Depends(get_db)):
    reference = db.query(ReferenceUploadModel).filter(ReferenceUploadModel.id == req.reference_upload_id).first()
    if not reference:
        raise HTTPException(status_code=404, detail="Reference upload not found")

    line_draft = db.query(LineDraftModel).filter(LineDraftModel.id == req.line_draft_id).first()
    if not line_draft or line_draft.reference_upload_id != reference.id:
        raise HTTPException(status_code=404, detail="Line draft not found for reference")

    registered_baimiao_path, registration = _resolve_registered_baimiao_path(line_draft)
    if not registered_baimiao_path:
        raise HTTPException(
            status_code=409,
            detail={
                "status": "registration_review",
                "message": "Approved registered_baimiao is required before fenran rendering",
                "line_draft_id": line_draft.id,
                "registration": registration or {},
            },
        )

    sample_id = req.sample_id.strip() or generate_uuid()
    output_dir = str(Path(settings.UPLOAD_DIR) / "fenran_training")

    try:
        result = generate_fenran_training_render(
            original_path=reference.file_path,
            registered_baimiao_path=str(registered_baimiao_path),
            output_dir=output_dir,
            sample_id=sample_id,
            registration=registration,
            teaching_goal=req.teaching_goal,
            include_base_color=req.include_base_color,
            force_regenerate=req.force_regenerate,
            max_attempts=req.max_attempts,
        )
    except FenranConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FenranProviderError as exc:
        raise HTTPException(status_code=502, detail=f"Fenran image provider failed: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Fenran training render failed: {exc}") from exc

    stages = [
        FenranStageRenderSchema(
            stage_id=stage["stage_id"],
            title=stage["title"],
            technique=stage["technique"],
            pigments=stage.get("pigments", []),
            file_url=_file_url_for_upload_path(stage["output_path"]),
            status=stage.get("status", "ready"),
            validation=stage.get("validation", {}),
        )
        for stage in result.stages
    ]
    if result.status == "review_required":
        raise HTTPException(
            status_code=422,
            detail={
                "status": "review_required",
                "failed_stage": result.failed_stage,
                "reasons": result.reasons,
                "best_attempt_url": _file_url_for_upload_path(result.output_path) if result.output_path else "",
                "completed_stages": [stage.model_dump() for stage in stages],
            },
        )

    file_url = _file_url_for_upload_path(result.output_path)
    return FenranTrainingRenderSchema(
        sample_id=str(result.parameters.get("sample_id", sample_id)),
        reference_upload_id=reference.id,
        line_draft_id=line_draft.id,
        canonical_width=result.width,
        canonical_height=result.height,
        stages=stages,
        file_url=file_url,
        status=result.status,
        cache_hit=result.cache_hit,
        metadata=result.parameters | {"registration": registration},
        created_at=line_draft.created_at,
    )


def _write_registration_candidate(reference: ReferenceUploadModel, line_draft: LineDraftModel) -> dict:
    original = ImageOps.exif_transpose(Image.open(reference.file_path)).convert("RGB")
    line = ImageOps.exif_transpose(Image.open(line_draft.file_path)).convert("L")
    canonical_size = original.size
    registration_id = generate_uuid()
    artifact_dir = Path(settings.UPLOAD_DIR) / "registrations" / line_draft.id / registration_id
    artifact_dir.mkdir(parents=True, exist_ok=True)

    global_registered = _fit_line_to_canonical_canvas(line, canonical_size)
    local_registered = global_registered.copy()
    global_overlay = _registration_overlay(original, global_registered)
    local_overlay = _registration_overlay(original, local_registered)

    global_registered_path = artifact_dir / "global_registered_baimiao.png"
    local_registered_path = artifact_dir / "local_registered_baimiao.png"
    global_overlay_path = artifact_dir / "global_overlay.png"
    local_overlay_path = artifact_dir / "local_overlay.png"
    control_points_path = artifact_dir / "control_points.json"
    result_path = artifact_dir / "registration_result.json"

    global_registered.save(global_registered_path)
    local_registered.save(local_registered_path)
    global_overlay.save(global_overlay_path)
    local_overlay.save(local_overlay_path)

    result = {
        "registration_id": registration_id,
        "status": "review_required",
        "canonical_size": [canonical_size[0], canonical_size[1]],
        "original_size": [original.width, original.height],
        "baimiao_size": [line.width, line.height],
        "global_transform": {
            "type": "identity" if line.size == canonical_size else "contain_to_canonical_canvas",
            "source_size": [line.width, line.height],
            "target_size": [canonical_size[0], canonical_size[1]],
        },
        "local_transform_uri": None,
        "control_points_uri": _upload_uri(control_points_path),
        "registered_baimiao_path": str(local_registered_path),
        "registered_baimiao_image_uri": _upload_uri(local_registered_path),
        "global_registered_baimiao_uri": _upload_uri(global_registered_path),
        "registration_overlay_uri": _upload_uri(local_overlay_path),
        "global_overlay_uri": _upload_uri(global_overlay_path),
        "registration_result_uri": _upload_uri(result_path),
        "registration_score": 0.5,
        "mean_boundary_error_px": None,
        "p95_boundary_error_px": None,
        "max_boundary_error_px": None,
        "landmark_error": {},
        "topology_mismatch_count": 0,
        "topology_issues": [],
        "requires_review": True,
        "line_overlay_applied": False,
        "version": "fenran-registration-review-v1",
    }
    _write_text_json(control_points_path, {"control_points": []})
    _write_text_json(result_path, result)
    return result


def _fit_line_to_canonical_canvas(line: Image.Image, canonical_size: tuple[int, int]) -> Image.Image:
    normalized = line.convert("L").point(lambda value: 0 if value < 200 else 255)
    if normalized.size == canonical_size:
        return normalized
    contained = ImageOps.contain(normalized, canonical_size, Image.Resampling.NEAREST)
    canvas = Image.new("L", canonical_size, 255)
    offset = ((canonical_size[0] - contained.width) // 2, (canonical_size[1] - contained.height) // 2)
    canvas.paste(contained, offset)
    return canvas


def _registration_overlay(original: Image.Image, line_draft: Image.Image) -> Image.Image:
    base = original.convert("RGBA")
    lines = Image.new("RGBA", line_draft.size, (0, 0, 0, 0))
    alpha = ImageOps.invert(line_draft).point(lambda value: min(255, max(0, value)))
    lines.putalpha(alpha)
    base.alpha_composite(lines)
    return base.convert("RGB")


def _write_text_json(path: Path, payload: dict) -> None:
    import json

    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _upload_uri(path: Path) -> str:
    upload_root = Path(settings.UPLOAD_DIR).resolve()
    try:
        rel_path = path.resolve().relative_to(upload_root)
    except ValueError:
        rel_path = path.name
    return f"/uploads/{rel_path.as_posix()}"

def _resolve_registered_baimiao_path(line_draft: LineDraftModel) -> tuple[Path | None, dict]:
    metadata = line_draft.metadata_ or {}
    registration = metadata.get("registration") or {}
    if registration.get("status") != "approved" or registration.get("requires_review") is True:
        return None, registration
    registered_path = registration.get("registered_baimiao_path")
    if not registered_path:
        return None, registration
    path = Path(registered_path)
    if not path.exists():
        return None, registration
    return path, registration


def _file_url_for_upload_path(path: str) -> str:
    upload_root = Path(settings.UPLOAD_DIR).resolve()
    output_path = Path(path).resolve()
    try:
        rel_path = output_path.relative_to(upload_root)
    except ValueError:
        rel_path = Path("fenran_training") / output_path.name
    return f"/uploads/{rel_path.as_posix()}"

