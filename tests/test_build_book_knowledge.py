import json

from scripts.build_book_knowledge import build_book_knowledge


def test_build_book_knowledge(tmp_path):
    book_dir = tmp_path / "book_test"
    ocr_dir = book_dir / "ocr"
    ocr_dir.mkdir(parents=True)
    (ocr_dir / "book_test_page_001_teaching_units.json").write_text(
        json.dumps({
            "page_id": "book_test_page_001",
            "page_index": 1,
            "page_type": "baimiao_logic",
            "ocr_summary": {"titles": ["技法"], "figure_numbers": ["图1"], "short_text_summary": "summary", "key_terms": ["白描"]},
            "figures": [{"figure_no": "图1", "role": "baimiao", "visual_content": "line draft"}],
            "existing_ink_line_observations": [{"source_figure_no": "图1", "object": "叶片", "line_function": "叶脉", "line_extraction_rule": "keep visible veins", "do_not_invent": ["hidden veins"]}],
            "technique_units": [{"step_order": 1, "objects": ["叶片"], "materials_or_colors": [], "actions": ["勾线"]}],
            "baimiao_quality_rules": ["只取已有线"],
        }, ensure_ascii=False),
        encoding="utf-8",
    )

    knowledge = build_book_knowledge(book_dir)

    assert knowledge["page_count"] == 1
    assert knowledge["figure_index"][0]["figure_no"] == "图1"
    assert knowledge["existing_ink_line_rules"][0]["object"] == "叶片"
    assert knowledge["technique_units"][0]["actions"] == ["勾线"]
