"""Data contracts for the independent Shise Zhaoran module."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


Medium = Literal["silk", "paper"]


class ShiseUpstreamUploadResult(BaseModel):
    file_url: str
    original_filename: str
    width: int
    height: int


class ShiseZhaoranRequest(BaseModel):
    upstream_image: str
    medium: Medium
    reference_image: str | None = None
    subject_hints: list[str] = Field(default_factory=list)
    textbook_notes: str = ""
    user_rules: list[str] = Field(default_factory=list)
    apply_fixing: bool | None = None
    force_fixing: bool | None = None
    sample_id: str = ""
    teaching_goal: str = ""


class ReadinessResult(BaseModel):
    status: Literal["ready", "not_ready"]
    ready: bool
    medium: Medium
    fixing_required: bool
    fixing_applied: bool
    checks: dict[str, bool] = Field(default_factory=dict)
    reasons: list[str] = Field(default_factory=list)


class ObjectColorPlan(BaseModel):
    object_type: str
    object_label: str
    pigment: str
    pigment_key: str
    action: str
    reason: str
    source: Literal["user", "textbook", "reference", "default"]
    preserve: list[str] = Field(default_factory=list)


class QualityResult(BaseModel):
    passed: bool
    checks: dict[str, bool | float] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class ShiseZhaoranResult(BaseModel):
    sample_id: str
    status: Literal["ready", "not_ready", "completed", "failed"]
    final_image: str | None = None
    final_image_url: str | None = None
    plan_summary: list[ObjectColorPlan] = Field(default_factory=list)
    readiness: ReadinessResult
    validation_result: QualityResult | None = None
    metadata: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)
