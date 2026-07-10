import json
import zipfile
from io import BytesIO

from PIL import Image

from scripts.prepare_teaching_pages import prepare_from_zip


def _image_bytes(width: int, height: int, color: str) -> bytes:
    image = Image.new("RGB", (width, height), color)
    stream = BytesIO()
    image.save(stream, format="JPEG")
    return stream.getvalue()


def test_prepare_teaching_pages_from_zip(tmp_path):
    zip_path = tmp_path / "book.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("scan/2.jpg", _image_bytes(120, 80, "white"))
        archive.writestr("scan/1.jpg", _image_bytes(80, 120, "gray"))
        archive.writestr("scan/readme.txt", "ignored")

    raw_root = tmp_path / "raw"
    processed_root = tmp_path / "processed"
    records = prepare_from_zip(zip_path, "book_test", raw_root, processed_root)

    assert [record.filename for record in records] == ["page_001.jpg", "page_002.jpg"]
    assert records[0].width == 80
    assert records[0].height == 120

    book_dir = processed_root / "book_test"
    pages = [
        json.loads(line)
        for line in (book_dir / "pages.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(pages) == 2
    assert pages[0]["status"] == "needs_ocr"

    annotation = json.loads((book_dir / "annotation_template.json").read_text(encoding="utf-8"))
    assert annotation["pages"][0]["form_logic_units"] == []
    assert "form_logic_unit_schema" in annotation
    assert "technique_unit_schema" in annotation

    assert (book_dir / "README.md").exists()
    assert (book_dir / "contact_sheet.jpg").exists()
