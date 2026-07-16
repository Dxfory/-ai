# Fenran Registration Fix Report

Date: 2026-07-14

## 1. Misalignment Root Cause

The latest sample has matching final outer dimensions (`1204 x 1394`) for original and baimiao, but the baimiao was generated through a `1024 x 1536` API canvas and restored through `content_box [0, 175, 1024, 1361]`. This preserves the frame while still allowing local model redraw drift in flowers, leaves, and stems.

## 2. Frontend Coordinate Issue

The old UI showed original and baimiao in separate `<img>` cards. Each card used its own rendered box, so there was no shared canonical image-space mapping. The new registration viewer displays original, registered baimiao, and SVG points in one overlay container, with shared screen-to-canonical coordinate conversion exposed as `window.registrationGeometry`.

## 3. Baimiao Structure Drift Issue

This change does not alter baimiao generation. Local structure drift is now treated as a registration-review concern before fenran starts. The current automated candidate uses conservative canvas fitting only and defaults to `review_required`; manual approval is required before fenran can consume it.

## 4. Modified Files

- `backend/routes/fenran.py`
- `frontend/index.html`
- `frontend/styles.css`
- `frontend/app.js`
- `tests/test_fenran_training.py`
- `tests/test_fenran_registration_gate.py`
- `tests/test_registration_api.py`
- `docs/fenran/REGISTRATION_AUDIT.md`
- `docs/fenran/REGISTRATION_FIX_REPORT.md`

## 5. Fenran Files Not Modified

The main fenran rendering service was not modified:

- `backend/services/fenran.py`

No changes were made to fenran prompt construction, color evidence extraction, palette logic, tone-map behavior, technique graph semantics, model-call logic, final preview post-processing, pigments, or templates.

## 6. Global Registration Artifacts

The registration API writes:

- `global_registered_baimiao.png`
- `global_overlay.png`
- `registration_result.json`

These are stored under `uploads/registrations/{line_draft_id}/{registration_id}/`.

## 7. Local Registration Artifacts

The registration API currently writes:

- `local_registered_baimiao.png`
- `local_overlay.png`
- `control_points.json`

For this pass, local registration is a reviewed candidate copy of the global result. It is intentionally not a dense optical-flow warp and does not force topology changes.

## 8. Quality Metrics

Current metadata includes:

- `registration_score`
- `mean_boundary_error_px`
- `p95_boundary_error_px`
- `max_boundary_error_px`
- `landmark_error`
- `topology_mismatch_count`
- `requires_review`

Boundary/landmark metrics are scaffolded but not yet computed from real petal/leaf/stem landmarks. The status defaults to `review_required` until a teacher/user approves the registration version.

## 9. Topology Error Regions

Topology mismatch detection is scaffolded through `topology_issues` and `topology_mismatch_count`. Automatic object-level detection of missing petals, merged leaves, split leaves, and changed branch connectivity is not implemented in this pass.

## 10. Manual Review Entry

The frontend now has a `配准编辑` action. It opens an overlay viewer with:

- original image;
- registered baimiao overlay;
- opacity slider;
- point display in canonical image coordinates;
- auto registration refresh;
- save/approve registration version.

## 11. Test Results

Fresh verification:

- `python -m pytest -q`
- Result: `62 passed, 4 warnings`
- `node --check frontend/app.js`
- Result: exit code `0`

## 12. Remaining Automatic Limits

The current fix prevents unreviewed or geometrically untracked baimiao from entering fenran, and it fixes the frontend coordinate basis for review. It does not yet automatically solve severe local redraw drift where the model changed object topology. Those regions still require manual review/approval and, later, constrained landmark-based local registration.
