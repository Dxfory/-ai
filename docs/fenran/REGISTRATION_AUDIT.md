# Fenran Registration Coordinate Audit

Date: 2026-07-14
Worktree: `C:\tmp\dxfory-fenran-training`
Scope: audit only. No fenran rendering, color, tone-map, technique graph, template, pigment, or model-call behavior was changed for this document.

## Current Sample Evidence

Latest real user-like sample in `uploads`:

- Original: `uploads/references/aa61e6fb1a4841df9f8b9e819332a0f0.jpg`, true size `1204 x 1394`.
- Final baimiao: `uploads/line_drafts/885bdd14fdca445eb81c1c45819efd35.png`, true size `1204 x 1394`.
- AI baimiao raw output: `uploads/line_drafts/885bdd14fdca445eb81c1c45819efd35_raw.png`, true size `1024 x 1536`.
- AI baimiao API input: `uploads/line_drafts/885bdd14fdca445eb81c1c45819efd35_api_input.jpg`, true size `1024 x 1536`.
- AI baimiao structure guide: `uploads/line_drafts/885bdd14fdca445eb81c1c45819efd35_structure_guide.png`, true size `1024 x 1536`.
- Current fenran registered original: `uploads/fenran_training/0bc5f5819143491e9a7603ec28ab1954/registered_original.png`, true size `1204 x 1394`.
- Current fenran registered baimiao: `uploads/fenran_training/0bc5f5819143491e9a7603ec28ab1954/registered_baimiao.png`, true size `1204 x 1394`.
- Current fenran API downscaled original/baimiao: `884 x 1024` each.

Database metadata for this sample:

- `reference_uploads.metadata` contains only `{"content_type":"image/jpeg"}`. The original natural width/height are not persisted at upload time.
- `line_drafts.metadata` contains `source_size: [1204, 1394]`, `api_canvas_size: [1024, 1536]`, `content_box: [0, 175, 1024, 1361]`, provider/model/prompt metadata, and final `width/height`.

## Audit Checklist

### 1. Original upload true pixel size

The current upload endpoint saves the original bytes directly to `uploads/references` and stores only content type metadata in `backend/routes/practice.py:56-68`. It does not open the image to persist natural width/height.

For the latest sample, true size was measured from disk with Pillow: `1204 x 1394`.

### 2. Baimiao true pixel size

Generated line drafts are persisted with final `width` and `height` in `backend/routes/practice.py:108-117`.

For the latest sample, final baimiao size is `1204 x 1394`, matching the original outer image size. The raw model output was `1024 x 1536`, so matching final dimensions do not prove internal object alignment.

### 3. Resize, crop, padding, and letterbox points

Observed coordinate-space transitions:

- Local preview provider: `backend/services/line_draft.py:54-55` opens the image and calls `thumbnail((1800, 1800))`; this can downscale large originals before line extraction.
- AI baimiao canvas selection: `backend/services/line_draft.py:262-285` resolves an API canvas and computes `content_box` by contain-fitting the source into the model canvas.
- AI baimiao API input: `backend/services/line_draft.py:315-321` places the source on the generation canvas when aspect preservation is enabled, otherwise thumbnails to max side.
- Canvas placement: `backend/services/line_draft.py:404-409` resizes the source into `content_box` and pastes onto a white canvas.
- AI baimiao aspect restore: `backend/services/line_draft.py:478-495` crops the generated model output back through scaled `content_box` and resizes to `canvas.source_size`.
- Practice overlay: `backend/services/line_draft.py:209-228` uses `ImageOps.contain(submission, reference.size)` and centered offsets before compositing. This is a static image overlay, not a canonical-coordinate overlay.
- Fenran original alignment: `backend/services/fenran.py:276-283` contain-fits the original to the baimiao canvas only if sizes differ.
- Fenran model output fit: `backend/services/fenran.py:286-293` contain-fits generated output to the baimiao canvas.
- Fenran API inputs: `backend/services/fenran.py:296-313` downscale registered original and baimiao together to the same API size.

Latest sample specific transform:

- Source `1204 x 1394` was placed into API canvas `1024 x 1536` with `content_box [0, 175, 1024, 1361]`.
- Raw model output `1024 x 1536` was cropped by that content region and resized back to `1204 x 1394`.
- This preserves outer dimensions but cannot guarantee flower/leaf/stem topology stayed in the same canonical pixels.

### 4. Frontend original object-fit

Original preview uses `<img id="referencePreview">` in `frontend/index.html:67` and the common `figure img` CSS in `frontend/styles.css:176-181`.

Current display style:

- `display: block`
- `width: 100%`
- `max-height: 740px`
- `object-fit: contain`
- `padding: 12px`

### 5. Frontend baimiao object-fit

Baimiao preview uses `<img id="draftPreview">` in `frontend/index.html:71` and the same common `figure img` CSS in `frontend/styles.css:176-181`.

It uses `object-fit: contain`, but it lives in a separate figure/card from the original. There is no shared rendered rectangle or canonical coordinate mapping between the two previews.

