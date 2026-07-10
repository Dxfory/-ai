"""Prepare scanned technique-book pages for later OCR and figure-text binding.

This script intentionally does not require the user to pre-classify pages into
source/baimiao/coloring steps. It treats the book as whole pages first, then
creates manifests that can be enriched by OCR and figure-region annotation.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}


@dataclass
class PageRecord:
    book_id: str
    page_index: int
    page_id: str
    filename: str
    raw_path: str
    processed_path: str
    width: int
    height: int
    file_size: int
    original_zip_name: str = ""
    status: str = "needs_ocr"
    notes: str = ""


def natural_key(value: str) -> list[object]:
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", value)]


def iter_zip_images(zip_path: Path) -> list[zipfile.ZipInfo]:
    with zipfile.ZipFile(zip_path) as archive:
        infos = [
            info for info in archive.infolist()
            if not info.is_dir() and Path(info.filename).suffix.lower() in IMAGE_EXTS
        ]
    return sorted(infos, key=lambda info: natural_key(Path(info.filename).name))


def prepare_from_zip(zip_path: Path, book_id: str, raw_root: Path, processed_root: Path) -> list[PageRecord]:
    raw_book_dir = raw_root / book_id
    processed_book_dir = processed_root / book_id
    raw_book_dir.mkdir(parents=True, exist_ok=True)
    processed_book_dir.mkdir(parents=True, exist_ok=True)

    records: list[PageRecord] = []
    infos = iter_zip_images(zip_path)
    with zipfile.ZipFile(zip_path) as archive:
        for index, info in enumerate(infos, start=1):
            ext = Path(info.filename).suffix.lower() or ".jpg"
            page_id = f"{book_id}_page_{index:03d}"
            filename = f"page_{index:03d}{ext}"
            raw_path = raw_book_dir / filename
            with archive.open(info) as src, raw_path.open("wb") as dst:
                shutil.copyfileobj(src, dst)

            with Image.open(raw_path) as img:
                width, height = img.size

            records.append(PageRecord(
                book_id=book_id,
                page_index=index,
                page_id=page_id,
                filename=filename,
                raw_path=str(raw_path),
                processed_path=str(processed_book_dir),
                width=width,
                height=height,
                file_size=raw_path.stat().st_size,
                original_zip_name=info.filename,
            ))

    write_manifests(records, processed_book_dir)
    return records


def write_manifests(records: list[PageRecord], processed_book_dir: Path) -> None:
    pages_path = processed_book_dir / "pages.jsonl"
    with pages_path.open("w", encoding="utf-8") as out:
        for record in records:
            out.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")

    annotation = {
        "book_id": records[0].book_id if records else "",
        "purpose": "Bind full-page scans to OCR text, figure regions, figure numbers, and gongbi technique steps.",
        "pages": [
            {
                "page_id": record.page_id,
                "page_index": record.page_index,
                "image": record.raw_path,
                "ocr_text": "",
                "figures": [],
                "text_blocks": [],
                "form_logic_units": [],
                "technique_units": [],
            }
            for record in records
        ],
        "figure_schema": {
            "figure_no": "图9",
            "bbox": [0, 0, 0, 0],
            "role": "reference|baimiao|gouxian|done|comparison|unknown",
            "step_order": None,
            "caption": "",
            "linked_text_block_ids": [],
        },
        "form_logic_unit_schema": {
            "object": "leaf|flower|branch|bird|fruit|insect|other",
            "real_world_reference": "",
            "structural_observation": "",
            "artistic_transformation": "",
            "line_logic": "",
            "linked_figure_nos": [],
            "source_text": "",
        },
        "technique_unit_schema": {
            "step_name": "",
            "step_order": None,
            "objects": ["flower", "leaf", "branch", "bird", "fruit"],
            "materials": [],
            "colors": [],
            "actions": [],
            "warnings": [],
            "source_text": "",
            "linked_figure_nos": [],
        },
    }
    (processed_book_dir / "annotation_template.json").write_text(
        json.dumps(annotation, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    summary = [
        f"# {records[0].book_id if records else 'book'} ingest summary",
        "",
        f"- pages: {len(records)}",
        f"- total_bytes: {sum(record.file_size for record in records)}",
        f"- generated_at: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Next annotation passes",
        "",
        "1. OCR each page and fill `ocr_text` / `text_blocks`.",
        "2. Crop or mark every figure region with `bbox`.",
        "3. Bind captions such as `图9` to the nearest explanatory paragraph.",
        "4. Extract technique units: materials, colors, actions, warnings, step order.",
        "5. Convert validated units into training/evaluation examples.",
    ]
    (processed_book_dir / "README.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
    if records:
        write_contact_sheet(records, processed_book_dir / "contact_sheet.jpg")


def write_contact_sheet(records: list[PageRecord], output_path: Path) -> None:
    thumb_w = 260
    thumb_h = 360
    label_h = 30
    gap = 18
    columns = 5
    rows = (len(records) + columns - 1) // columns
    sheet_w = columns * thumb_w + (columns + 1) * gap
    sheet_h = rows * (thumb_h + label_h) + (rows + 1) * gap
    sheet = Image.new("RGB", (sheet_w, sheet_h), "white")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()

    for index, record in enumerate(records):
        row = index // columns
        col = index % columns
        x = gap + col * (thumb_w + gap)
        y = gap + row * (thumb_h + label_h + gap)
        with Image.open(record.raw_path).convert("RGB") as page:
            page.thumbnail((thumb_w, thumb_h), Image.Resampling.LANCZOS)
            px = x + (thumb_w - page.width) // 2
            py = y + (thumb_h - page.height) // 2
            sheet.paste(page, (px, py))
        draw.text((x, y + thumb_h + 8), record.filename, fill=(35, 35, 35), font=font)

    sheet.save(output_path, quality=88, optimize=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("zip_path", type=Path)
    parser.add_argument("--book-id", required=True)
    parser.add_argument("--raw-root", type=Path, default=Path("datasets/raw_books"))
    parser.add_argument("--processed-root", type=Path, default=Path("datasets/processed_books"))
    args = parser.parse_args()

    records = prepare_from_zip(args.zip_path, args.book_id, args.raw_root, args.processed_root)
    print(json.dumps({
        "book_id": args.book_id,
        "pages": len(records),
        "raw_dir": str(args.raw_root / args.book_id),
        "processed_dir": str(args.processed_root / args.book_id),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
