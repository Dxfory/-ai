"""Use a vision model to extract OCR, figure binding, and technique units.

Outputs are written under `datasets/processed_books/<book>/ocr/`, which is
ignored by git because it may contain copyrighted book text.
"""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import re
from pathlib import Path
from typing import Any

import httpx
from PIL import Image


SYSTEM_PROMPT = """你是工笔花鸟临摹教材的图文结构抽取助手。
你的任务不是改写教材，也不是生成新教程，而是把页面上的视觉信息和文字说明整理成结构化 JSON。
重点关注：
1. OCR 主要文字、标题、图号、图注。
2. 每个图号对应的图像内容与附近文字说明。
3. 形理逻辑：真实物象如何转成画面结构、枝叶/花果/禽鸟如何穿插、遮挡、转折。
4. 白描逻辑：哪些线是骨架线，哪些线表达质感、转折、包裹、虚实、疏密。
5. 技法步骤：对象、材料/颜色、动作、先后顺序、等待/干后/固色等条件、常见风险。

只返回 JSON，不要返回 Markdown。不要逐字长篇复刻整页文字；保留必要短摘录和你抽取出的结构。"""


USER_PROMPT = """请分析这页工笔花鸟教材扫描页，并返回如下 JSON：
{
  "page_id": "",
  "page_index": 0,
  "page_type": "form_logic|baimiao_logic|coloring_step|finished_artwork|mixed|unknown",
  "ocr_summary": {
    "titles": [],
    "figure_numbers": [],
    "short_text_summary": "",
    "key_terms": []
  },
  "figures": [
    {
      "figure_no": "图8",
      "visual_content": "",
      "role": "reference_photo|artwork_detail|baimiao|coloring_step|finished_artwork|unknown",
      "linked_text_summary": ""
    }
  ],
  "form_logic_units": [
    {
      "object": "",
      "structural_observation": "",
      "artistic_transformation": "",
      "line_logic": "",
      "linked_figure_nos": []
    }
  ],
  "technique_units": [
    {
      "step_order": null,
      "objects": [],
      "materials_or_colors": [],
      "actions": [],
      "conditions": [],
      "warnings": [],
      "linked_figure_nos": []
    }
  ],
  "baimiao_quality_rules": [],
  "needs_human_review": []
}"""


def load_env_file(env_path: Path) -> None:
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load_pages(processed_book_dir: Path) -> list[dict[str, Any]]:
    pages_path = processed_book_dir / "pages.jsonl"
    return [
        json.loads(line)
        for line in pages_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def encode_image(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


def image_data_url(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    return f"data:{mime};base64,{encode_image(path)}"


def normalize_base_url(base_url: str) -> str:
    base_url = base_url.rstrip("/")
    if not base_url.endswith("/v1"):
        base_url = f"{base_url}/v1"
    return base_url


def extract_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def prepare_model_image(page: dict[str, Any], output_dir: Path, max_side: int) -> Path:
    source_path = Path(page["raw_path"])
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{page['page_id']}_vision.jpg"
    with Image.open(source_path).convert("RGB") as img:
        img.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
        img.save(output_path, format="JPEG", quality=88, optimize=True)
    return output_path


def call_vision_model(
    page: dict[str, Any],
    model: str,
    base_url: str,
    api_key: str,
    image_path: Path,
) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"page_id={page['page_id']}, page_index={page['page_index']}\n{USER_PROMPT}"},
                    {"type": "image_url", "image_url": {"url": image_data_url(image_path)}},
                ],
            },
        ],
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    with httpx.Client(timeout=180) as client:
        response = client.post(f"{base_url}/chat/completions", headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
    content = data["choices"][0]["message"]["content"]
    result = extract_json(content)
    result.setdefault("page_id", page["page_id"])
    result.setdefault("page_index", page["page_index"])
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("processed_book_dir", type=Path)
    parser.add_argument("--pages", required=True, help="Comma-separated 1-based page numbers, e.g. 18,26,27,30")
    parser.add_argument("--env", type=Path, default=Path(".env"))
    parser.add_argument("--max-image-side", type=int, default=1600)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    load_env_file(args.env)
    api_key = os.getenv("TEACHING_VISION_API_KEY") or os.getenv("OPENAI_API_KEY") or os.getenv("BAIMIAO_API_KEY")
    base_url = normalize_base_url(
        os.getenv("TEACHING_VISION_API_BASE")
        or os.getenv("BAIMIAO_API_BASE")
        or os.getenv("OPENAI_BASE_URL")
        or os.getenv("OPENAI_API_BASE")
        or "https://api.openai.com/v1"
    )
    model = os.getenv("TEACHING_VISION_MODEL", "gpt-5.5")

    selected = {
        int(value.strip())
        for value in args.pages.split(",")
        if value.strip()
    }
    pages = [page for page in load_pages(args.processed_book_dir) if page["page_index"] in selected]
    output_dir = args.processed_book_dir / "ocr"
    model_image_dir = output_dir / "model_images"
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.dry_run:
        print(json.dumps({
            "model": model,
            "base_url": base_url,
            "pages": [page["page_index"] for page in pages],
            "output_dir": str(output_dir),
            "max_image_side": args.max_image_side,
            "has_api_key": bool(api_key),
        }, ensure_ascii=False, indent=2))
        return

    if not api_key:
        raise RuntimeError("Missing TEACHING_VISION_API_KEY, OPENAI_API_KEY, or BAIMIAO_API_KEY")

    outputs = []
    for page in pages:
        image_path = prepare_model_image(page, model_image_dir, args.max_image_side)
        result = call_vision_model(
            page,
            model=model,
            base_url=base_url,
            api_key=api_key,
            image_path=image_path,
        )
        output_path = output_dir / f"{page['page_id']}_teaching_units.json"
        output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        outputs.append(str(output_path))

    print(json.dumps({
        "pages": len(outputs),
        "outputs": outputs,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
