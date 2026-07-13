# Fenran Evaluation

## Automated Tests

- tests/test_fenran_training.py verifies line draft immutability, source-color preservation, artifact creation, background whiteness, and deterministic output hash.
- tests/test_backend.py continues to cover existing baimiao/practice flows.

## Pixel-Level Checks

Current V1 checks:

- Line draft source file hash unchanged.
- Rendered background remains white.
- Flower and leaf color directions remain distinguishable.
- Same input and config produce identical final render hash.

## Gaps

- No manual golden image set yet.
- No per-object mask IoU metric yet.
- No registration boundary-error metric from real contours yet.
