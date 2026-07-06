"""课程 API — 使用真实课程模板引擎"""
import sys as _sys, os as _os
_sys.path.insert(0, r"C:\Users\wangy\Desktop\美育ai")

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from dataclasses import asdict
from ..database import get_db
from ..models import CourseModel, ArtworkModel, StepModel
from ..schemas import CourseSchema
from ..services.course_templates import get_course_steps, get_method_material_brief
from shared.utils import generate_uuid

router = APIRouter(prefix="/api/v1/courses", tags=["courses"])

def _serialize_materials(materials):
    """将 MaterialItem 对象转为可 JSON 序列化的 dict"""
    return [asdict(m) if hasattr(m, '__dataclass_fields__') else m for m in materials]

@router.post("/generate", response_model=CourseSchema)
def generate_course(artwork_id: str, db: Session = Depends(get_db)):
    artwork = db.query(ArtworkModel).filter(ArtworkModel.id == artwork_id).first()
    if not artwork:
        raise HTTPException(status_code=404, detail="Artwork not found")
    template_steps = get_course_steps(artwork.method, artwork.genre)
    course = CourseModel(
        id=generate_uuid(), artwork_id=artwork_id,
        genre=artwork.genre, method=artwork.method,
    )
    db.add(course); db.commit(); db.refresh(course)
    for i, ts in enumerate(template_steps):
        s = StepModel(
            id=generate_uuid(), course_id=course.id, step_num=i+1,
            title=ts["title"], instruction=ts["instruction"],
            checklist=ts.get("checklist", []),
            materials=_serialize_materials(ts.get("materials", [])),
            common_mistakes=ts.get("common_mistakes", []),
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

@router.get("/{course_id}/materials")
def get_course_materials(course_id: str, db: Session = Depends(get_db)):
    course = db.query(CourseModel).filter(CourseModel.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    result = get_method_material_brief(course.method, course.genre)
    return {k: [asdict(m) for m in v] for k, v in result.items()}