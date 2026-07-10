import json

from PIL import Image, ImageDraw

from scripts.extract_page_regions import extract_regions_for_page, write_preview


def test_extract_regions_for_synthetic_page(tmp_path):
    image_path = tmp_path / "page_001.jpg"
    image = Image.new("RGB", (800, 1000), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((90, 90, 700, 520), outline="black", width=8)
    for y in range(620, 800, 32):
        draw.rectangle((100, y, 620, y + 8), fill="black")
    image.save(image_path)

    page = {
        "book_id": "book_test",
        "page_index": 1,
        "page_id": "book_test_page_001",
        "raw_path": str(image_path),
        "width": 800,
        "height": 1000,
    }
    regions = extract_regions_for_page(page, max_side=800)

    assert regions
    assert any(region.role_hint in {"large_figure_or_full_artwork", "figure_candidate"} for region in regions)
    assert all(len(region.bbox) == 4 for region in regions)

    preview_dir = tmp_path / "previews"
    write_preview(page, regions, preview_dir)
    assert (preview_dir / "book_test_page_001_layout.jpg").exists()


def test_layout_candidate_shape(tmp_path):
    payload = {
        "book_id": "book_test",
        "purpose": "Rough layout candidates for OCR, figure-number binding, and technique-unit extraction.",
        "pages": [],
    }
    path = tmp_path / "layout_candidates.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["pages"] == []
