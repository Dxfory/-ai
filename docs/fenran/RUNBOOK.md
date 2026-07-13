# Fenran Runbook

## Env

Set these before running the real model path:

```bash
FENRAN_API_KEY=...
FENRAN_API_BASE=https://api.openai.com/v1
FENRAN_IMAGE_MODEL=gpt-image-2
```

## Test

```bash
python -m pytest tests/test_fenran_training.py
```

## Flow

1. Upload reference with `POST /api/v1/uploads/reference`.
2. Generate white draft with `POST /api/v1/line-drafts/generate`, or upload an existing white draft with `POST /api/v1/line-drafts/upload`.
3. Create fenran render with `POST /api/v1/fenran/training-renders`.
4. Open the result under `/uploads/fenran_training/{sample_id}.png`.

## Request Example

```json
{
  "reference_upload_id": "...",
  "line_draft_id": "...",
  "teaching_goal": "先浅后深，保留纸白"
}
```
