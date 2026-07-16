import base64
import io
import json
from pathlib import Path

from PIL import Image

from backend.shise_zhaoran import renderer


def test_prepare_api_inputs_downsizes_large_images(tmp_path):
    upstream = tmp_path / "large-upstream.png"
    reference = tmp_path / "large-reference.jpg"
    Image.new("RGB", (1686, 1559), (180, 195, 140)).save(upstream)
    Image.new("RGB", (1686, 1559), (150, 170, 120)).save(reference)

    prepared = renderer._prepare_api_inputs(
        image_path=str(upstream),
        reference_image=str(reference),
        artifact_dir=tmp_path / "artifacts",
        model_size="1536x1024",
        max_side=512,
    )

    assert prepared["canvas_size"] == [512, 341]
    assert len(prepared["paths"]) == 2
    assert all(Image.open(path).size == (512, 341) for path in prepared["paths"])
    assert sum(prepared["input_bytes"].values()) < upstream.stat().st_size + reference.stat().st_size


def test_image_api_uses_image_field_and_falls_back_to_single_input(tmp_path, monkeypatch):
    upstream = tmp_path / "upstream.png"
    reference = tmp_path / "reference.png"
    output = tmp_path / "render" / "final.png"
    output.parent.mkdir(parents=True)
    Image.new("RGB", (320, 280), (180, 195, 140)).save(upstream)
    Image.new("RGB", (320, 280), (140, 160, 110)).save(reference)
    calls = []

    class FakeResponse:
        def __init__(self, status_code, payload=None, text=""):
            self.status_code = status_code
            self._payload = payload or {}
            self.text = text

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
            calls.append([(field, filename, len(handle.read())) for field, (filename, handle, _mime) in files])
            if len(calls) == 1:
                return FakeResponse(413, text="payload too large")
            buffer = io.BytesIO()
            Image.new("RGB", (1024, 1024), (165, 185, 130)).save(buffer, format="PNG")
            return FakeResponse(200, {"data": [{"b64_json": base64.b64encode(buffer.getvalue()).decode("ascii")}]})

    monkeypatch.setattr(renderer.httpx, "Client", FakeClient)
    config = renderer.RendererConfig(
        api_key="test-key",
        base_url="https://example.test/v1",
        model="gpt-image-2",
        timeout_seconds=10,
        max_image_side=512,
    )

    metadata = renderer._call_image_edit_api(
        config=config,
        image_path=str(upstream),
        reference_image=str(reference),
        prompt="石色罩染",
        size="1024x1024",
        output_path=output,
    )

    assert output.exists()
    assert len(calls) == 2
    assert len(calls[0]) == 2
    assert len(calls[1]) == 1
    assert all(field == "image" for call in calls for field, _filename, _size in call)
    assert metadata["canvas_size"] == [512, 512]


def test_restore_from_api_canvas_removes_letterbox_without_cropping_subject():
    rendered = Image.new("RGB", (300, 200), (250, 248, 242))
    rendered.paste((170, 190, 135), (45, 0, 255, 200))
    restored = renderer._restore_from_api_canvas(
        rendered,
        (420, 400),
        {"canvas_size": [300, 200], "content_box": [45, 0, 255, 200]},
    )

    assert restored.size == (420, 400)
    assert restored.getpixel((0, 0)) == (170, 190, 135)
    assert restored.getpixel((419, 399)) == (170, 190, 135)


def test_image_api_failure_persists_structured_error(tmp_path, monkeypatch):
    upstream = tmp_path / "upstream.png"
    output = tmp_path / "render" / "final.png"
    output.parent.mkdir(parents=True)
    Image.new("RGB", (128, 96), (180, 195, 140)).save(upstream)

    class FakeResponse:
        status_code = 422
        text = "unsupported multipart image field"

    class FakeClient:
        def __init__(self, timeout):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, headers, data, files):
            return FakeResponse()

    monkeypatch.setattr(renderer.httpx, "Client", FakeClient)
    config = renderer.RendererConfig("key", "https://example.test/v1", "gpt-image-2", 10, 512)

    try:
        renderer._call_image_edit_api(
            config=config,
            image_path=str(upstream),
            reference_image=None,
            prompt="石色罩染",
            size="1536x1024",
            output_path=output,
        )
    except RuntimeError:
        pass
    else:
        raise AssertionError("expected API failure")

    error = json.loads((output.parent / "render_error.json").read_text(encoding="utf-8"))
    assert error["status_code"] == 422
    assert error["attempts"][0]["mode"] == "single"
    assert error["input_bytes"]["api_upstream.jpg"] > 0
