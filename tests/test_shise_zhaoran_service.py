from pathlib import Path

from PIL import Image, ImageDraw

from backend.shise_zhaoran.schemas import ShiseZhaoranRequest
from backend.shise_zhaoran.service import ShiseZhaoranService


def _ready_upstream(path: Path) -> None:
    image = Image.new("RGB", (96, 72), (244, 239, 225))
    draw = ImageDraw.Draw(image)
    draw.ellipse((10, 10, 44, 45), fill=(180, 203, 146), outline=(45, 50, 40), width=2)
    draw.polygon([(50, 14), (84, 27), (57, 48)], fill=(105, 150, 78), outline=(35, 45, 30))
    draw.line((38, 42, 78, 66), fill=(80, 55, 38), width=3)
    image.save(path)


def test_silk_without_fixing_is_not_ready_and_does_not_render(tmp_path):
    upstream = tmp_path / "upstream.png"
    _ready_upstream(upstream)
    called = False

    def fake_render(**kwargs):
        nonlocal called
        called = True

    result = ShiseZhaoranService(str(tmp_path / "out")).generate(
        ShiseZhaoranRequest(upstream_image=str(upstream), medium="silk", apply_fixing=False),
        render_image=fake_render,
    )

    assert result.status == "not_ready"
    assert result.readiness.fixing_required is True
    assert any("胶矾水" in reason for reason in result.readiness.reasons)
    assert called is False


def test_missing_upstream_returns_not_ready(tmp_path):
    result = ShiseZhaoranService(str(tmp_path / "out")).generate(
        ShiseZhaoranRequest(upstream_image=str(tmp_path / "missing.png"), medium="paper")
    )
    assert result.status == "not_ready"
    assert result.final_image is None


def test_ready_input_outputs_final_result_and_prompt(tmp_path):
    upstream = tmp_path / "upstream.png"
    _ready_upstream(upstream)

    def fake_render(**kwargs):
        source = Image.open(kwargs["upstream_image"]).convert("RGB")
        overlay = Image.new("RGB", source.size, (176, 194, 139))
        Image.blend(source, overlay, 0.12).save(kwargs["output_path"])
        assert "石色罩染" in kwargs["prompt"]
        assert "正叶：三绿" in kwargs["prompt"]
        return {"output_path": kwargs["output_path"]}

    result = ShiseZhaoranService(str(tmp_path / "out"), str(tmp_path)).generate(
        ShiseZhaoranRequest(
            upstream_image=str(upstream),
            medium="paper",
            subject_hints=["正叶", "反叶", "枝干"],
            sample_id="happy-path",
        ),
        render_image=fake_render,
    )

    assert result.status == "completed"
    assert result.readiness.ready is True
    assert result.final_image and Path(result.final_image).exists()
    assert result.final_image_url == "/uploads/out/happy-path/final_shise_zhaoran.png"
    assert result.validation_result is not None
    assert result.metadata["upstream_stage"] == "fenran_plus_water_color_glaze"
