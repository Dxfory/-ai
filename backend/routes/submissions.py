"""作业提交 API"""

import sys as _sys, os as _os
_sys.path.insert(0, r"C:\Users\wangy\Desktop\美育ai")

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import SubmissionModel, StepModel
from ..schemas import SubmissionSchema, SubmissionCreateRequest, StepFeedbackSchema
from shared.utils import generate_uuid

router = APIRouter(prefix="/api/v1/submissions", tags=["submissions"])

@router.post("/", response_model=SubmissionSchema)
def submit(req: SubmissionCreateRequest, db: Session = Depends(get_db)):
    step = db.query(StepModel).filter(StepModel.id == req.step_id).first()
    if not step:
        raise HTTPException(status_code=404, detail="Step not found")
    sub = SubmissionModel(
        id=generate_uuid(), user_id=req.user_id,
        step_id=req.step_id, image_url=req.image_url,
    )
    db.add(sub); db.commit(); db.refresh(sub)
    return sub

@router.get("/{submission_id}", response_model=SubmissionSchema)
def get_submission(submission_id: str, db: Session = Depends(get_db)):
    sub = db.query(SubmissionModel).filter(SubmissionModel.id == submission_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")
    return sub

@router.post("/{submission_id}/feedback", response_model=SubmissionSchema)
def add_feedback(submission_id: str, fb: StepFeedbackSchema, db: Session = Depends(get_db)):
    sub = db.query(SubmissionModel).filter(SubmissionModel.id == submission_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")
    sub.feedback = fb.model_dump()
    sub.status = "graded"
    db.commit(); db.refresh(sub)
    return sub
