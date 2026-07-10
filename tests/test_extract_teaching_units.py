import json

from PIL import Image

from scripts.extract_teaching_units import extract_json, normalize_base_url, prepare_model_image


def test_normalize_base_url():
    assert normalize_base_url("https://lingsuan.top") == "https://lingsuan.top/v1"
    assert normalize_base_url("https://lingsuan.top/v1") == "https://lingsuan.top/v1"


def test_extract_json_plain_and_fenced():
    assert extract_json('{"page_id":"p1"}') == {"page_id": "p1"}
    assert extract_json('```json\n{"page_id":"p2"}\n```') == {"page_id": "p2"}


def test_teaching_unit_shape():
    payload = {
        "page_id": "book_001_page_030",
        "page_type": "coloring_step",
        "technique_units": [
            {
                "objects": ["正叶"],
                "materials_or_colors": ["汁绿"],
                "actions": ["罩染"],
                "conditions": [],
                "warnings": [],
                "linked_figure_nos": ["图13"],
            }
        ],
    }
    encoded = json.dumps(payload, ensure_ascii=False)
    assert extract_json(encoded)["technique_units"][0]["actions"] == ["罩染"]


def test_prepare_model_image(tmp_path):
    source = tmp_path / "page.jpg"
    Image.new("RGB", (2400, 1200), "white").save(source)
    page = {"raw_path": str(source), "page_id": "book_001_page_001"}

    output = prepare_model_image(page, tmp_path / "model_images", max_side=800)

    assert output.exists()
    with Image.open(output) as img:
        assert max(img.size) == 800
