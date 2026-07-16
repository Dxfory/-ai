# Fenran Runbook

## Environment

```text
FENRAN_API_KEY=...
FENRAN_API_BASE=https://api.openai.com/v1
FENRAN_IMAGE_MODEL=gpt-image-2
FENRAN_IMAGE_SIZE=auto
FENRAN_MAX_ATTEMPTS=3
FENRAN_FAIL_CLOSED=true
FENRAN_ALLOW_SINGLE_REFERENCE_FALLBACK=false
FENRAN_ENABLE_CACHE=true
```

The Fenran key is independent from baimiao and teaching-vision keys. Do not commit a real key.

## Flow

1. Upload an original reference.
2. Generate or upload a white draft.
3. Open `配准编辑`, inspect the shared canonical overlay, and save an approved registration.
4. Choose whether to make a base color. The default is off.
5. Start Fenran. The response displays all complete stage images in source proportion.

Without approved registration the API returns `409 registration_review`. Provider errors return `502`; validation exhaustion returns `422 review_required`. A cache hit is returned without another model call unless `force_regenerate=true`.

## Test

```powershell
python -m pytest -q
node --check frontend/app.js
```
