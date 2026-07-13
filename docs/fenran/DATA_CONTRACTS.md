# Fenran Data Contracts

## Fenran Training Render Request

```json
{
  "reference_upload_id": "string",
  "line_draft_id": "string",
  "sample_id": "string",
  "teaching_goal": "string"
}
```

## Fenran Training Render Response

```json
{
  "sample_id": "string",
  "reference_upload_id": "string",
  "line_draft_id": "string",
  "file_url": "/uploads/fenran_training/{sample_id}.png",
  "metadata": {
    "line_draft_modified": false,
    "model": "gpt-image-2",
    "renderer_version": "fenran-renderer-v2"
  }
}
```

## Line Draft Upload

A user-uploaded white draft is stored with the same line-draft table and a `provider` value of `user_upload`. It keeps the reference linkage intact so fenran and practice sessions can reuse it.

## Read-Only Baimiao Contract

Fenran reads:

- the original reference file path
- the line-draft file path
- the stored database record metadata

Fenran does not mutate line-draft records or files.
