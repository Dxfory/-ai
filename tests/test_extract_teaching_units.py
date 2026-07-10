import json

from PIL import Image

from scripts.extract_teaching_units import (
    call_with_retries,
    extract_json,
    extract_message_text,
    normalize_base_url,
    parse_selected_pages,
    prepare_model_image,
)


def test_normalize_base_url():
    assert normalize_base_url("https://lingsuan.top") == "https://lingsuan.top/v1"
    assert normalize_base_url("https://lingsuan.top/v1") == "https://lingsuan.top/v1"


def test_extract_json_plain_and_fenced():
    assert extract_json('{"page_id":"p1"}') == {"page_id": "p1"}
    assert extract_json('```json\n{"page_id":"p2"}\n```') == {"page_id": "p2"}


def test_extract_message_text_variants():
    assert extract_message_text({"choices": [{"message": {"content": "hello"}}]}) == "hello"
    assert extract_message_text({"choices": [{"message": {"content": [{"text": "hello"}]}}]}) == "hello"
    assert extract_message_text({"choices": [{"text": "hello"}]}) == "hello"
    assert extract_message_text({"output_text": "hello"}) == "hello"
    assert extract_message_text({"output": [{"content": [{"text": "hello"}]}]}) == "hello"


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


def test_parse_selected_pages():
    pages = [{"page_index": 1}, {"page_index": 2}, {"page_index": 3}]
    assert parse_selected_pages("1,3", pages) == {1, 3}
    assert parse_selected_pages("all", pages) == {1, 2, 3}


def test_call_with_retries_raises_without_network(tmp_path):
    page = {"page_id": "p1", "page_index": 1}
    try:
        call_with_retries(
            page=page,
            model="model",
            base_url="https://127.0.0.1:9/v1",
            api_key="key",
            image_path=tmp_path / "missing.jpg",
            raw_response_dir=tmp_path,
            wire_api="responses",
            retries=0,
            retry_sleep=0,
            compact=True,
        )
    except Exception as exc:
        assert type(exc).__name__ in {"ConnectError", "FileNotFoundError"}
