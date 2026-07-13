import hashlib
import io
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from backend.app import app
from backend.config import settings
from backend.services import fenran as fenran_service
from backend.services.fenran import FenranTrainingRenderResult, generate_fenran_training_render


client = TestClient(app)


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _png_bytes(size: tuple[int, int], color: tuple[int, int, int]) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


def test_fenran_training_render_builds_llm_prompt_and_keeps_line_draft_frozen(tmp_path, monkeypatch):
    original_path = tmp_path / "original.png"
    line_draft_path = tmp_path / "line.png"
    output_dir = tmp_path / "fenran"

    original = Image.new("RGB", (120, 90), "white")
    draw_original = ImageDraw.Draw(original)
    draw_original.ellipse((15, 15, 58, 55), fill=(226, 130, 150))
    draw_original.polygon([(72, 18), (108, 28), (82, 52)], fill=(115, 164, 76))
    draw_original.line((50, 55, 85, 80), fill=(86, 60, 38), width=5)
    original.save(original_path)

    line_draft = Image.new("L", (120, 90), 255)
    draw_line = ImageDraw.Draw(line_draft)
    draw_line.ellipse((15, 15, 58, 55), outline=0, width=2)
    draw_line.polygon([(72, 18), (108, 28), (82, 52)], outline=0)
    draw_line.line((50, 55, 85, 80), fill=0, width=2)
    line_draft.save(line_draft_path)
    before_hash = _file_hash(line_draft_path)

    monkeypatch.setenv("FENRAN_API_KEY", "fenran-test-key")
    monkeypatch.setenv("FENRAN_API_BASE", "https://example.com/v1")
    monkeypatch.setenv("FENRAN_IMAGE_MODEL", "gpt-image-2")

    captured: dict = {}

    def fake_render_image(*, model, prompt, size, image_paths, evidence, output_path):
        captured["model"] = model
        captured["prompt"] = prompt
        captured["size"] = size
        captured["image_paths"] = image_paths
        captured["evidence"] = evidence
        output_size = tuple(int(part) for part in size.split("x")) if isinstance(size, str) else size
        Image.new("RGB", output_size, (242, 224, 202)).save(output_path)
        return {
            "raw_output_path": str(output_path),
            "provider": "fake-llm",
            "used_model": model,
        }

    result = generate_fenran_training_render(
        str(original_path),
        str(line_draft_path),
        str(output_dir),
        "sample001",
        teaching_goal="first light then deepen; preserve paper white",
        render_image=fake_render_image,
    )

    assert _file_hash(line_draft_path) == before_hash
    assert result.width == 120
    assert result.height == 90
    assert result.parameters["renderer_version"] == fenran_service.RENDERER_VERSION
    assert result.parameters["model"] == "gpt-image-2"
    assert result.parameters["line_draft_modified"] is False
    assert "prompt_bundle" in result.parameters["artifacts"]
    assert Path(result.parameters["artifacts"]["prompt_bundle"]).exists()

    assert captured["model"] == "gpt-image-2"
    assert "\u5206\u67d3" in captured["prompt"]
    assert captured["image_paths"][0].endswith("registered_original.png")
    assert captured["image_paths"][1].endswith("registered_baimiao.png")
    assert captured["evidence"]["teacher_goal"] == "first light then deepen; preserve paper white"
    assert result.parameters["line_overlay_applied"] is False
    assert Image.open(result.output_path).convert("RGB").getpixel((5, 5)) == (242, 224, 202)


