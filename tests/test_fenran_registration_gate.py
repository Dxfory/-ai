from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from backend.app import app
from backend.config import settings
from backend.database import SessionLocal
from backend.models import LineDraftModel
from backend.services.fenran import FenranTrainingRenderResult

client = TestClient(app)


def _png_bytes(path: Path, size=(64, 48), color=(255, 255, 255)) -> bytes:
    Image.new("RGB", size, color).save(path)
    return path.read_bytes()


def _create_reference_and_line(tmp_path: Path):
    original_path = tmp_path / "original.png"
    line_path = tmp_path / "line.png"
    Image.new("RGB", (64, 48), (230, 220, 200)).save(original_path)
    Image.new("RGB", (64, 48), (255, 255, 255)).save(line_path)

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


def test_fenran_requires_approved_registered_baimiao_before_render(tmp_path, monkeypatch):
    reference, draft = _create_reference_and_line(tmp_path)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("fenran render must not run before registration approval")

    monkeypatch.setattr("backend.routes.fenran.generate_fenran_training_render", fail_if_called)

    resp = client.post(
        "/api/v1/fenran/training-renders",
        json={"reference_upload_id": reference["id"], "line_draft_id": draft["id"], "sample_id": "blocked"},
    )

    assert resp.status_code == 409
    assert resp.json()["detail"]["status"] == "registration_review"


def test_fenran_uses_approved_registered_baimiao_path_without_changing_render_contract(tmp_path, monkeypatch):
    reference, draft = _create_reference_and_line(tmp_path)
    registered_path = Path(settings.UPLOAD_DIR) / "registrations" / draft["id"] / "registered_baimiao.png"
    registered_path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("L", (64, 48), 255).save(registered_path)

    with SessionLocal() as db:
        model = db.query(LineDraftModel).filter(LineDraftModel.id == draft["id"]).first()
        assert model is not None
        metadata = dict(model.metadata_ or {})
        metadata["registration"] = {
            "status": "approved",
            "registered_baimiao_path": str(registered_path),
            "registered_baimiao_image_uri": f"/uploads/registrations/{draft['id']}/registered_baimiao.png",
            "registration_score": 0.98,
            "requires_review": False,
        }
        model.metadata_ = metadata
        db.add(model)
        db.commit()

    captured = {}

    def fake_generate_fenran_training_render(original_path, registered_baimiao_path, output_dir, sample_id, **kwargs):
        captured["line_draft_path"] = registered_baimiao_path
        out_path = Path(output_dir) / sample_id / "final_teaching_preview.png"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (64, 48), (240, 228, 210)).save(out_path)
        return FenranTrainingRenderResult(
            output_path=str(out_path),
            width=64,
            height=48,
            parameters={
                "line_draft_modified": False,
                "line_overlay_applied": False,
                "renderer_version": "fenran-renderer-v2",
                "artifacts": {"final_teaching_preview": str(out_path)},
            },
        )

    monkeypatch.setattr("backend.routes.fenran.generate_fenran_training_render", fake_generate_fenran_training_render)

    resp = client.post(
        "/api/v1/fenran/training-renders",
        json={"reference_upload_id": reference["id"], "line_draft_id": draft["id"], "sample_id": "approved"},
    )

    assert resp.status_code == 200
    assert Path(captured["line_draft_path"]).resolve() == registered_path.resolve()
    assert resp.json()["metadata"]["registration"]["status"] == "approved"

