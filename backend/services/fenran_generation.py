"""OpenAI-compatible multi-image edit transport for Fenran stages."""

from __future__ import annotations

import base64
import os
from pathlib import Path

import httpx


class FenranConfigurationError(RuntimeError):
    pass


class FenranProviderError(RuntimeError):
    pass


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _guess_mime(path: str | Path) -> str:
    suffix = Path(path).suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".webp":
        return "image/webp"
    return "image/png"


def _post_fenran_image_edit(
    client: httpx.Client,
    url: str,
    headers: dict,
    data: dict,
    image_paths: list[str],
) -> httpx.Response:
    if not image_paths:
        raise FenranConfigurationError("Fenran image edit requires at least one image")
    handles = []
    files = []
    try:
        for image_path in image_paths:
            handle = open(image_path, "rb")
            handles.append(handle)
            files.append(("image", (Path(image_path).name, handle, _guess_mime(image_path))))
        return client.post(url, headers=headers, data=data, files=files)
    finally:
        for handle in handles:
            handle.close()


def _format_provider_error(response: httpx.Response) -> str:
    body = response.text.strip().replace("\n", " ")
    if len(body) > 500:
        body = f"{body[:500]}..."
    return f"Image API returned HTTP {response.status_code}: {body or response.reason_phrase}"


def render_fenran_image(
    *,
    model: str,
    prompt: str,
    size: str,
    image_paths: list[str],
    output_path: str,
    api_key: str | None,
    base_url: str,
    timeout_seconds: float = 240,
    fallback_image_path: str | None = None,
) -> dict:
    if not api_key:
        raise FenranConfigurationError("Missing FENRAN_API_KEY")
    url = f"{base_url.rstrip('/')}/images/edits"
    headers = {"Authorization": f"Bearer {api_key}"}
    data = {"model": model, "prompt": prompt, "size": size}
    request_mode = "multi_image" if len(image_paths) > 1 else "single_image"
    fallback_used = False

    with httpx.Client(timeout=timeout_seconds) as client:
        response = _post_fenran_image_edit(client, url, headers, data, image_paths)
        if (
            response.status_code >= 400
            and _env_bool("FENRAN_ALLOW_SINGLE_REFERENCE_FALLBACK", False)
            and fallback_image_path
        ):
            response = _post_fenran_image_edit(client, url, headers, data, [fallback_image_path])
            fallback_used = response.status_code < 400
        if response.status_code >= 400:
            raise FenranProviderError(_format_provider_error(response))

        payload = response.json()
        image_data = (payload.get("data") or [{}])[0]
        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if image_data.get("b64_json"):
            destination.write_bytes(base64.b64decode(image_data["b64_json"]))
        elif image_data.get("url"):
            image_response = client.get(image_data["url"])
            image_response.raise_for_status()
            destination.write_bytes(image_response.content)
        else:
            raise FenranProviderError("Image API did not return b64_json or url")

    return {
        "raw_output_path": str(destination),
        "provider": "gpt-image-compatible",
        "request_mode": request_mode,
        "input_image_count": len(image_paths),
        "fallback_used": fallback_used,
    }
