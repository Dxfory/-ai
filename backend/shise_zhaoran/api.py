"""Minimal API for the independent Shise Zhaoran stage."""

from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from PIL import Image

from ..config import settings
from shared.utils import generate_uuid, validate_image_format

from .schemas import ShiseUpstreamUploadResult, ShiseZhaoranRequest, ShiseZhaoranResult
from .service import ShiseZhaoranService


router = APIRouter(prefix="/api/v1/shise-zhaoran", tags=["shise-zhaoran"])


@router.post("/upstream", response_model=ShiseUpstreamUploadResult)
def upload_shise_upstream(file: UploadFile = File(...)) -> ShiseUpstreamUploadResult:
    if not file.filename or not validate_image_format(file.filename):
        raise HTTPException(status_code=400, detail="Unsupported image format")
    suffix = file.filename.rsplit(".", 1)[-1].lower()
    filename = f"{generate_uuid()}.{suffix}"
    path = Path(settings.UPLOAD_DIR) / "shise_zhaoran_inputs" / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(file.file.read())
    try:
        with Image.open(path) as image:
            width, height = image.size
    except Exception as exc:
        path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Invalid image file") from exc
    return ShiseUpstreamUploadResult(
        file_url=f"/uploads/shise_zhaoran_inputs/{filename}",
        original_filename=file.filename,
        width=width,
        height=height,
    )


@router.post("/generate", response_model=ShiseZhaoranResult)
def generate_shise_zhaoran(req: ShiseZhaoranRequest) -> ShiseZhaoranResult:
    resolved = req.model_copy(
        update={
            "upstream_image": _resolve_image(req.upstream_image),
            "reference_image": _resolve_image(req.reference_image) if req.reference_image else None,
        }
    )
    service = ShiseZhaoranService(
        output_root=str(Path(settings.UPLOAD_DIR) / "shise_zhaoran"),
        upload_root=settings.UPLOAD_DIR,
    )
    try:
        return service.generate(resolved)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


def _resolve_image(value: str) -> str:
    if value.startswith("/uploads/"):
        path = Path(settings.UPLOAD_DIR) / value.removeprefix("/uploads/")
    else:
        path = Path(value)
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"Image not found: {value}")
    return str(path)
