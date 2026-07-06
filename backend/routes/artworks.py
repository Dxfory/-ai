"""范本作品 API"""

import sys as _sys, os as _os
_sys.path.insert(0, r"C:\Users\wangy\Desktop\美育ai")

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import ArtworkModel
from ..schemas import ArtworkSchema, ArtworkCreateRequest
from shared.utils import generate_uuid

router = APIRouter(prefix="/api/v1/artworks", tags=["artworks"])

@router.post("/", response_model=ArtworkSchema)
def create_artwork(req: ArtworkCreateRequest, db: Session = Depends(get_db)):
    artwork = ArtworkModel(
        id=generate_uuid(), title=req.title, genre=req.genre,
        method=req.method, image_url=req.image_url,
        input_method=req.input_method,
    )
    db.add(artwork); db.commit(); db.refresh(artwork)
    return artwork

@router.get("/", response_model=list[ArtworkSchema])
def list_artworks(db: Session = Depends(get_db)):
    return db.query(ArtworkModel).all()

@router.get("/{artwork_id}", response_model=ArtworkSchema)
def get_artwork(artwork_id: str, db: Session = Depends(get_db)):
    artwork = db.query(ArtworkModel).filter(ArtworkModel.id == artwork_id).first()
    if not artwork:
        raise HTTPException(status_code=404, detail="Artwork not found")
    return artwork
