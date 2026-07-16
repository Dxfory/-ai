"""Business orchestration for the independent mineral-pigment stage."""

from datetime import datetime
from pathlib import Path
from typing import Callable

from .analyzer import analyze_readiness, infer_reference_pigments
from .planner import build_plan
from .prompt_builder import build_prompt
from .renderer import render_shise_zhaoran
from .schemas import QualityResult, ShiseZhaoranRequest, ShiseZhaoranResult
from .utils import upload_url, validate_output, write_json


class ShiseZhaoranService:
    def __init__(self, output_root: str, upload_root: str | None = None):
        self.output_root = Path(output_root)
        self.upload_root = upload_root or output_root

    def generate(
        self,
        request: ShiseZhaoranRequest,
        *,
        render_image: Callable[..., dict | str | None] | None = None,
    ) -> ShiseZhaoranResult:
        sample_id = request.sample_id.strip() or _sample_id()
        fixing_applied = bool(request.apply_fixing or request.force_fixing)
        readiness = analyze_readiness(request.upstream_image, request.medium, fixing_applied)
        reference_evidence = infer_reference_pigments(request.reference_image)
        plan = build_plan(
            subject_hints=request.subject_hints,
            user_rules=request.user_rules,
            textbook_notes=request.textbook_notes,
            reference_evidence=reference_evidence,
        )

        if not readiness.ready:
            return ShiseZhaoranResult(
                sample_id=sample_id,
                status="not_ready",
                plan_summary=plan,
                readiness=readiness,
                validation_result=QualityResult(passed=False, warnings=readiness.reasons),
                metadata={"renderer_called": False, "module": "shise_zhaoran-v1"},
            )

        prompt = build_prompt(
            medium=request.medium,
            plan=plan,
            textbook_notes=request.textbook_notes,
            teaching_goal=request.teaching_goal,
        )
        artifact_dir = self.output_root / sample_id
        artifact_dir.mkdir(parents=True, exist_ok=True)
        output_path = artifact_dir / "final_shise_zhaoran.png"
        write_json(artifact_dir / "plan.json", {"plan": [item.model_dump() for item in plan]})
        write_json(artifact_dir / "readiness.json", readiness.model_dump())
        write_json(artifact_dir / "prompt.json", {"prompt": prompt})

        render_metadata = render_shise_zhaoran(
            upstream_image=request.upstream_image,
            reference_image=request.reference_image,
            prompt=prompt,
            output_path=str(output_path),
            render_image=render_image,
        )
        validation = validate_output(request.upstream_image, str(output_path))
        write_json(artifact_dir / "validation.json", validation.model_dump())
        metadata = {
            "module": "shise_zhaoran-v1",
            "upstream_stage": "fenran_plus_water_color_glaze",
            "renderer_called": True,
            "renderer": render_metadata,
            "artifacts": {
                "plan": str(artifact_dir / "plan.json"),
                "readiness": str(artifact_dir / "readiness.json"),
                "prompt": str(artifact_dir / "prompt.json"),
                "validation": str(artifact_dir / "validation.json"),
            },
        }
        return ShiseZhaoranResult(
            sample_id=sample_id,
            status="completed",
            final_image=str(output_path),
            final_image_url=upload_url(str(output_path), self.upload_root),
            plan_summary=plan,
            readiness=readiness,
            validation_result=validation,
            metadata=metadata,
        )


def _sample_id() -> str:
    return datetime.now().strftime("shise-%Y%m%d%H%M%S%f")
