from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from backend.app import app
from backend.config import settings
from backend.database import SessionLocal
from backend.models import LineDraftModel
from backend.schemas import FenranStageRenderSchema, FenranTrainingRenderRequest, FenranTrainingRenderSchema
from backend.services.fenran import FenranTrainingRenderResult


client = TestClient(app)


def _approved_inputs(tmp_path: Path):
    original = tmp_path / "original.png"
    line = tmp_path / "line.png"
    Image.new("RGB", (64, 48), "white").save(original)
    Image.new("L", (64, 48), 255).save(line)
    reference = client.post(
        "/api/v1/uploads/reference",
        files={"file": ("original.png", original.read_bytes(), "image/png")},
    ).json()
    draft = client.post(
        "/api/v1/line-drafts/upload",
        data={"reference_upload_id": reference["id"]},
        files={"file": ("line.png", line.read_bytes(), "image/png")},
    ).json()
    registered = Path(settings.UPLOAD_DIR) / "registrations" / draft["id"] / "approved.png"
    registered.parent.mkdir(parents=True, exist_ok=True)
    Image.new("L", (64, 48), 255).save(registered)
    with SessionLocal() as db:
        model = db.query(LineDraftModel).filter(LineDraftModel.id == draft["id"]).first()
        metadata = dict(model.metadata_ or {})
        metadata["registration"] = {
            "registration_id": "approved-registration",
            "status": "approved",
            "requires_review": False,
            "registered_baimiao_path": str(registered),
        }
        model.metadata_ = metadata
        db.add(model)
        db.commit()
    return reference, draft


def test_schema_exposes_stage_outputs_and_generation_controls():
    request = FenranTrainingRenderRequest(
        reference_upload_id="reference",
        line_draft_id="draft",
        include_base_color=True,
        force_regenerate=True,
        max_attempts=5,
    )
    response = FenranTrainingRenderSchema(
        sample_id="sample",
        reference_upload_id="reference",
        line_draft_id="draft",
        canonical_width=1204,
        canonical_height=1394,
        stages=[FenranStageRenderSchema(
            stage_id="stage_01_first_fenran",
            title="第一遍分染",
            technique="分染",
            pigments=["花青", "淡墨"],
            file_url="/uploads/stage.png",
            status="ready",
        )],
        file_url="/uploads/stage.png",
    )

    assert request.include_base_color is True
    assert request.force_regenerate is True
    assert request.max_attempts == 5
    assert response.stages[0].pigments == ["花青", "淡墨"]
    assert response.canonical_width == 1204


def test_api_returns_422_when_all_stage_attempts_fail_validation(tmp_path, monkeypatch):
    reference, draft = _approved_inputs(tmp_path)

    def fake_generate(**kwargs):
        completed = tmp_path / "stage-1.png"
        Image.new("RGB", (64, 48), "white").save(completed)
        return FenranTrainingRenderResult(
            output_path=str(tmp_path / "best.png"),
            width=64,
            height=48,
            parameters={},
            status="review_required",
            failed_stage="stage_02_deepen_fenran",
            reasons=["subject_bbox_iou_below_threshold"],
            stages=[{
                "stage_id": "stage_01_first_fenran",
                "title": "第一遍分染",
                "technique": "分染",
                "pigments": ["花青", "淡墨"],
                "output_path": str(completed),
                "status": "ready",
                "validation": {"score": 0.95},
            }],
        )

    monkeypatch.setattr("backend.routes.fenran.generate_fenran_training_render", fake_generate)
    response = client.post(
        "/api/v1/fenran/training-renders",
        json={"reference_upload_id": reference["id"], "line_draft_id": draft["id"]},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["status"] == "review_required"
    assert response.json()["detail"]["failed_stage"] == "stage_02_deepen_fenran"
    assert response.json()["detail"]["completed_stages"][0]["stage_id"] == "stage_01_first_fenran"


def test_api_returns_400_for_invalid_fenran_configuration(tmp_path, monkeypatch):
    reference, draft = _approved_inputs(tmp_path)
    monkeypatch.setenv("FENRAN_IMAGE_TIMEOUT_SECONDS", "not-a-number")

    response = client.post(
        "/api/v1/fenran/training-renders",
        json={"reference_upload_id": reference["id"], "line_draft_id": draft["id"]},
    )

    assert response.status_code == 400
    assert "FENRAN" in response.text
