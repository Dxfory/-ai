"""工笔花鸟白描临摹 MVP API"""

import os
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import LineDraftModel, PracticeSessionModel, PracticeStepRunModel, ReferenceUploadModel
from ..schemas import (
    ColorStepGenerateRequest,
    GeneratedStepImageSchema,
    LineDraftGenerateRequest,
    LineDraftSchema,
    PracticeSessionCreateRequest,
    PracticeSessionSchema,
    PracticeStepRunSchema,
    ReferenceUploadSchema,
)
from ..services.line_draft import (
    generate_ai_baimiao,
    generate_ai_fenran,
    generate_line_draft,
    generate_local_fenran_preview,
    generate_overlay,
)
from shared.utils import generate_uuid, validate_image_format

router = APIRouter(prefix="/api/v1", tags=["gongbi-practice"])


GONGBI_FLOWER_BIRD_STEPS = [
    {
        "title": "白描稿与构图定位",
        "instruction": "观察白描稿的主体位置、外轮廓和比例。先轻轻定出大形，不急着画细节。",
        "checklist": ["主体位置是否准确？", "花瓣/叶片/鸟身比例是否接近？", "外轮廓是否太大或太小？"],
        "common_mistakes": ["一开始画细节", "主体整体偏移", "局部比例被放大"],
    },
    {
        "title": "勾线",
        "instruction": "用中锋稳定勾主轮廓和关键结构线。线条要慢、稳、不断续。",
        "checklist": ["是否中锋行笔？", "主轮廓是否完整？", "关键结构线是否清楚？"],
        "common_mistakes": ["反复描线", "线条断续", "勾线偏离白描稿"],
    },
    {
        "title": "分染",
        "instruction": "从浅色开始，花瓣、叶片或鸟身按结构由浅入深分染，过渡要慢。",
        "checklist": ["是否由浅入深？", "过渡是否自然？", "是否保留了线条？"],
        "common_mistakes": ["颜色一次上太重", "过渡生硬", "分染压住线条"],
    },
    {
        "title": "罩染",
        "instruction": "用淡色统一局部色调。每层要薄，干透后再加下一层。",
        "checklist": ["颜色是否淡而透？", "是否等上一层干透？", "线条是否仍然清楚？"],
        "common_mistakes": ["罩染过厚", "色块不均", "线条被压住"],
    },
    {
        "title": "提染与细节调整",
        "instruction": "加强花心、叶脉、羽毛等局部层次。只提关键处，避免越画越满。",
        "checklist": ["重点是否明确？", "细节是否顺着结构？", "局部层次是否太黑？"],
        "common_mistakes": ["细节过密", "层次死黑", "局部脱离大结构"],
    },
    {
        "title": "复勾与完成检查",
        "instruction": "轻复关键轮廓，检查整体疏密、透明感和完成度。宁少勿多。",
        "checklist": ["是否只复勾关键线？", "整体疏密是否舒服？", "画面是否还有透明感？"],
        "common_mistakes": ["复勾过重", "所有线都重新描一遍", "最后调整过多"],
    },
]


@router.post("/uploads/reference", response_model=ReferenceUploadSchema)
def upload_reference(
    file: UploadFile = File(...),
    notes: str = Form(default=""),
    consent_scope: str = Form(default="personal_analysis"),
    db: Session = Depends(get_db),
):
    if not file.filename or not validate_image_format(file.filename):
        raise HTTPException(status_code=400, detail="Unsupported image format")

    upload_id = generate_uuid()
    ext = file.filename.rsplit(".", 1)[-1].lower()
    rel_path = Path("references") / f"{upload_id}.{ext}"
    file_path = Path(settings.UPLOAD_DIR) / rel_path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with file_path.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    reference = ReferenceUploadModel(
        id=upload_id,
        original_filename=file.filename,
        file_path=str(file_path),
        file_url=f"/uploads/{rel_path.as_posix()}",
        consent_scope=consent_scope,
        notes=notes,
        metadata_={"content_type": file.content_type or ""},
    )
    db.add(reference)
    db.commit()
    db.refresh(reference)
    return _reference_schema(reference)


