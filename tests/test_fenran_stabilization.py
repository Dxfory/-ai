import io
from pathlib import Path

import httpx
import pytest
from PIL import Image, ImageDraw, ImageOps

from backend.services.fenran_canvas import (
    _place_on_fenran_generation_canvas,
    _resolve_fenran_generation_canvas,
    _restore_from_fenran_generation_canvas,
)
from backend.services.fenran_generation import (
    FenranProviderError,
    _post_fenran_image_edit,
    render_fenran_image,
)


@pytest.mark.parametrize("canonical_size", [(1800, 900), (960, 1440), (1024, 1024)])
def test_generation_canvas_round_trip_restores_each_canonical_size(canonical_size):
    source = Image.new("RGB", canonical_size, "white")
    ImageDraw.Draw(source).rectangle((10, 10, canonical_size[0] - 11, canonical_size[1] - 11), fill="black")

    canvas = _resolve_fenran_generation_canvas(canonical_size, image_size="auto", max_side=1536)
    placed = _place_on_fenran_generation_canvas(source, canvas)
    restored = _restore_from_fenran_generation_canvas(placed, canvas)

    assert restored.size == canonical_size
    assert canvas.content_box[2] > canvas.content_box[0]
    assert canvas.content_box[3] > canvas.content_box[1]
    assert placed.size == canvas.canvas_size


def test_multiple_inputs_share_the_exact_same_content_box():
    canvas = _resolve_fenran_generation_canvas((1204, 1394), image_size="auto", max_side=1536)
    original = _place_on_fenran_generation_canvas(Image.new("RGB", (1204, 1394), "red"), canvas)
    baimiao = _place_on_fenran_generation_canvas(Image.new("L", (1204, 1394), 0), canvas)

    assert original.size == baimiao.size == canvas.canvas_size
    assert original.getbbox() == (0, 0, *canvas.canvas_size)
    assert ImageOps.invert(baimiao).getbbox() == canvas.content_box


def test_image_edit_upload_supports_arbitrary_image_count(tmp_path):
    paths = []
    for index in range(4):
        path = tmp_path / f"input-{index}.png"
        Image.new("RGB", (8, 8), (index, index, index)).save(path)
        paths.append(str(path))

    captured = {}

    class FakeClient:
        def post(self, url, headers, data, files):
            captured["files"] = files
            return httpx.Response(200, json={"data": []})

    response = _post_fenran_image_edit(FakeClient(), "https://example.test", {}, {}, paths)

    assert response.status_code == 200
    assert len(captured["files"]) == 4
    assert all(item[0] == "image" for item in captured["files"])
    assert all(item[1][1].closed for item in captured["files"])


def test_multi_image_failure_does_not_silently_fallback_by_default(tmp_path, monkeypatch):
    image_paths = []
    for name in ("previous.png", "original.png", "baimiao.png"):
        path = tmp_path / name
        Image.new("RGB", (8, 8), "white").save(path)
        image_paths.append(str(path))

    calls = []

    class FakeClient:
        def __init__(self, timeout):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, headers, data, files):
            calls.append(files)
            return httpx.Response(524, text="provider timeout")

    monkeypatch.setattr("backend.services.fenran_generation.httpx.Client", FakeClient)
    monkeypatch.delenv("FENRAN_ALLOW_SINGLE_REFERENCE_FALLBACK", raising=False)

    with pytest.raises(FenranProviderError, match="HTTP 524"):
        render_fenran_image(
            model="gpt-image-2",
            prompt="stage",
            size="1024x1024",
            image_paths=image_paths,
            output_path=str(tmp_path / "out.png"),
            api_key="test-key",
            base_url="https://example.test/v1",
        )

    assert len(calls) == 1
