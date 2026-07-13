# Fenran Audit Report

## Git Snapshot

- Repository: https://github.com/Dxfory/-ai
- Worktree: C:/tmp/dxfory-fenran-training
- Branch: codex/fenran-training-source-locked-threshold-fix
- Base commit: 63c0be1 Fix source locked ink threshold
- Push performed: no
- Cached/staged diff at audit time: none

Initial audit commands run:

- git status --short
- git branch --show-current
- git log --oneline --decorate -20
- git reflog --date=local -20
- git diff --stat
- git diff --cached --stat
- git remote -v

## Current Repository Shape

- Backend: FastAPI in backend/app.py with routers under backend/routes.
- Existing practice flow: backend/routes/practice.py handles reference upload, line draft generation, practice sessions, submissions, and overlay checks.
- Existing baimiao/line draft implementation: backend/services/line_draft.py.
- Existing baimiao knowledge/prompt file: backend/services/baimiao_knowledge.py.
- Schemas: backend/schemas.py.
- Tests: pytest, mainly tests/test_backend.py and tests/test_shared.py.
- Image dependency currently used: Pillow.

## Baimiao Call Chain

1. POST /api/v1/uploads/reference stores the original image under uploads/references.
2. POST /api/v1/line-drafts/generate reads the reference upload and calls one of the existing line draft providers.
3. The stable source-locked provider is generate_source_locked_baimiao in backend/services/line_draft.py.
4. LineDraftModel stores file_path, file_url, provider, and metadata.
5. Fenran V1 reads only ReferenceUploadModel.file_path and LineDraftModel.file_path through the API/data contract. It does not import backend.services.line_draft.

## Original And Baimiao Artifact Format

- Original image: user-uploaded image file path and /uploads/references URL.
- Baimiao image: PNG saved under /uploads/line_drafts/{draft_id}.png.
- Size: source-locked baimiao preserves source size when using that provider.
- URI contract: current backend uses local file_path plus public file_url.

## Reusable Infrastructure

- FastAPI router pattern.
- SQLAlchemy models for ReferenceUploadModel and LineDraftModel.
- settings.UPLOAD_DIR static file mount.
- Pillow image loading and deterministic image transforms.
- pytest + TestClient integration tests.

## Frozen Baimiao Boundary

These files are treated as read-only for fenran logic:

- backend/services/line_draft.py
- backend/services/baimiao_knowledge.py
- backend/routes/practice.py, except as external API behavior
- Existing baimiao provider names and env var names
- Existing baimiao output files under uploads/line_drafts

## Implemented Fenran V1 Changes

- Added backend/services/fenran.py as an independent deterministic renderer.
- Added backend/routes/fenran.py as an independent API route.
- Added fenran request/response schemas to backend/schemas.py.
- Registered the new router in backend/app.py.
- Added tests/test_fenran_training.py for read-only line draft behavior, color preservation, artifacts, and determinism.
- Repaired encoding-fragile legacy assertions in tests/test_backend.py without modifying baimiao runtime files.

## Risks

- Registration is currently basic contain-to-canvas alignment, not feature-based affine or homography.
- Object masks are V1 color-region masks, not per-leaf/per-petal instance segmentation.
- Color extraction is apparent display color only. It does not infer true pigment ratios.
- Renderer is deterministic and traceable, but not yet a complete professional gongbi technique engine.

## Implementation Order Used

1. Isolated worktree from source-locked baimiao version.
2. Baseline pytest run.
3. Add failing fenran tests.
4. Implement independent fenran service and API route.
5. Add traceable render artifacts and manifest.
6. Run full pytest suite.
