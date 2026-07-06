"""课程 API"""

import sys as _sys, os as _os
_sys.path.insert(0, r"C:\Users\wangy\Desktop\美育ai")

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import CourseModel, ArtworkModel, StepModel
from ..schemas import CourseSchema
from shared.utils import generate_uuid

router = APIRouter(prefix="/api/v1/courses", tags=["courses"])

@router.post("/generate", response_model=CourseSchema)
def generate_course(artwork_id: str, db: Session = Depends(get_db)):
    artwork = db.query(ArtworkModel).filter(ArtworkModel.id == artwork_id).first()
    if not artwork:
        raise HTTPException(status_code=404, detail="Artwork not found")
    course = CourseModel(
        id=generate_uuid(), artwork_id=artwork_id,
        genre=artwork.genre, method=artwork.method,
    )
    db.add(course); db.commit(); db.refresh(course)
    mock_titles = (
        ["构图定位","勾线","分染/皴擦","罩染","复勾调整"]
        if artwork.method == "gongbi"
        else ["构图定位","调色","画主体","穿枝干","调整画面"]
    )
    for i, t in enumerate(mock_titles):
        s = StepModel(
            id=generate_uuid(), course_id=course.id, step_num=i+1,
            title=t, instruction=f"Phase 1 将对接 AI 生成真实教学步骤",
        )
        db.add(s)
    db.commit(); db.refresh(course)
    return course

@router.get("/{course_id}", response_model=CourseSchema)
def get_course(course_id: str, db: Session = Depends(get_db)):
    course = db.query(CourseModel).filter(CourseModel.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    return course
