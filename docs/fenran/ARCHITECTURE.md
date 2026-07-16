# Fenran Architecture

Fenran is an independent teaching-render pipeline. It reads an approved `registered_baimiao` and the original reference; it never imports or writes the baimiao generation service or its source file.

## Runtime Flow

```text
approved registered_baimiao
  -> canonical canvas
  -> optional base color
  -> first fenran
  -> deepen fenran
  -> sap green glaze
  -> mask composition and validation
  -> file cache
  -> stage previews
```

Every formal stage is a complete image at the source artwork's canonical size. Stage 2 receives stage 1 as its first edit image, and stage 3 receives stage 2. The model is instructed to generate one painting only; it does not design a page layout.

## Modules

- `backend/services/fenran.py`: orchestration, artifacts, cumulative stages, manifest.
- `backend/services/fenran_canvas.py`: provider canvas selection, `content_box`, canonical placement and restoration.
- `backend/services/fenran_generation.py`: OpenAI-compatible multi-image edit transport and explicit provider errors.
- `backend/services/fenran_plan.py`: versioned optional base-color plan and three formal stages.
- `backend/services/fenran_masks.py`: deterministic subject/background masks and background protection.
- `backend/services/fenran_validation.py`: canvas, subject, background, and stage-change metrics.
- `backend/services/fenran_cache.py`: file-level cache keyed by immutable inputs and renderer configuration.
- `backend/routes/fenran.py`: registration approval gate, request validation, error mapping, and response URLs.

## Artifacts

Each run is written under `uploads/fenran_training/{sample_id}/` with canonical inputs, `generation_canvas.json`, `subject_mask.png`, `teaching_plan.json`, `prompt_bundle.json`, per-stage attempts and `selected.png`, `technique_graph.json`, and `render_manifest.json`. A successful response points to the final selected stage while `stages` exposes every complete stage.

## Frozen Boundaries

The baimiao generation algorithm, prompts, post-processing, registration approval gate, registration editor coordinate logic, original pixels, and the current color direction are outside Fenran's ownership.
