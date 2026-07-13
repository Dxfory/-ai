"""Fenran training API."""

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from PIL import Image
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import LineDraftModel, ReferenceUploadModel
from ..schemas import FenranTrainingRenderRequest, FenranTrainingRenderSchema, LineDraftSchema
from ..services.fenran import generate_fenran_training_render
from shared.utils import generate_uuid, validate_image_format

router = APIRouter(prefix="/api/v1", tags=["fenran-training"])


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


@router.post("/fenran/training-renders", response_model=FenranTrainingRenderSchema)
def create_fenran_training_render(req: FenranTrainingRenderRequest, db: Session = Depends(get_db)):
    reference = db.query(ReferenceUploadModel).filter(ReferenceUploadModel.id == req.reference_upload_id).first()
    if not reference:
        raise HTTPException(status_code=404, detail="Reference upload not found")

    line_draft = db.query(LineDraftModel).filter(LineDraftModel.id == req.line_draft_id).first()
    if not line_draft or line_draft.reference_upload_id != reference.id:
        raise HTTPException(status_code=404, detail="Line draft not found for reference")

    sample_id = req.sample_id.strip() or generate_uuid()
    output_dir = str(Path(settings.UPLOAD_DIR) / "fenran_training")

    try:
        result = generate_fenran_training_render(
            reference.file_path,
            line_draft.file_path,
            output_dir,
            sample_id,
            teaching_goal=req.teaching_goal,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Fenran training render failed: {exc}") from exc

    file_url = _file_url_for_upload_path(result.output_path)
    return FenranTrainingRenderSchema(
        sample_id=sample_id,
        reference_upload_id=reference.id,
        line_draft_id=line_draft.id,
        file_url=file_url,
        metadata=result.parameters,
        created_at=line_draft.created_at,
    )


def _file_url_for_upload_path(path: str) -> str:
    upload_root = Path(settings.UPLOAD_DIR).resolve()
    output_path = Path(path).resolve()
    try:
        rel_path = output_path.relative_to(upload_root)
    except ValueError:
        rel_path = Path("fenran_training") / output_path.name
    return f"/uploads/{rel_path.as_posix()}"
