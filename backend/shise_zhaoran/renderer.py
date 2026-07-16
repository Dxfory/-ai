"""Independent image-edit adapter for mineral-pigment glazing."""

import base64
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import httpx
from PIL import Image, ImageOps


DEFAULT_MODEL = "gpt-image-2"
DEFAULT_API_BASE = "https://api.openai.com/v1"


@dataclass(frozen=True)
class RendererConfig:
    api_key: str | None
    base_url: str
    model: str
    timeout_seconds: float
    max_image_side: int


def resolve_renderer_config() -> RendererConfig:
    api_key = (
        os.getenv("SHISE_ZHAORAN_API_KEY")
        or os.getenv("FENRAN_API_KEY")
        or os.getenv("BAIMIAO_API_KEY")
        or os.getenv("OPENAI_API_KEY")
    )
    base_url = (
        os.getenv("SHISE_ZHAORAN_API_BASE")
        or os.getenv("FENRAN_API_BASE")
        or os.getenv("BAIMIAO_API_BASE")
        or os.getenv("OPENAI_BASE_URL")
        or os.getenv("OPENAI_API_BASE")
        or DEFAULT_API_BASE
    ).rstrip("/")
    if not base_url.endswith("/v1"):
        base_url = f"{base_url}/v1"
    model = os.getenv("SHISE_ZHAORAN_IMAGE_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    timeout = float(os.getenv("SHISE_ZHAORAN_IMAGE_TIMEOUT_SECONDS", "240"))
    max_image_side = max(256, int(os.getenv("SHISE_ZHAORAN_API_MAX_IMAGE_SIDE", "1024")))
    return RendererConfig(
        api_key=api_key,
        base_url=base_url,
        model=model,
        timeout_seconds=timeout,
        max_image_side=max_image_side,
    )


def render_shise_zhaoran(
    *,
    upstream_image: str,
    reference_image: str | None,
    prompt: str,
    output_path: str,
    render_image: Callable[..., dict | str | None] | None = None,
) -> dict:
    config = resolve_renderer_config()
    input_image = ImageOps.exif_transpose(Image.open(upstream_image)).convert("RGB")
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    size = _image_size(input_image.size)
    restore_metadata: dict | None = None

    if render_image is not None:
        result = render_image(
            model=config.model,
            prompt=prompt,
            size=size,
            upstream_image=upstream_image,
            reference_image=reference_image,
            output_path=str(output),
        )
        if isinstance(result, str):
            output = Path(result)
        elif isinstance(result, dict) and result.get("output_path"):
            output = Path(result["output_path"])
    else:
        restore_metadata = _call_image_edit_api(
            config=config,
            image_path=upstream_image,
            reference_image=reference_image,
            prompt=prompt,
            size=size,
            output_path=output,
        )

    if not output.is_file():
        raise RuntimeError("Shise Zhaoran renderer did not produce an output image")
    rendered = ImageOps.exif_transpose(Image.open(output)).convert("RGB")
    if restore_metadata:
        rendered = _restore_from_api_canvas(rendered, input_image.size, restore_metadata)
    elif rendered.size != input_image.size:
        rendered = ImageOps.contain(rendered, input_image.size, method=Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", input_image.size, "white")
        offset = ((canvas.width - rendered.width) // 2, (canvas.height - rendered.height) // 2)
        canvas.paste(rendered, offset)
        rendered = canvas
    rendered.save(output_path)
    return {
        "output_path": output_path,
        "model": config.model,
        "api_base": config.base_url,
        "input_size": list(input_image.size),
        "output_size": list(rendered.size),
    }


def _call_image_edit_api(
    *,
    config: RendererConfig,
    image_path: str,
    reference_image: str | None,
    prompt: str,
    size: str,
    output_path: Path,
) -> dict:
    if not config.api_key:
        raise RuntimeError("Missing SHISE_ZHAORAN_API_KEY, FENRAN_API_KEY, or BAIMIAO_API_KEY")
    url = f"{config.base_url}/images/edits"
    headers = {"Authorization": f"Bearer {config.api_key}"}
    data = {"model": config.model, "prompt": prompt, "size": size}
    prepared = _prepare_api_inputs(
        image_path=image_path,
        reference_image=reference_image,
        artifact_dir=output_path.parent,
        model_size=size,
        max_side=config.max_image_side,
    )
    attempts: list[dict] = []
    try:
        with httpx.Client(timeout=config.timeout_seconds) as client:
            response = _post_image_edit(client, url, headers, data, prepared["paths"])
            attempts.append(_response_summary(response, "multi" if len(prepared["paths"]) > 1 else "single"))
            if response.status_code >= 400 and len(prepared["paths"]) > 1 and _should_fallback(response.status_code):
                response = _post_image_edit(client, url, headers, data, prepared["paths"][:1])
                attempts.append(_response_summary(response, "single_fallback"))
            if response.status_code >= 400:
                detail = response.text[:800]
                _write_render_error(
                    output_path,
                    status_code=response.status_code,
                    detail=detail,
                    attempts=attempts,
                    prepared=prepared,
                )
                raise RuntimeError(f"Shise Zhaoran image API failed ({response.status_code}): {detail}")
            payload = response.json()
    except (httpx.HTTPError, TimeoutError) as exc:
        _write_render_error(
            output_path,
            status_code=None,
            detail=str(exc),
            attempts=attempts,
            prepared=prepared,
        )
        raise RuntimeError(f"Shise Zhaoran image API request failed: {exc}") from exc
    item = (payload.get("data") or [{}])[0]
    if item.get("b64_json"):
        output_path.write_bytes(base64.b64decode(item["b64_json"]))
        return prepared
    if item.get("url"):
        with httpx.Client(timeout=config.timeout_seconds) as client:
            image_response = client.get(item["url"])
            image_response.raise_for_status()
        output_path.write_bytes(image_response.content)
        return prepared
    _write_render_error(
        output_path,
        status_code=200,
        detail="Image API returned no b64_json or url",
        attempts=attempts,
        prepared=prepared,
    )
    raise RuntimeError("Shise Zhaoran image API returned no image data")


def _image_size(size: tuple[int, int]) -> str:
    requested = os.getenv("SHISE_ZHAORAN_IMAGE_SIZE", "auto").strip()
    if requested and requested.lower() != "auto":
        return requested
    width, height = size
    if width >= height * 1.05:
        return "1536x1024"
    if height >= width * 1.05:
        return "1024x1536"
    return "1024x1024"


def _prepare_api_inputs(
    *,
    image_path: str,
    reference_image: str | None,
    artifact_dir: Path,
    model_size: str,
    max_side: int,
) -> dict:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    model_width, model_height = (int(value) for value in model_size.split("x"))
    scale = min(max_side / max(model_width, model_height), 1.0)
    canvas_size = (max(1, round(model_width * scale)), max(1, round(model_height * scale)))
    upstream = ImageOps.exif_transpose(Image.open(image_path)).convert("RGB")
    upstream_canvas, content_box = _letterbox(upstream, canvas_size)
    upstream_path = artifact_dir / "api_upstream.jpg"
    upstream_canvas.save(upstream_path, quality=90, optimize=True)
    paths = [upstream_path]

    if reference_image and Path(reference_image).is_file():
        reference = ImageOps.exif_transpose(Image.open(reference_image)).convert("RGB")
        reference_canvas, _ = _letterbox(reference, canvas_size)
        reference_path = artifact_dir / "api_reference.jpg"
        reference_canvas.save(reference_path, quality=88, optimize=True)
        paths.append(reference_path)

    return {
        "paths": paths,
        "canvas_size": list(canvas_size),
        "content_box": list(content_box),
        "input_bytes": {path.name: path.stat().st_size for path in paths},
    }


def _letterbox(image: Image.Image, canvas_size: tuple[int, int]) -> tuple[Image.Image, tuple[int, int, int, int]]:
    contained = ImageOps.contain(image, canvas_size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", canvas_size, (250, 248, 242))
    left = (canvas.width - contained.width) // 2
    top = (canvas.height - contained.height) // 2
    canvas.paste(contained, (left, top))
    return canvas, (left, top, left + contained.width, top + contained.height)


def _restore_from_api_canvas(rendered: Image.Image, source_size: tuple[int, int], metadata: dict) -> Image.Image:
    canvas_width, canvas_height = metadata["canvas_size"]
    left, top, right, bottom = metadata["content_box"]
    scale_x = rendered.width / max(1, canvas_width)
    scale_y = rendered.height / max(1, canvas_height)
    crop_box = (
        round(left * scale_x),
        round(top * scale_y),
        round(right * scale_x),
        round(bottom * scale_y),
    )
    content = rendered.crop(crop_box)
    return content.resize(source_size, Image.Resampling.LANCZOS)


def _post_image_edit(client: httpx.Client, url: str, headers: dict, data: dict, paths: list[Path]):
    handles = [path.open("rb") for path in paths]
    try:
        files = [
            ("image", (path.name, handle, _mime_type(path)))
            for path, handle in zip(paths, handles, strict=True)
        ]
        return client.post(url, headers=headers, data=data, files=files)
    finally:
        for handle in handles:
            handle.close()


def _should_fallback(status_code: int) -> bool:
    return status_code in {400, 413, 415, 422, 524}


def _response_summary(response, mode: str) -> dict:
    return {"mode": mode, "status_code": response.status_code, "detail": response.text[:300]}


def _write_render_error(
    output_path: Path,
    *,
    status_code: int | None,
    detail: str,
    attempts: list[dict],
    prepared: dict,
) -> None:
    payload = {
        "status_code": status_code,
        "detail": detail[:800],
        "attempts": attempts,
        "api_canvas_size": prepared["canvas_size"],
        "content_box": prepared["content_box"],
        "input_bytes": prepared["input_bytes"],
    }
    (output_path.parent / "render_error.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _mime_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".webp":
        return "image/webp"
    return "image/png"
