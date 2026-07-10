"""版权素材 API"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AssetModel
from ..schemas import AssetCreateRequest, AssetSchema
from shared.utils import generate_uuid

router = APIRouter(prefix="/api/v1/assets", tags=["assets"])


@router.post("/", response_model=AssetSchema)
def create_asset(req: AssetCreateRequest, db: Session = Depends(get_db)):
    asset = AssetModel(
        id=generate_uuid(),
        title=req.title,
        source_name=req.source_name,
        source_url=req.source_url,
        license_type=req.license_type,
        license_url=req.license_url,
        attribution_text=req.attribution_text,
        display_allowed=req.display_allowed,
        train_allowed=req.train_allowed,
        commercial_allowed=req.commercial_allowed,
        derivative_allowed=req.derivative_allowed,
        risk_level=req.risk_level,
        file_hash=req.file_hash,
        image_url=req.image_url,
        metadata_=req.metadata,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return _to_schema(asset)


@router.get("/", response_model=list[AssetSchema])
def list_assets(
    risk_level: str | None = None,
    display_allowed: bool | None = Query(default=None),
    train_allowed: bool | None = Query(default=None),
    db: Session = Depends(get_db),
):
    query = db.query(AssetModel)
    if risk_level:
        query = query.filter(AssetModel.risk_level == risk_level)
    if display_allowed is not None:
        query = query.filter(AssetModel.display_allowed == display_allowed)
    if train_allowed is not None:
        query = query.filter(AssetModel.train_allowed == train_allowed)
    return [_to_schema(asset) for asset in query.all()]


@router.get("/{asset_id}", response_model=AssetSchema)
def get_asset(asset_id: str, db: Session = Depends(get_db)):
    asset = db.query(AssetModel).filter(AssetModel.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    return _to_schema(asset)


def _to_schema(asset: AssetModel) -> AssetSchema:
    return AssetSchema(
        id=asset.id,
        title=asset.title,
        source_name=asset.source_name,
        source_url=asset.source_url,
        license_type=asset.license_type,
        license_url=asset.license_url,
        attribution_text=asset.attribution_text,
        display_allowed=asset.display_allowed,
        train_allowed=asset.train_allowed,
        commercial_allowed=asset.commercial_allowed,
        derivative_allowed=asset.derivative_allowed,
        risk_level=asset.risk_level,
        file_hash=asset.file_hash,
        image_url=asset.image_url,
        metadata=asset.metadata_ or {},
        created_at=asset.created_at,
    )
