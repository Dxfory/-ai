from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

from backend.services.fenran import generate_fenran_training_render
from backend.services.fenran_generation import FenranProviderError


def _write_inputs(tmp_path, size=(120, 90)):
    original_path = tmp_path / "original.png"
    baimiao_path = tmp_path / "registered-baimiao.png"
    original = Image.new("RGB", size, "white")
    ImageDraw.Draw(original).ellipse((20, 15, 90, 70), fill=(150, 170, 110))
    original.save(original_path)
    baimiao = Image.new("L", size, 255)
    ImageDraw.Draw(baimiao).ellipse((20, 15, 90, 70), outline=0, width=2)
    baimiao.save(baimiao_path)
    return original_path, baimiao_path


def _write_structured_provider_output(image_paths, size, output_path, color):
    previous = Image.open(image_paths[0]).convert("RGB")
    tinted = Image.blend(previous, Image.new("RGB", previous.size, color), 0.45)
    dark_lines = previous.convert("L").point(lambda value: 255 if value < 160 else 0)
    tinted.paste(previous, mask=dark_lines)
    canvas_size = tuple(int(part) for part in size.split("x"))
    placed = ImageOps.contain(tinted, canvas_size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", canvas_size, "white")
    canvas.paste(placed, ((canvas.width - placed.width) // 2, (canvas.height - placed.height) // 2))
    canvas.save(output_path)


def test_pipeline_generates_cumulative_stages_at_canonical_size_and_reuses_cache(tmp_path, monkeypatch):
    original_path, baimiao_path = _write_inputs(tmp_path)
    calls = []
    colors = [(175, 190, 180), (120, 150, 150), (105, 155, 95)]

    def fake_render_image(*, model, prompt, size, image_paths, evidence, output_path):
        index = len(calls)
        calls.append({"prompt": prompt, "image_paths": list(image_paths)})
        _write_structured_provider_output(image_paths, size, output_path, colors[index])
        return {"raw_output_path": output_path, "request_mode": "multi_image", "fallback_used": False}

    monkeypatch.setenv("FENRAN_ENABLE_CACHE", "true")
    first = generate_fenran_training_render(
        original_path=str(original_path),
        registered_baimiao_path=str(baimiao_path),
        output_dir=str(tmp_path / "renders"),
        sample_id="sample-a",
        registration={"registration_id": "approved-1", "status": "approved"},
        render_image=fake_render_image,
    )

    assert first.status == "ready"
    assert [stage["stage_id"] for stage in first.stages] == [
        "stage_01_first_fenran",
        "stage_02_deepen_fenran",
        "stage_03_sap_green_glaze",
    ]
    assert all(Image.open(stage["output_path"]).size == (120, 90) for stage in first.stages)
    assert Path(first.output_path).parent.name == "stage_03_sap_green_glaze"
    assert Path(first.output_path).name == "selected.png"
    assert len(calls) == 3
    assert Path(calls[1]["image_paths"][0]).parent.name == "stage_01_first_fenran"
    assert Path(calls[2]["image_paths"][0]).parent.name == "stage_02_deepen_fenran"

    second = generate_fenran_training_render(
        original_path=str(original_path),
        registered_baimiao_path=str(baimiao_path),
        output_dir=str(tmp_path / "renders"),
        sample_id="sample-b",
        registration={"registration_id": "approved-1", "status": "approved"},
        render_image=fake_render_image,
    )

    assert second.cache_hit is True
    assert second.parameters["sample_id"] == "sample-a"
    assert len(calls) == 3


def test_pipeline_retries_validation_failure_and_fails_closed(tmp_path, monkeypatch):
    original_path, baimiao_path = _write_inputs(tmp_path)
    attempts = 0

    def unchanged_render(*, model, prompt, size, image_paths, evidence, output_path):
        nonlocal attempts
        attempts += 1
        previous = Image.open(image_paths[0]).convert("RGB")
        canvas_size = tuple(int(part) for part in size.split("x"))
        placed = ImageOps.contain(previous, canvas_size, Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", canvas_size, "white")
        canvas.paste(placed, ((canvas.width - placed.width) // 2, (canvas.height - placed.height) // 2))
        canvas.save(output_path)
        return {"raw_output_path": output_path, "request_mode": "multi_image", "fallback_used": False}

    monkeypatch.setenv("FENRAN_ENABLE_CACHE", "false")
    result = generate_fenran_training_render(
        original_path=str(original_path),
        registered_baimiao_path=str(baimiao_path),
        output_dir=str(tmp_path / "renders"),
        sample_id="failed",
        registration={"registration_id": "approved-2", "status": "approved"},
        max_attempts=3,
        render_image=unchanged_render,
    )

    assert result.status == "review_required"
    assert result.failed_stage == "stage_01_first_fenran"
    assert attempts == 3
    assert result.stages == []


def test_pipeline_includes_optional_base_color_only_when_requested(tmp_path, monkeypatch):
    original_path, baimiao_path = _write_inputs(tmp_path)
    calls = []
    input_counts = []

    def fake_render_image(*, model, prompt, size, image_paths, evidence, output_path):
        calls.append(prompt)
        input_counts.append(len(image_paths))
        _write_structured_provider_output(
            image_paths,
            size,
            output_path,
            (80 + len(calls) * 25, 130, 100),
        )
        return {"raw_output_path": output_path, "request_mode": "multi_image", "fallback_used": False}

    monkeypatch.setenv("FENRAN_ENABLE_CACHE", "false")
    result = generate_fenran_training_render(
        original_path=str(original_path),
        registered_baimiao_path=str(baimiao_path),
        output_dir=str(tmp_path / "renders"),
        sample_id="with-base-color",
        registration={"registration_id": "approved-3", "status": "approved"},
        include_base_color=True,
        render_image=fake_render_image,
    )

    assert result.status == "ready"
    assert [stage["stage_id"] for stage in result.stages] == [
        "stage_00_base_color",
        "stage_01_first_fenran",
        "stage_02_deepen_fenran",
        "stage_03_sap_green_glaze",
    ]
    assert len(calls) == 4
    assert input_counts == [2, 3, 3, 3]


def test_pipeline_rejects_provider_output_with_wrong_canvas_size(tmp_path, monkeypatch):
    original_path, baimiao_path = _write_inputs(tmp_path)

    def wrong_size_render(*, model, prompt, size, image_paths, evidence, output_path):
        Image.new("RGB", (17, 19), "white").save(output_path)
        return {"raw_output_path": output_path, "request_mode": "multi_image", "fallback_used": False}

    monkeypatch.setenv("FENRAN_ENABLE_CACHE", "false")
    import pytest
    with pytest.raises(FenranProviderError, match="canvas size"):
        generate_fenran_training_render(
            original_path=str(original_path),
            registered_baimiao_path=str(baimiao_path),
            output_dir=str(tmp_path / "renders"),
            sample_id="wrong-size",
            registration={"registration_id": "approved-4", "status": "approved"},
            render_image=wrong_size_render,
        )
