# Fenran Architecture

## Boundary

Fenran is independent from baimiao generation. It only reads completed baimiao output through stable database records and file paths. It never imports `backend.services.line_draft` and never writes back to line-draft files.

## Current V1 Flow

original image + baimiao image
-> registration and alignment
-> color evidence bundle (palette, LAB, regions, review flags)
-> GPT-image-compatible teaching prompt
-> model-generated teaching render
-> deterministic line overlay and border clamp
-> artifacts + technique graph + render manifest

## Implemented Modules

- `backend.services.fenran`: prompt building, evidence extraction, model call, and post-processing.
- `backend.routes.fenran`: `/api/v1/line-drafts/upload` and `/api/v1/fenran/training-renders`.
- `backend.schemas`: request/response DTOs only.

## Artifact Layout

Each run writes a public preview at:

- `uploads/fenran_training/{sample_id}.png`

Each run also writes traceable artifacts under:

- `uploads/fenran_training/{sample_id}/`

Required V1 artifacts include registered images, registration JSON, color evidence JSON, prompt bundle, raw model output, final teaching preview, technique graph, and render manifest.

## Environment

Fenran uses its own variables:

- `FENRAN_API_KEY`
- `FENRAN_API_BASE`
- `FENRAN_IMAGE_MODEL`
- `FENRAN_IMAGE_SIZE`
- `FENRAN_IMAGE_TIMEOUT_SECONDS`

## Not Implemented Yet

- Per-object leaf/petal/bud instance segmentation.
- Manual mask review UI.
- Feature-based affine/homography registration.
- Real pigment-library matching from measured color cards.
- Teacher correction persistence.