@router.post("/line-drafts/generate", response_model=LineDraftSchema)
def create_line_draft(req: LineDraftGenerateRequest, db: Session = Depends(get_db)):
    reference = db.query(ReferenceUploadModel).filter(ReferenceUploadModel.id == req.reference_upload_id).first()
    if not reference:
        raise HTTPException(status_code=404, detail="Reference upload not found")

    draft_id = generate_uuid()
    rel_dir = Path("line_drafts")
    output_dir = str(Path(settings.UPLOAD_DIR) / rel_dir)
    try:
        if req.provider == "ai_baimiao":
            result = generate_ai_baimiao(
                reference.file_path,
                output_dir,
                draft_id,
                prompt=req.prompt,
            )
        elif req.provider == "local_edge_preview":
            result = generate_line_draft(
                reference.file_path,
                output_dir,
                draft_id,
                line_strength=req.line_strength,
                detail_level=req.detail_level,
                preserve_texture=req.preserve_texture,
            )
        else:
            raise HTTPException(status_code=400, detail="Unsupported line draft provider")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Line draft generation failed: {exc}") from exc
    draft = LineDraftModel(
        id=draft_id,
        reference_upload_id=reference.id,
        file_path=result.output_path,
        file_url=f"/uploads/{rel_dir.as_posix()}/{draft_id}.png",
        line_strength=req.line_strength,
        detail_level=req.detail_level,
        preserve_texture=req.preserve_texture,
        provider=req.provider,
        metadata_=result.parameters | {"width": result.width, "height": result.height},
    )
    db.add(draft)
    db.commit()
    db.refresh(draft)
    return _line_draft_schema(draft)


@router.get("/line-drafts/{draft_id}", response_model=LineDraftSchema)
def get_line_draft(draft_id: str, db: Session = Depends(get_db)):
    draft = db.query(LineDraftModel).filter(LineDraftModel.id == draft_id).first()
    if not draft:
        raise HTTPException(status_code=404, detail="Line draft not found")
    return _line_draft_schema(draft)


@router.post("/color-steps/generate", response_model=GeneratedStepImageSchema)
def create_color_step_image(req: ColorStepGenerateRequest, db: Session = Depends(get_db)):
    if req.step_type != "fenran":
        raise HTTPException(status_code=400, detail="Unsupported color step type")

    reference = db.query(ReferenceUploadModel).filter(ReferenceUploadModel.id == req.reference_upload_id).first()
    if not reference:
        raise HTTPException(status_code=404, detail="Reference upload not found")
    draft = db.query(LineDraftModel).filter(LineDraftModel.id == req.line_draft_id).first()
    if not draft or draft.reference_upload_id != reference.id:
        raise HTTPException(status_code=404, detail="Line draft not found for reference")

    step_id = generate_uuid()
    rel_dir = Path("color_steps")
    output_dir = str(Path(settings.UPLOAD_DIR) / rel_dir)
    try:
        if req.provider == "ai_fenran":
            result = generate_ai_fenran(
                reference.file_path,
                draft.file_path,
                output_dir,
                step_id,
                prompt=req.prompt,
            )
        elif req.provider == "local_fenran_preview":
            result = generate_local_fenran_preview(
                reference.file_path,
                draft.file_path,
                output_dir,
                step_id,
            )
        else:
            raise HTTPException(status_code=400, detail="Unsupported color step provider")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Color step generation failed: {exc}") from exc

    return GeneratedStepImageSchema(
        id=step_id,
        reference_upload_id=reference.id,
        line_draft_id=draft.id,
        step_type=req.step_type,
        file_url=f"/uploads/{rel_dir.as_posix()}/{step_id}.png",
        provider=req.provider,
        metadata=result.parameters | {"width": result.width, "height": result.height},
    )


@router.post("/practice-sessions/", response_model=PracticeSessionSchema)
def create_practice_session(req: PracticeSessionCreateRequest, db: Session = Depends(get_db)):
    reference = db.query(ReferenceUploadModel).filter(ReferenceUploadModel.id == req.reference_upload_id).first()
    draft = db.query(LineDraftModel).filter(LineDraftModel.id == req.line_draft_id).first()
    if not reference:
        raise HTTPException(status_code=404, detail="Reference upload not found")
    if not draft or draft.reference_upload_id != reference.id:
        raise HTTPException(status_code=404, detail="Line draft not found for reference")

    session = PracticeSessionModel(
        id=generate_uuid(),
        reference_upload_id=reference.id,
        line_draft_id=draft.id,
        title=req.title,
    )
    db.add(session)
    db.flush()
    for index, step in enumerate(GONGBI_FLOWER_BIRD_STEPS, start=1):
        db.add(PracticeStepRunModel(
            id=generate_uuid(),
            session_id=session.id,
            step_num=index,
            title=step["title"],
            instruction=step["instruction"],
            checklist=step["checklist"],
            common_mistakes=step["common_mistakes"],
            status="active" if index == 1 else "pending",
        ))
    db.commit()
    db.refresh(session)
    return _session_schema(session)


