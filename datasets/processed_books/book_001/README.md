# book_001 ingest summary

- pages: 33
- total_bytes: 65039971
- generated_at: 2026-07-10T06:31:36.434671+00:00

## Next annotation passes

1. OCR each page and fill `ocr_text` / `text_blocks`.
2. Crop or mark every figure region with `bbox`.
3. Bind captions such as `图9` to the nearest explanatory paragraph.
4. Extract technique units: materials, colors, actions, warnings, step order.
5. Convert validated units into training/evaluation examples.