def test_fenran_training_api_supports_user_uploaded_line_draft(tmp_path, monkeypatch):
    reference_path = tmp_path / "reference.png"
    reference = Image.new("RGB", (100, 80), "white")
    draw_reference = ImageDraw.Draw(reference)
    draw_reference.ellipse((12, 14, 54, 48), fill=(223, 120, 146))
    draw_reference.rectangle((64, 18, 90, 48), fill=(118, 168, 86))
    reference.save(reference_path)

    reference_upload = client.post(
        "/api/v1/uploads/reference",
        files={"file": ("reference.png", reference_path.read_bytes(), "image/png")},
    )
    assert reference_upload.status_code == 200
    reference_id = reference_upload.json()["id"]

    line_draft_upload = client.post(
        "/api/v1/line-drafts/upload",
        data={"reference_upload_id": reference_id},
        files={"file": ("line.png", _png_bytes((100, 80), (255, 255, 255)), "image/png")},
    )
    assert line_draft_upload.status_code == 200
    draft = line_draft_upload.json()
    assert draft["provider"] == "user_upload"
    draft_path = Path(settings.UPLOAD_DIR) / draft["file_url"].removeprefix("/uploads/")
    before_hash = _file_hash(draft_path)

    def fake_generate_fenran_training_render(original_path, line_draft_path, output_dir, sample_id, **kwargs):
        out_path = Path(output_dir) / f"{sample_id}.png"
        Image.new("RGB", (100, 80), (240, 228, 210)).save(out_path)
        return FenranTrainingRenderResult(
            output_path=str(out_path),
            width=100,
            height=80,
            parameters={
                "line_draft_modified": False,
                "renderer_version": "fenran-renderer-v1",
                "model": "gpt-image-2",
                "artifacts": {"prompt_bundle": str(Path(output_dir) / sample_id / "prompt_bundle.json")},
            },
        )

    monkeypatch.setattr("backend.routes.fenran.generate_fenran_training_render", fake_generate_fenran_training_render)

    resp = client.post(
        "/api/v1/fenran/training-renders",
        json={
            "reference_upload_id": reference_id,
            "line_draft_id": draft["id"],
            "sample_id": "api-sample",
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["reference_upload_id"] == reference_id
    assert data["line_draft_id"] == draft["id"]
    assert data["metadata"]["line_draft_modified"] is False
    assert data["file_url"].startswith("/uploads/fenran_training/")
    assert _file_hash(draft_path) == before_hash


def test_fenran_training_render_requires_model_configuration_when_not_stubbed(tmp_path, monkeypatch):
    original_path = tmp_path / "original.png"
    line_draft_path = tmp_path / "line.png"
    output_dir = tmp_path / "fenran"

    Image.new("RGB", (40, 30), (220, 140, 160)).save(original_path)
    Image.new("L", (40, 30), 255).save(line_draft_path)

    monkeypatch.delenv("FENRAN_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    try:
        generate_fenran_training_render(str(original_path), str(line_draft_path), str(output_dir), "sample-no-key")
    except RuntimeError as exc:
        assert "FENRAN_API_KEY" in str(exc) or "OPENAI_API_KEY" in str(exc)
    else:
        raise AssertionError("expected fenran render to require an API key when no stub is provided")




def test_fenran_image_api_falls_back_to_single_reference_overlay_after_524(tmp_path, monkeypatch):
    original_path = tmp_path / "original.png"
    line_draft_path = tmp_path / "line.png"
    fallback_path = tmp_path / "reference_overlay.jpg"
    output_path = tmp_path / "raw.png"
    Image.new("RGB", (24, 24), (220, 170, 150)).save(original_path)
    Image.new("L", (24, 24), 255).save(line_draft_path)
    Image.new("RGB", (24, 24), (220, 170, 150)).save(fallback_path)

    calls = []

    class FakeResponse:
        def __init__(self, status_code, payload=None, text=""):
            self.status_code = status_code
            self._payload = payload or {}
            self.text = text
            self.reason_phrase = ""

        def json(self):
            return self._payload

    class FakeClient:
        def __init__(self, timeout):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, headers, data, files):
            calls.append(files)
            if len(calls) == 1:
                return FakeResponse(524, text="<html><title>524: A timeout occurred</title></html>")
            buffer = io.BytesIO()
            Image.new("RGB", (24, 24), (238, 225, 210)).save(buffer, format="PNG")
            import base64
            return FakeResponse(200, payload={"data": [{"b64_json": base64.b64encode(buffer.getvalue()).decode("ascii")}]})

    monkeypatch.setattr(fenran_service.httpx, "Client", FakeClient)

    result = fenran_service._render_fenran_with_openai_compatible_api(
        request={
            "model": "gpt-image-2",
            "prompt": "fenran",
            "size": "1024x1024",
            "image_paths": [str(original_path), str(line_draft_path)],
            "fallback_image_path": str(fallback_path),
            "output_path": str(output_path),
        },
        api_key="test-key",
        base_url="https://example.com/v1",
    )

    assert output_path.exists()
    assert result["provider"] == "gpt-image-compatible"
    assert len(calls) == 2
    assert isinstance(calls[0], list)
    assert isinstance(calls[1], dict)


def test_fenran_training_api_returns_actual_nested_output_url(tmp_path, monkeypatch):
    reference_path = tmp_path / "reference-url.png"
    Image.new("RGB", (32, 24), (230, 220, 200)).save(reference_path)
    reference_upload = client.post(
        "/api/v1/uploads/reference",
        files={"file": ("reference-url.png", reference_path.read_bytes(), "image/png")},
    )
    assert reference_upload.status_code == 200
    reference_id = reference_upload.json()["id"]

    line_draft_upload = client.post(
        "/api/v1/line-drafts/upload",
        data={"reference_upload_id": reference_id},
        files={"file": ("line-url.png", _png_bytes((32, 24), (255, 255, 255)), "image/png")},
    )
    assert line_draft_upload.status_code == 200
    draft = line_draft_upload.json()

    def fake_generate_fenran_training_render(original_path, line_draft_path, output_dir, sample_id, **kwargs):
        nested = Path(output_dir) / sample_id / "final_teaching_preview.png"
        nested.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (32, 24), (240, 228, 210)).save(nested)
        return FenranTrainingRenderResult(
            output_path=str(nested),
            width=32,
            height=24,
            parameters={"line_draft_modified": False, "artifacts": {"final_teaching_preview": str(nested)}},
        )

    monkeypatch.setattr("backend.routes.fenran.generate_fenran_training_render", fake_generate_fenran_training_render)

    resp = client.post(
        "/api/v1/fenran/training-renders",
        json={"reference_upload_id": reference_id, "line_draft_id": draft["id"], "sample_id": "nested-url-sample"},
    )

    assert resp.status_code == 200
    assert resp.json()["file_url"] == "/uploads/fenran_training/nested-url-sample/final_teaching_preview.png"


def test_fenran_final_preview_preserves_model_layout_without_system_line_overlay(tmp_path, monkeypatch):
    original_path = tmp_path / "original-layout.png"
    line_draft_path = tmp_path / "line-heavy.png"
    output_dir = tmp_path / "fenran-layout"

    original = Image.new("RGB", (64, 48), "white")
    ImageDraw.Draw(original).rectangle((20, 18, 44, 34), fill=(228, 205, 170))
    original.save(original_path)

    line_draft = Image.new("L", (64, 48), 255)
    ImageDraw.Draw(line_draft).line((0, 24, 63, 24), fill=0, width=5)
    line_draft.save(line_draft_path)
    before_hash = _file_hash(line_draft_path)

    monkeypatch.setenv("FENRAN_API_KEY", "fenran-test-key")
    monkeypatch.setenv("FENRAN_API_BASE", "https://example.com/v1")
    monkeypatch.setenv("FENRAN_IMAGE_MODEL", "gpt-image-2")

    def fake_render_image(*, model, prompt, size, image_paths, evidence, output_path):
        model_page = Image.new("RGB", (64, 48), (238, 226, 206))
        draw = ImageDraw.Draw(model_page)
        draw.rectangle((0, 0, 63, 6), fill=(92, 82, 66))
        draw.rectangle((4, 40, 14, 46), fill=(168, 146, 102))
        draw.rectangle((30, 22, 34, 26), fill=(238, 226, 206))
        model_page.save(output_path)
        return {"raw_output_path": str(output_path), "provider": "fake-llm"}

    result = generate_fenran_training_render(
        str(original_path),
        str(line_draft_path),
        str(output_dir),
        "preserve-layout-no-line-overlay",
        render_image=fake_render_image,
    )

    final = Image.open(result.output_path).convert("RGB")
    assert final.getpixel((8, 3)) == (92, 82, 66)
    assert final.getpixel((8, 43)) == (168, 146, 102)
    assert min(final.getpixel((32, 24))) > 180
    assert result.parameters["line_overlay_applied"] is False
    assert _file_hash(line_draft_path) == before_hash