@router.get("/practice-sessions/{session_id}", response_model=PracticeSessionSchema)
def get_practice_session(session_id: str, db: Session = Depends(get_db)):
    session = db.query(PracticeSessionModel).filter(PracticeSessionModel.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Practice session not found")
    return _session_schema(session)


@router.post("/practice-steps/{step_run_id}/submission", response_model=PracticeStepRunSchema)
def upload_practice_step_submission(
    step_run_id: str,
    file: UploadFile = File(...),
    notes: str = Form(default=""),
    db: Session = Depends(get_db),
):
    step = db.query(PracticeStepRunModel).filter(PracticeStepRunModel.id == step_run_id).first()
    if not step:
        raise HTTPException(status_code=404, detail="Practice step not found")
    if not file.filename or not validate_image_format(file.filename):
        raise HTTPException(status_code=400, detail="Unsupported image format")

    ext = file.filename.rsplit(".", 1)[-1].lower()
    rel_submission = Path("practice_submissions") / f"{step.id}.{ext}"
    submission_path = Path(settings.UPLOAD_DIR) / rel_submission
    submission_path.parent.mkdir(parents=True, exist_ok=True)
    with submission_path.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    rel_overlay = Path("overlays") / f"{step.id}.png"
    overlay_path = Path(settings.UPLOAD_DIR) / rel_overlay
    reference_path = _step_reference_path(step)
    overlay_meta = generate_overlay(reference_path, str(submission_path), str(overlay_path))

    step.submission_image_path = str(submission_path)
    step.submission_image_url = f"/uploads/{rel_submission.as_posix()}"
    step.overlay_image_path = str(overlay_path)
    step.overlay_image_url = f"/uploads/{rel_overlay.as_posix()}"
    step.notes = notes
    step.status = "review"
    db.commit()
    db.refresh(step)
    return _step_schema(step, extra_notes=overlay_meta)


@router.post("/practice-steps/{step_run_id}/continue", response_model=PracticeSessionSchema)
def continue_practice_step(step_run_id: str, db: Session = Depends(get_db)):
    step = db.query(PracticeStepRunModel).filter(PracticeStepRunModel.id == step_run_id).first()
    if not step:
        raise HTTPException(status_code=404, detail="Practice step not found")
    session = step.session
    step.status = "completed"
    next_step = (
        db.query(PracticeStepRunModel)
        .filter(PracticeStepRunModel.session_id == session.id, PracticeStepRunModel.step_num == step.step_num + 1)
        .first()
    )
    if next_step:
        next_step.status = "active"
        session.current_step_num = next_step.step_num
    else:
        session.status = "completed"
    db.commit()
    db.refresh(session)
    return _session_schema(session)


@router.post("/practice-steps/{step_run_id}/retry", response_model=PracticeStepRunSchema)
def retry_practice_step(step_run_id: str, db: Session = Depends(get_db)):
    step = db.query(PracticeStepRunModel).filter(PracticeStepRunModel.id == step_run_id).first()
    if not step:
        raise HTTPException(status_code=404, detail="Practice step not found")
    step.status = "needs_revision"
    db.commit()
    db.refresh(step)
    return _step_schema(step)


def _step_reference_path(step: PracticeStepRunModel) -> str:
    session = step.session
    if step.step_num <= 2:
        return session.line_draft.file_path
    return session.reference.file_path


def _reference_schema(reference: ReferenceUploadModel) -> ReferenceUploadSchema:
    return ReferenceUploadSchema(
        id=reference.id,
        original_filename=reference.original_filename,
        file_url=reference.file_url,
        consent_scope=reference.consent_scope,
        notes=reference.notes,
        metadata=reference.metadata_ or {},
        created_at=reference.created_at,
    )


def _line_draft_schema(draft: LineDraftModel) -> LineDraftSchema:
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


def _step_schema(step: PracticeStepRunModel, extra_notes: dict | None = None) -> PracticeStepRunSchema:
    notes = step.notes
    if extra_notes:
        notes = f"{notes} | overlay={extra_notes}"
    return PracticeStepRunSchema(
        id=step.id,
        session_id=step.session_id,
        step_num=step.step_num,
        title=step.title,
        instruction=step.instruction,
        checklist=step.checklist or [],
        common_mistakes=step.common_mistakes or [],
        status=step.status,
        submission_image_url=step.submission_image_url,
        overlay_image_url=step.overlay_image_url,
        notes=notes,
    )


def _session_schema(session: PracticeSessionModel) -> PracticeSessionSchema:
    return PracticeSessionSchema(
        id=session.id,
        reference_upload_id=session.reference_upload_id,
        line_draft_id=session.line_draft_id,
        title=session.title,
        status=session.status,
        current_step_num=session.current_step_num,
        steps=[_step_schema(step) for step in session.step_runs],
        created_at=session.created_at,
    )
