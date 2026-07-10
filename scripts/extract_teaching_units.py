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
import time
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
4. 原作已有墨线/勾线逻辑：只观察原画或书中白描稿里已经存在的作者勾线，不要发明新线，不要把照片边缘当成白描线。
5. 技法步骤：对象、材料/颜色、动作、先后顺序、等待/干后/固色等条件、常见风险。

白描训练的核心约束：
- 最终要学习“原作者已经画在原作中的线”的取舍和组织逻辑。
- 判断一根线是否应该进入白描稿时，优先依据原画可见墨线、白描稿、教材文字说明。
- 不允许改变构图方向、对象数量、枝叶走势、花果/鸟体位置。
- 可以总结哪些线表达骨架、质感、转折、包裹、遮挡、虚实、疏密，但不要凭空补画不存在的结构。

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
  "existing_ink_line_observations": [
    {
      "source_figure_no": "图8",
      "object": "",
      "visible_author_lines": "",
      "line_function": "骨架|轮廓|叶脉|纹理|质感|转折|遮挡|虚实|设色边界|unknown",
      "line_extraction_rule": "",
      "do_not_invent": []
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
  "faithfulness_constraints": [],
  "needs_human_review": []
}"""


COMPACT_USER_PROMPT = """请只基于本页图像抽取工笔花鸟白描训练要点，返回 JSON：
{
  "page_id": "",
  "page_index": 0,
  "page_type": "form_logic|baimiao_logic|coloring_step|finished_artwork|mixed|unknown",
  "ocr_summary": {"titles": [], "figure_numbers": [], "short_text_summary": "", "key_terms": []},
  "figures": [{"figure_no": "", "visual_content": "", "role": "", "linked_text_summary": ""}],
  "existing_ink_line_observations": [
    {
      "source_figure_no": "",
      "object": "",
      "visible_author_lines": "",
      "line_function": "骨架|轮廓|叶脉|纹理|质感|转折|遮挡|虚实|设色边界|unknown",
      "line_extraction_rule": "",
      "do_not_invent": []
    }
  ],
  "baimiao_quality_rules": [],
  "faithfulness_constraints": [],
  "needs_human_review": []
}
重点：只学习原画或白描稿中已经存在的作者勾线，不要把照片边缘、纸纹、扫描阴影、设色色块边缘当成必须生成的白描线。"""


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


def extract_message_text(data: dict[str, Any]) -> str:
    if isinstance(data.get("output_text"), str):
        return data["output_text"]
    if isinstance(data.get("output"), list):
        parts = []
        for output_item in data["output"]:
            for content_item in output_item.get("content", []):
                if isinstance(content_item, dict):
                    parts.append(content_item.get("text") or content_item.get("output_text") or "")
        text = "\n".join(part for part in parts if part)
        if text:
            return text
    choice = data.get("choices", [{}])[0]
    message = choice.get("message") or {}
    if isinstance(message.get("content"), str):
        return message["content"]
    if isinstance(message.get("content"), list):
        parts = []
        for item in message["content"]:
            if isinstance(item, dict):
                parts.append(item.get("text") or item.get("content") or "")
        text = "\n".join(part for part in parts if part)
        if text:
            return text
    if isinstance(choice.get("text"), str):
        return choice["text"]
    raise KeyError(f"Cannot find message content in response keys: {sorted(data.keys())}")


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
    raw_response_dir: Path,
    wire_api: str,
    compact: bool,
) -> dict[str, Any]:
    if wire_api == "responses":
        return call_responses_model(
            page=page,
            model=model,
            base_url=base_url,
            api_key=api_key,
            image_path=image_path,
            raw_response_dir=raw_response_dir,
            compact=compact,
        )

    prompt = COMPACT_USER_PROMPT if compact else USER_PROMPT
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"page_id={page['page_id']}, page_index={page['page_index']}\n{prompt}"},
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
    raw_response_dir.mkdir(parents=True, exist_ok=True)
    (raw_response_dir / f"{page['page_id']}_raw_response.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    content = extract_message_text(data)
    result = extract_json(content)
    result.setdefault("page_id", page["page_id"])
    result.setdefault("page_index", page["page_index"])
    return result


def call_responses_model(
    page: dict[str, Any],
    model: str,
    base_url: str,
    api_key: str,
    image_path: Path,
    raw_response_dir: Path,
    compact: bool,
) -> dict[str, Any]:
    prompt = COMPACT_USER_PROMPT if compact else USER_PROMPT
    payload = {
        "model": model,
        "input": [
            {
                "role": "system",
                "content": [{"type": "input_text", "text": SYSTEM_PROMPT}],
            },
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": f"page_id={page['page_id']}, page_index={page['page_index']}\n{prompt}"},
                    {"type": "input_image", "image_url": image_data_url(image_path)},
                ],
            },
        ],
        "temperature": 0.1,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    with httpx.Client(timeout=180) as client:
        response = client.post(f"{base_url}/responses", headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
    raw_response_dir.mkdir(parents=True, exist_ok=True)
    (raw_response_dir / f"{page['page_id']}_raw_response.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    content = extract_message_text(data)
    result = extract_json(content)
    result.setdefault("page_id", page["page_id"])
    result.setdefault("page_index", page["page_index"])
    return result


def parse_selected_pages(value: str, pages: list[dict[str, Any]]) -> set[int]:
    if value.strip().lower() == "all":
        return {page["page_index"] for page in pages}
    return {
        int(part.strip())
        for part in value.split(",")
        if part.strip()
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("processed_book_dir", type=Path)
    parser.add_argument("--pages", required=True, help="Comma-separated 1-based page numbers, or all")
    parser.add_argument("--env", type=Path, default=Path(".env"))
    parser.add_argument("--max-image-side", type=int, default=1600)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--retry-sleep", type=float, default=4.0)
    parser.add_argument("--compact", action="store_true")
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
    wire_api = os.getenv("TEACHING_VISION_WIRE_API", "responses").strip().lower()

    all_pages = load_pages(args.processed_book_dir)
    selected = parse_selected_pages(args.pages, all_pages)
    pages = [page for page in all_pages if page["page_index"] in selected]
    output_dir = args.processed_book_dir / "ocr"
    model_image_dir = output_dir / "model_images"
    raw_response_dir = output_dir / "raw_responses"
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.dry_run:
        print(json.dumps({
            "model": model,
            "base_url": base_url,
            "pages": [page["page_index"] for page in pages],
            "output_dir": str(output_dir),
            "max_image_side": args.max_image_side,
            "wire_api": wire_api,
            "retries": args.retries,
            "compact": args.compact,
            "has_api_key": bool(api_key),
        }, ensure_ascii=False, indent=2))
        return

    if not api_key:
        raise RuntimeError("Missing TEACHING_VISION_API_KEY, OPENAI_API_KEY, or BAIMIAO_API_KEY")

    outputs = []
    failures = []
    for page in pages:
        image_path = prepare_model_image(page, model_image_dir, args.max_image_side)
        output_path = output_dir / f"{page['page_id']}_teaching_units.json"
        try:
            result = call_with_retries(
                page=page,
                model=model,
                base_url=base_url,
                api_key=api_key,
                image_path=image_path,
                raw_response_dir=raw_response_dir,
                wire_api=wire_api,
                retries=args.retries,
                retry_sleep=args.retry_sleep,
                compact=args.compact,
            )
            output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            outputs.append(str(output_path))
        except Exception as exc:
            failure = {
                "page_id": page["page_id"],
                "page_index": page["page_index"],
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
            failures.append(failure)
            with (output_dir / "failures.jsonl").open("a", encoding="utf-8") as out:
                out.write(json.dumps(failure, ensure_ascii=False) + "\n")

    print(json.dumps({
        "pages": len(outputs),
        "outputs": outputs,
        "failures": failures,
    }, ensure_ascii=False, indent=2))


def call_with_retries(
    page: dict[str, Any],
    model: str,
    base_url: str,
    api_key: str,
    image_path: Path,
    raw_response_dir: Path,
    wire_api: str,
    retries: int,
    retry_sleep: float,
    compact: bool,
) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return call_vision_model(
                page,
                model=model,
                base_url=base_url,
                api_key=api_key,
                image_path=image_path,
                raw_response_dir=raw_response_dir,
                wire_api=wire_api,
                compact=compact,
            )
        except (httpx.HTTPError, KeyError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt >= retries:
                break
            time.sleep(retry_sleep * (attempt + 1))
    assert last_error is not None
    raise last_error


if __name__ == "__main__":
    main()
