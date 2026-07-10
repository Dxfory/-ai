"""Extract rough page-region candidates from scanned teaching-book pages.

This is a lightweight PIL-only layout pass. It does not replace OCR or a true
document-layout model; it creates stable candidate boxes that later passes can
attach OCR text, figure numbers, captions, and technique units to.
"""

from __future__ import annotations

import argparse
import json
from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path

from PIL import Image, ImageDraw


@dataclass
class RegionCandidate:
    region_id: str
    page_id: str
    page_index: int
    bbox: list[int]
    role_hint: str
    confidence: float
    dark_density: float
    notes: str = ""


def load_pages(pages_jsonl: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in pages_jsonl.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def extract_regions_for_page(
    page: dict,
    max_side: int = 1400,
    threshold: int = 245,
    cell_size: int = 10,
) -> list[RegionCandidate]:
    source_path = Path(page["raw_path"])
    with Image.open(source_path).convert("L") as img:
        original_w, original_h = img.size
        scale = min(1.0, max_side / max(original_w, original_h))
        work_w = max(1, int(original_w * scale))
        work_h = max(1, int(original_h * scale))
        work = img.resize((work_w, work_h), Image.Resampling.LANCZOS)
        pixels = work.load()

    grid_w = (work_w + cell_size - 1) // cell_size
    grid_h = (work_h + cell_size - 1) // cell_size
    occupied = [[False for _ in range(grid_w)] for _ in range(grid_h)]
    dark_counts = [[0 for _ in range(grid_w)] for _ in range(grid_h)]

    for gy in range(grid_h):
        for gx in range(grid_w):
            dark = 0
            x0 = gx * cell_size
            y0 = gy * cell_size
            x1 = min(work_w, x0 + cell_size)
            y1 = min(work_h, y0 + cell_size)
            for y in range(y0, y1):
                for x in range(x0, x1):
                    if pixels[x, y] < threshold:
                        dark += 1
            dark_counts[gy][gx] = dark
            occupied[gy][gx] = dark >= 3

    occupied = remove_border_components(occupied, margin=1)
    occupied = dilate_grid(occupied, radius=1)
    components = connected_components(occupied)
    regions: list[RegionCandidate] = []
    for comp_index, cells in enumerate(components, start=1):
        min_gx = min(gx for gx, _ in cells)
        max_gx = max(gx for gx, _ in cells)
        min_gy = min(gy for _, gy in cells)
        max_gy = max(gy for _, gy in cells)

        sx0 = min_gx * cell_size
        sy0 = min_gy * cell_size
        sx1 = min(work_w, (max_gx + 1) * cell_size)
        sy1 = min(work_h, (max_gy + 1) * cell_size)
        if (sx1 - sx0) < 28 or (sy1 - sy0) < 18:
            continue

        dark = sum(dark_counts[gy][gx] for gx, gy in cells)
        area = max(1, (sx1 - sx0) * (sy1 - sy0))
        density = dark / area

        bbox = [
            int(sx0 / scale),
            int(sy0 / scale),
            int(sx1 / scale),
            int(sy1 / scale),
        ]
        role_hint, confidence, notes = classify_region(
            bbox=bbox,
            page_width=original_w,
            page_height=original_h,
            dark_density=density,
        )
        regions.append(RegionCandidate(
            region_id=f"{page['page_id']}_region_{comp_index:03d}",
            page_id=page["page_id"],
            page_index=page["page_index"],
            bbox=bbox,
            role_hint=role_hint,
            confidence=confidence,
            dark_density=round(density, 4),
            notes=notes,
        ))

    panel_regions = extract_panel_regions(page, max_side=max_side)
    regions = merge_regions(regions + panel_regions)
    for index, region in enumerate(regions, start=1):
        region.region_id = f"{page['page_id']}_region_{index:03d}"
    return sorted(regions, key=lambda region: (region.bbox[1], region.bbox[0]))


def extract_panel_regions(page: dict, max_side: int = 1400, threshold: int = 248) -> list[RegionCandidate]:
    source_path = Path(page["raw_path"])
    with Image.open(source_path).convert("L") as img:
        original_w, original_h = img.size
        scale = min(1.0, max_side / max(original_w, original_h))
        work_w = max(1, int(original_w * scale))
        work_h = max(1, int(original_h * scale))
        work = img.resize((work_w, work_h), Image.Resampling.LANCZOS)
        pixels = work.load()

    margin_x = int(work_w * 0.035)
    margin_y = int(work_h * 0.025)
    row_counts: list[int] = []
    for y in range(work_h):
        if y < margin_y or y >= work_h - margin_y:
            row_counts.append(0)
            continue
        count = 0
        for x in range(margin_x, work_w - margin_x):
            if pixels[x, y] < threshold:
                count += 1
        row_counts.append(count)

    row_groups = ranges_from_activity(
        [count > work_w * 0.10 for count in row_counts],
        min_len=max(8, int(work_h * 0.018)),
        gap=max(2, int(work_h * 0.004)),
    )

    regions: list[RegionCandidate] = []
    for y0, y1 in row_groups:
        group_h = y1 - y0
        col_counts: list[int] = []
        for x in range(work_w):
            if x < margin_x or x >= work_w - margin_x:
                col_counts.append(0)
                continue
            count = 0
            for y in range(y0, y1):
                if pixels[x, y] < threshold:
                    count += 1
            col_counts.append(count)
        col_groups = ranges_from_activity(
            [count > group_h * 0.07 for count in col_counts],
            min_len=max(8, int(work_w * 0.035)),
            gap=max(2, int(work_w * 0.006)),
        )
        for x0, x1 in col_groups:
            bbox = [
                int(x0 / scale),
                int(y0 / scale),
                int(x1 / scale),
                int(y1 / scale),
            ]
            role_hint, confidence, notes = classify_region(
                bbox=bbox,
                page_width=original_w,
                page_height=original_h,
                dark_density=0,
            )
            if role_hint == "mixed_candidate":
                role_hint = "panel_candidate"
                confidence = 0.52
                notes = "Projection-detected panel; likely image, caption group, or step block."
            regions.append(RegionCandidate(
                region_id="",
                page_id=page["page_id"],
                page_index=page["page_index"],
                bbox=bbox,
                role_hint=role_hint,
                confidence=confidence,
                dark_density=0,
                notes=notes,
            ))
    return regions


def ranges_from_activity(active: list[bool], min_len: int, gap: int) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    start: int | None = None
    last_active = 0
    for index, is_active in enumerate(active):
        if is_active:
            if start is None:
                start = index
            last_active = index
        elif start is not None and index - last_active > gap:
            if last_active + 1 - start >= min_len:
                ranges.append((start, last_active + 1))
            start = None
    if start is not None and last_active + 1 - start >= min_len:
        ranges.append((start, last_active + 1))
    return ranges


def merge_regions(regions: list[RegionCandidate]) -> list[RegionCandidate]:
    merged: list[RegionCandidate] = []
    for region in sorted(regions, key=lambda item: box_area(item.bbox), reverse=True):
        if any(iou(region.bbox, existing.bbox) > 0.78 for existing in merged):
            continue
        merged.append(region)
    return sorted(merged, key=lambda item: (item.bbox[1], item.bbox[0]))


def box_area(bbox: list[int]) -> int:
    return max(0, bbox[2] - bbox[0]) * max(0, bbox[3] - bbox[1])


def iou(a: list[int], b: list[int]) -> float:
    x0 = max(a[0], b[0])
    y0 = max(a[1], b[1])
    x1 = min(a[2], b[2])
    y1 = min(a[3], b[3])
    inter = box_area([x0, y0, x1, y1])
    union = box_area(a) + box_area(b) - inter
    return inter / union if union else 0


def dilate_grid(grid: list[list[bool]], radius: int) -> list[list[bool]]:
    height = len(grid)
    width = len(grid[0]) if height else 0
    output = [[False for _ in range(width)] for _ in range(height)]
    for y in range(height):
        for x in range(width):
            if not grid[y][x]:
                continue
            for yy in range(max(0, y - radius), min(height, y + radius + 1)):
                for xx in range(max(0, x - radius), min(width, x + radius + 1)):
                    output[yy][xx] = True
    return output


def remove_border_components(grid: list[list[bool]], margin: int) -> list[list[bool]]:
    height = len(grid)
    width = len(grid[0]) if height else 0
    output = [row[:] for row in grid]
    for cells in connected_components(grid):
        touches_border = any(
            gx <= margin
            or gy <= margin
            or gx >= width - margin - 1
            or gy >= height - margin - 1
            for gx, gy in cells
        )
        if touches_border:
            for gx, gy in cells:
                output[gy][gx] = False
    return output


def connected_components(grid: list[list[bool]]) -> list[list[tuple[int, int]]]:
    height = len(grid)
    width = len(grid[0]) if height else 0
    seen = [[False for _ in range(width)] for _ in range(height)]
    components: list[list[tuple[int, int]]] = []
    for y in range(height):
        for x in range(width):
            if seen[y][x] or not grid[y][x]:
                continue
            queue: deque[tuple[int, int]] = deque([(x, y)])
            seen[y][x] = True
            cells: list[tuple[int, int]] = []
            while queue:
                cx, cy = queue.popleft()
                cells.append((cx, cy))
                for nx, ny in ((cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1)):
                    if nx < 0 or ny < 0 or nx >= width or ny >= height:
                        continue
                    if seen[ny][nx] or not grid[ny][nx]:
                        continue
                    seen[ny][nx] = True
                    queue.append((nx, ny))
            components.append(cells)
    return components


def classify_region(
    bbox: list[int],
    page_width: int,
    page_height: int,
    dark_density: float,
) -> tuple[str, float, str]:
    x0, y0, x1, y1 = bbox
    width = x1 - x0
    height = y1 - y0
    area_ratio = (width * height) / max(1, page_width * page_height)
    aspect = width / max(1, height)

    if area_ratio > 0.22:
        return "large_figure_or_full_artwork", 0.72, "Large visual block; inspect as artwork or full-page figure."
    if area_ratio > 0.055 and dark_density > 0.015:
        return "figure_candidate", 0.68, "Dense visual block; likely artwork detail, photo, or line drawing."
    if aspect > 2.5 and height < page_height * 0.18:
        return "text_candidate", 0.58, "Wide low-height block; likely title, paragraph, caption, or page note."
    if area_ratio < 0.018:
        return "caption_or_figure_number", 0.48, "Small block; may be figure number, caption, or short label."
    return "mixed_candidate", 0.45, "Needs OCR/layout-model review."


def write_preview(page: dict, regions: list[RegionCandidate], output_dir: Path) -> None:
    source_path = Path(page["raw_path"])
    output_dir.mkdir(parents=True, exist_ok=True)
    with Image.open(source_path).convert("RGB") as img:
        img.thumbnail((1200, 1200), Image.Resampling.LANCZOS)
        scale_x = img.width / page["width"]
        scale_y = img.height / page["height"]
        draw = ImageDraw.Draw(img)
        colors = {
            "large_figure_or_full_artwork": "red",
            "figure_candidate": "orange",
            "text_candidate": "blue",
            "caption_or_figure_number": "purple",
            "mixed_candidate": "green",
        }
        for region in regions:
            x0, y0, x1, y1 = region.bbox
            box = [x0 * scale_x, y0 * scale_y, x1 * scale_x, y1 * scale_y]
            color = colors.get(region.role_hint, "green")
            draw.rectangle(box, outline=color, width=3)
            draw.text((box[0] + 4, box[1] + 4), region.role_hint, fill=color)
        img.save(output_dir / f"{page['page_id']}_layout.jpg", quality=88, optimize=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("processed_book_dir", type=Path)
    parser.add_argument("--pages", default="", help="Comma-separated 1-based page numbers, e.g. 18,26,27,30")
    parser.add_argument("--write-previews", action="store_true")
    args = parser.parse_args()

    pages = load_pages(args.processed_book_dir / "pages.jsonl")
    selected = {
        int(value.strip())
        for value in args.pages.split(",")
        if value.strip()
    }
    if selected:
        pages = [page for page in pages if page["page_index"] in selected]

    all_regions: list[dict] = []
    for page in pages:
        regions = extract_regions_for_page(page)
        all_regions.append({
            "page_id": page["page_id"],
            "page_index": page["page_index"],
            "regions": [asdict(region) for region in regions],
        })
        if args.write_previews:
            write_preview(page, regions, args.processed_book_dir / "layout_previews")

    output = {
        "book_id": pages[0]["book_id"] if pages else "",
        "purpose": "Rough layout candidates for OCR, figure-number binding, and technique-unit extraction.",
        "pages": all_regions,
    }
    output_path = args.processed_book_dir / "layout_candidates.json"
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "pages": len(all_regions),
        "regions": sum(len(page["regions"]) for page in all_regions),
        "output": str(output_path),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
