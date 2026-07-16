from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from backend.app import app
from backend.config import settings

client = TestClient(app)


def _create_reference_and_line(tmp_path: Path):
    original_path = tmp_path / "original.png"
    original = Image.new("RGB", (80, 60), "white")
    draw_original = ImageDraw.Draw(original)
    draw_original.ellipse((12, 10, 34, 32), fill=(220, 190, 150))
    draw_original.line((30, 35, 68, 44), fill=(95, 82, 60), width=4)
    original.save(original_path)

    line_path = tmp_path / "line.png"
    line = Image.new("L", (80, 60), 255)
    draw_line = ImageDraw.Draw(line)
    draw_line.ellipse((14, 11, 36, 33), outline=0, width=2)
    draw_line.line((32, 36, 70, 45), fill=0, width=2)
    line.save(line_path)

    reference_resp = client.post(
        "/api/v1/uploads/reference",
        files={"file": ("original.png", original_path.read_bytes(), "image/png")},
    )
    assert reference_resp.status_code == 200
    reference_id = reference_resp.json()["id"]

    line_resp = client.post(
        "/api/v1/line-drafts/upload",
        data={"reference_upload_id": reference_id},
        files={"file": ("line.png", line_path.read_bytes(), "image/png")},
    )
    assert line_resp.status_code == 200
    return reference_resp.json(), line_resp.json()


def test_registration_review_flow_writes_registered_baimiao_then_approves(tmp_path):
    reference, draft = _create_reference_and_line(tmp_path)

    auto_resp = client.post(f"/api/v1/registrations/line-drafts/{draft['id']}/auto")

    assert auto_resp.status_code == 200
    auto_data = auto_resp.json()
    assert auto_data["status"] == "review_required"
    assert auto_data["canonical_size"] == [80, 60]
    assert auto_data["registered_baimiao_image_uri"].startswith("/uploads/registrations/")
    assert auto_data["registration_overlay_uri"].startswith("/uploads/registrations/")

    registered_path = Path(settings.UPLOAD_DIR) / auto_data["registered_baimiao_image_uri"].removeprefix("/uploads/")
    overlay_path = Path(settings.UPLOAD_DIR) / auto_data["registration_overlay_uri"].removeprefix("/uploads/")
    assert registered_path.exists()
    assert overlay_path.exists()
    assert Image.open(registered_path).size == (80, 60)
    assert Image.open(overlay_path).size == (80, 60)

    approve_resp = client.post(
        f"/api/v1/registrations/line-drafts/{draft['id']}/approve",
        json={"registration_id": auto_data["registration_id"]},
    )

    assert approve_resp.status_code == 200
    approved = approve_resp.json()
    assert approved["status"] == "approved"
    assert approved["registered_baimiao_image_uri"] == auto_data["registered_baimiao_image_uri"]
    assert approved["registered_baimiao_path"] == str(registered_path)
