"""分染试用 API。

该路由与白描生成路由隔离：只读取已有白描结果，生成新的分染文件。
"""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import LineDraftModel, ReferenceUploadModel
from ..schemas import FenranGenerateRequest, FenranResultSchema, FenranStepSchema
from ..services.fenran import generate_fenran_steps
from shared.utils import generate_uuid

router = APIRouter(prefix="/api/v1/fenran", tags=["fenran"])


@router.post("/generate", response_model=FenranResultSchema)
def create_fenran(req: FenranGenerateRequest, db: Session = Depends(get_db)):
    reference = db.query(ReferenceUploadModel).filter(ReferenceUploadModel.id == req.reference_upload_id).first()
    if not reference:
        raise HTTPException(status_code=404, detail="Reference upload not found")

    draft = db.query(LineDraftModel).filter(LineDraftModel.id == req.line_draft_id).first()
    if not draft or draft.reference_upload_id != reference.id:
        raise HTTPException(status_code=404, detail="Line draft not found for reference")

    task_id = generate_uuid()
    rel_dir = Path("fenran_steps")
    output_dir = str(Path(settings.UPLOAD_DIR) / rel_dir)
    try:
        result = generate_fenran_steps(
            reference_path=reference.file_path,
            line_draft_path=draft.file_path,
            output_dir=output_dir,
            task_id=task_id,
            subject_hint=req.subject_hint,
            palette_hint=req.palette_hint,
            step_count=req.step_count,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Fenran generation failed: {exc}") from exc

    return FenranResultSchema(
        id=task_id,
        reference_upload_id=reference.id,
        line_draft_id=draft.id,
        preview_url=_file_url(rel_dir, task_id, result.preview_path),
        steps=[
            FenranStepSchema(
                step_num=step.step_num,
                title=step.title,
                instruction=step.instruction,
                image_url=_file_url(rel_dir, task_id, step.output_path),
            )
            for step in result.steps
        ],
        metadata=result.metadata,
    )


def _file_url(rel_dir: Path, task_id: str, path: str) -> str:
    filename = Path(path).name
    return f"/uploads/{rel_dir.as_posix()}/{task_id}/{filename}"
