"""File-level cache for completed Fenran render manifests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_fenran_cache_key(
    *,
    original_path: str,
    registered_baimiao_path: str,
    registration_id: str,
    include_base_color: bool,
    teaching_plan_version: str,
    prompt_version: str,
    model: str,
    image_size: str,
    teaching_goal: str,
    renderer_version: str,
    api_base: str = "",
    validation_signature: str = "",
    runtime_signature: str = "",
) -> str:
    values = (
        file_sha256(original_path),
        file_sha256(registered_baimiao_path),
        registration_id,
        str(include_base_color),
        teaching_plan_version,
        prompt_version,
        model,
        image_size,
        teaching_goal,
        renderer_version,
        api_base,
        validation_signature,
        runtime_signature,
    )
    return hashlib.sha256("|".join(values).encode("utf-8")).hexdigest()


def load_cached_manifest(cache_root: str | Path, cache_key: str) -> Path | None:
    record_path = Path(cache_root) / f"{cache_key}.json"
    if not record_path.exists():
        return None
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
        manifest_path = Path(record["manifest_path"])
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, KeyError, json.JSONDecodeError):
        return None
    if manifest.get("status") != "ready":
        return None
    output_path = Path(manifest.get("output_path", ""))
    stage_paths = [Path(stage.get("output_path", "")) for stage in manifest.get("stages", [])]
    if not output_path.is_file() or any(not path.is_file() for path in stage_paths):
        return None
    return manifest_path


def save_cache_record(cache_root: str | Path, cache_key: str, manifest_path: str | Path) -> None:
    root = Path(cache_root)
    root.mkdir(parents=True, exist_ok=True)
    destination = root / f"{cache_key}.json"
    temporary = destination.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps({"cache_key": cache_key, "manifest_path": str(Path(manifest_path).resolve())}, indent=2),
        encoding="utf-8",
    )
    temporary.replace(destination)
