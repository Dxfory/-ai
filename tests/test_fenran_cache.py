import json
from pathlib import Path

from backend.services.fenran_cache import build_fenran_cache_key, load_cached_manifest, save_cache_record


def test_cache_key_changes_for_plan_inputs_but_is_stable_for_same_input(tmp_path):
    original = tmp_path / "original.png"
    baimiao = tmp_path / "baimiao.png"
    original.write_bytes(b"original")
    baimiao.write_bytes(b"baimiao")
    kwargs = dict(
        original_path=str(original),
        registered_baimiao_path=str(baimiao),
        registration_id="registration-1",
        include_base_color=False,
        teaching_plan_version="plan-v1",
        prompt_version="prompt-v1",
        model="gpt-image-2",
        image_size="auto",
        teaching_goal="goal",
        renderer_version="renderer-v1",
        api_base="https://provider-a.example/v1",
        validation_signature="iou=0.90",
        runtime_signature="fallback=false|fail_closed=true",
    )

    first = build_fenran_cache_key(**kwargs)
    second = build_fenran_cache_key(**kwargs)
    changed = build_fenran_cache_key(**(kwargs | {"include_base_color": True}))
    changed_threshold = build_fenran_cache_key(**(kwargs | {"validation_signature": "iou=0.95"}))

    assert first == second
    assert first != changed
    assert first != changed_threshold


def test_cache_record_returns_only_existing_ready_manifest(tmp_path):
    cache_root = tmp_path / ".cache"
    manifest = tmp_path / "sample" / "render_manifest.json"
    manifest.parent.mkdir()
    output = manifest.parent / "selected.png"
    output.write_bytes(b"image")
    manifest.write_text(json.dumps({"status": "ready", "output_path": str(output), "stages": []}), encoding="utf-8")

    save_cache_record(cache_root, "abc", manifest)

    assert load_cached_manifest(cache_root, "abc") == manifest
    manifest.write_text(json.dumps({"status": "review_required"}), encoding="utf-8")
    assert load_cached_manifest(cache_root, "abc") is None


def test_cache_miss_when_manifest_points_to_missing_output(tmp_path):
    cache_root = tmp_path / ".cache"
    manifest = tmp_path / "sample" / "render_manifest.json"
    manifest.parent.mkdir()
    manifest.write_text(
        json.dumps({"status": "ready", "output_path": str(tmp_path / "missing.png"), "stages": []}),
        encoding="utf-8",
    )
    save_cache_record(cache_root, "missing", manifest)

    assert load_cached_manifest(cache_root, "missing") is None