### 6. Canvas, SVG, and annotation coordinate size

No registration canvas/SVG layer currently exists in the frontend.

Evidence:

- `frontend/app.js` only sets image `src` through `setImage` at `frontend/app.js:15-18`.
- No `getBoundingClientRect`, `naturalWidth`, `naturalHeight`, canvas, SVG, or renderedRect logic exists in the current app.
- The current `overlayPreview` is only another `<img>` displaying a backend-generated static overlay, not a live coordinate layer.

### 7. CSS transform, scale, padding, border, and clipping

Relevant frontend CSS:

- Global `box-sizing: border-box`: `frontend/styles.css:13-15`.
- Preview figures have borders and min height: `frontend/styles.css:162-165`.
- Figure captions add a border and padding: `frontend/styles.css:168-172`.
- Images have `width: 100%`, `max-height: 740px`, `object-fit: contain`, and `padding: 12px`: `frontend/styles.css:176-181`.

No CSS `transform` or `scale()` was found in the frontend. The padding and independent cards are still enough to make screen-space overlays inconsistent unless a single renderedRect is computed and shared.

### 8. Whether original, baimiao, and red audit lines use the same display rectangle

They currently do not have a shared display rectangle.

- Original, baimiao, and fenran are separate images in separate figures.
- The backend practice overlay is a new raster file generated at reference pixel size, then displayed as its own image.
- There is no current red audit line / SVG layer for registration editing.
- Because no `renderedRect` is stored, future audit points cannot be guaranteed to land on the same image pixels across original, baimiao, and overlay layers.

### 9. Whether the API saves original-to-baimiao transform

Partially, but not enough for registration.

Saved today:

- AI baimiao metadata saves `source_size`, `api_canvas_size`, and `content_box`.
- Fenran registration JSON saves a nominal `global_transform.type = contain_resize_to_line_draft_canvas` in `backend/services/fenran.py:362-384`.

Missing today:

- No canonical original image-space contract is persisted on the reference upload.
- No measured affine/homography matrix is saved.
- No local control points are saved.
- No displacement field is saved.
- No approved/rejected registration version exists.
- No boundary-error metrics are measured from real flower/leaf/stem landmarks.

Current latest `registration.json` reports `registration_score: 1.0`, `mean_boundary_error_px: 0.0`, and `requires_review: false` only because image sizes match. It does not detect local object drift.

### 10. Whether overlay preview uses screenshot dimensions instead of original dimensions

The backend static overlays use image pixel dimensions, not browser screenshots.

However, the frontend displays all previews through browser-rendered `<img>` dimensions. Since it does not compute or persist `naturalWidth/naturalHeight -> renderedRect`, any manual point or SVG overlay added on top of the current UI would risk using DOM/screenshot coordinates instead of canonical image coordinates.

## Root Cause Summary

### A. Display-coordinate root cause

The app has no single canonical image-space display adapter. Original and baimiao are displayed in separate DOM boxes with independent layout. The CSS is consistent in rule name but not in actual rendered rectangle because each image is constrained by its own card width, max height, padding, caption, and natural aspect ratio.

Required correction: compute one `renderedRect` per image display, map screen clicks through that rect back to original natural pixel coordinates, and make original, baimiao, and SVG audit layers share the same rect.

### B. Backend registration root cause

Current fenran registration is a size/aspect check, not geometric registration. If original and baimiao dimensions match, it reports perfect registration. This misses exactly the current failure mode: the model-generated baimiao has the same final canvas size but locally redrew petals, leaves, and stems.

Required correction: make the original image the only canonical coordinate system, estimate global transform from subject structure, then allow constrained local non-rigid correction of the baimiao only.

### C. Baimiao structural drift root cause

The AI baimiao path sends a letterboxed `1024 x 1536` image to the model and restores output to `1204 x 1394`. Even with aspect restoration, the model can locally move or reshape flower centers, petal tips, leaf tips, leaf roots, and stem joints. This is a topology/structure problem, not just a resize problem.

Required correction: detect when local mismatch is registration-solvable versus topology mismatch. Do not force a global warp or dense unconstrained optical flow over missing/extra/merged/split objects.

## Implementation Boundary For Next Phase

Allowed next changes:

- Add canonical image-space utilities and tests.
- Add registration artifacts that transform only baimiao into original coordinates.
- Add frontend registration editor using shared `renderedRect`.
- Gate fenran on an approved `registered_baimiao` once registration exists.

Still frozen:

- Fenran LLM prompt behavior.
- Fenran color evidence, tone maps, Technique Graph semantics, rendering parameters, technique templates, pigment config.
- Existing baimiao generation logic unless a separate explicit request changes that boundary.
- Original image pixels.

## Immediate Risks To Test

- Same pixel dimensions can still hide local object drift.
- `object-fit: contain` is acceptable only if original/baimiao/SVG use the exact same renderedRect and canonical coordinate inverse mapping.
- Padding and letterbox must be included in screen-to-image coordinate conversion.
- Existing static overlay code is useful for review snapshots but should not be treated as a registration editor coordinate system.
