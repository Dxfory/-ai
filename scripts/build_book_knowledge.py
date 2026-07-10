"""Build a lightweight book-level knowledge summary from extracted pages.

The full page-level OCR outputs stay local under `ocr/`. This script writes a
compact summary that can be committed without copying long book text.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_page_outputs(ocr_dir: Path) -> list[dict[str, Any]]:
    outputs = []
    for path in sorted(ocr_dir.glob("*_teaching_units.json")):
        outputs.append(json.loads(path.read_text(encoding="utf-8")))
    return sorted(outputs, key=lambda item: item.get("page_index", 0))


def list_values(items: list[dict[str, Any]], key: str) -> list[str]:
    values: list[str] = []
    for item in items:
        value = item.get(key)
        if isinstance(value, str) and value and value not in values:
            values.append(value)
    return values


def collect_short(items: list[Any], limit: int) -> list[Any]:
    return items[:limit]


def build_book_knowledge(processed_book_dir: Path) -> dict[str, Any]:
    ocr_dir = processed_book_dir / "ocr"
    pages = load_page_outputs(ocr_dir)
    page_summaries = []
    figure_index = []
    line_rules = []
    faithfulness_constraints = []
    technique_units = []
    review_pages = []

    for page in pages:
        ocr_summary = page.get("ocr_summary", {}) or {}
        page_summaries.append({
            "page_id": page.get("page_id"),
            "page_index": page.get("page_index"),
            "page_type": page.get("page_type", "unknown"),
            "titles": ocr_summary.get("titles", []),
            "figure_numbers": ocr_summary.get("figure_numbers", []),
            "short_text_summary": ocr_summary.get("short_text_summary", ""),
            "key_terms": ocr_summary.get("key_terms", []),
            "has_existing_ink_line_observations": bool(page.get("existing_ink_line_observations")),
            "has_technique_units": bool(page.get("technique_units")),
        })

        for figure in page.get("figures", []) or []:
            figure_index.append({
                "page_index": page.get("page_index"),
                "figure_no": figure.get("figure_no", ""),
                "role": figure.get("role", "unknown"),
                "visual_content": figure.get("visual_content", ""),
            })

        for observation in page.get("existing_ink_line_observations", []) or []:
            line_rules.append({
                "page_index": page.get("page_index"),
                "source_figure_no": observation.get("source_figure_no", ""),
                "object": observation.get("object", ""),
                "line_function": observation.get("line_function", "unknown"),
                "line_extraction_rule": observation.get("line_extraction_rule", ""),
                "do_not_invent": observation.get("do_not_invent", []),
            })

        for rule in page.get("baimiao_quality_rules", []) or []:
            if rule not in faithfulness_constraints:
                faithfulness_constraints.append(rule)
        for constraint in page.get("faithfulness_constraints", []) or []:
            if constraint not in faithfulness_constraints:
                faithfulness_constraints.append(constraint)

        for unit in page.get("technique_units", []) or []:
            technique_units.append({
                "page_index": page.get("page_index"),
                "step_order": unit.get("step_order"),
                "objects": unit.get("objects", []),
                "materials_or_colors": unit.get("materials_or_colors", []),
                "actions": unit.get("actions", []),
                "conditions": unit.get("conditions", []),
                "warnings": unit.get("warnings", []),
                "linked_figure_nos": unit.get("linked_figure_nos", []),
            })

        if page.get("needs_human_review"):
            review_pages.append({
                "page_index": page.get("page_index"),
                "needs_human_review": page.get("needs_human_review", []),
            })

    return {
        "book_id": processed_book_dir.name,
        "source_scope": "full scanned technique book pages",
        "page_count": len(pages),
        "core_learning_goal": "Learn existing author-drawn gongbi ink line logic from original artworks and book baimiao drafts; do not invent new structure.",
        "page_summaries": page_summaries,
        "figure_index": figure_index,
        "existing_ink_line_rules": line_rules,
        "technique_units": technique_units,
        "faithfulness_constraints": collect_short(faithfulness_constraints, 80),
        "review_pages": review_pages,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("processed_book_dir", type=Path)
    args = parser.parse_args()

    knowledge = build_book_knowledge(args.processed_book_dir)
    output_path = args.processed_book_dir / "book_knowledge.json"
    output_path.write_text(json.dumps(knowledge, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "book_id": knowledge["book_id"],
        "page_count": knowledge["page_count"],
        "figures": len(knowledge["figure_index"]),
        "line_rules": len(knowledge["existing_ink_line_rules"]),
        "technique_units": len(knowledge["technique_units"]),
        "output": str(output_path),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
