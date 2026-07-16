# Fenran Data Contracts

## Request

```json
{
  "reference_upload_id": "string",
  "line_draft_id": "string",
  "sample_id": "string",
  "teaching_goal": "string",
  "include_base_color": false,
  "force_regenerate": false,
  "max_attempts": 3
}
```

`line_draft_id` must have an approved registration record containing `registered_baimiao_path`. The original and registered baimiao must have the same canonical pixel size.

## Response

```json
{
  "sample_id": "string",
  "reference_upload_id": "string",
  "line_draft_id": "string",
  "canonical_width": 1204,
  "canonical_height": 1394,
  "stages": [
    {
      "stage_id": "stage_01_first_fenran",
      "title": "第一遍分染",
      "technique": "分染",
      "pigments": ["花青", "淡墨"],
      "file_url": "/uploads/fenran_training/sample/stage_01_first_fenran/selected.png",
      "status": "ready",
      "validation": {}
    }
  ],
  "file_url": "/uploads/fenran_training/sample/stage_03_sap_green_glaze/selected.png",
  "status": "ready",
  "cache_hit": false,
  "metadata": {}
}
```

The source line draft and approved registered baimiao are read-only artifacts. Fenran copies them into its own artifact directory and does not write back to the source files.
