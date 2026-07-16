import io
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from backend.app import app


client = TestClient(app)


def test_shise_upstream_upload():
    buffer = io.BytesIO()
    Image.new("RGB", (48, 36), (180, 195, 140)).save(buffer, format="PNG")
    response = client.post(
        "/api/v1/shise-zhaoran/upstream",
        files={"file": ("water-color.png", buffer.getvalue(), "image/png")},
    )
    assert response.status_code == 200
    assert response.json()["file_url"].startswith("/uploads/shise_zhaoran_inputs/")
    assert response.json()["width"] == 48
    assert response.json()["height"] == 36


def test_shise_zhaoran_api_happy_path(tmp_path, monkeypatch):
    upstream = tmp_path / "water-color-finished.png"
    image = Image.new("RGB", (80, 60), (244, 238, 220))
    draw = ImageDraw.Draw(image)
    draw.ellipse((8, 8, 38, 38), fill=(164, 192, 125), outline=(35, 42, 30), width=2)
    draw.line((35, 35, 70, 52), fill=(75, 52, 36), width=3)
    image.save(upstream)

    def fake_renderer(**kwargs):
        source = Image.open(kwargs["upstream_image"]).convert("RGB")
        tint = Image.new("RGB", source.size, (160, 184, 128))
        Image.blend(source, tint, 0.1).save(kwargs["output_path"])
        return {
            "output_path": kwargs["output_path"],
            "model": "fake-image-2",
            "api_base": "test",
            "input_size": list(source.size),
            "output_size": list(source.size),
        }

    monkeypatch.setattr("backend.shise_zhaoran.service.render_shise_zhaoran", fake_renderer)

    response = client.post(
        "/api/v1/shise-zhaoran/generate",
        json={
            "upstream_image": str(upstream),
            "medium": "paper",
            "subject_hints": ["正叶", "反叶", "未成熟果", "枝干"],
            "sample_id": "api-happy-path",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["final_image_url"].endswith("/api-happy-path/final_shise_zhaoran.png")
    assert payload["readiness"]["ready"] is True
    assert {item["object_type"] for item in payload["plan_summary"]} == {
        "front_leaf",
        "back_leaf",
        "unripe_fruit",
        "branch",
    }


def test_shise_zhaoran_api_blocks_unfixed_silk(tmp_path, monkeypatch):
    upstream = tmp_path / "silk.png"
    Image.new("RGB", (32, 32), (120, 160, 90)).save(upstream)

    def fail_renderer(**kwargs):
        raise AssertionError("renderer must not run")

    monkeypatch.setattr("backend.shise_zhaoran.service.render_shise_zhaoran", fail_renderer)
    response = client.post(
        "/api/v1/shise-zhaoran/generate",
        json={"upstream_image": str(upstream), "medium": "silk", "apply_fixing": False},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "not_ready"
    assert response.json()["readiness"]["fixing_required"] is True
