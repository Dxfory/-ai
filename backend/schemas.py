"""Pydantic 请求/响应 Schema"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class MaterialItemSchema(BaseModel):
    category: str
    name: str
    description: str
    step: Optional[int] = None


class AssetCreateRequest(BaseModel):
    title: str
    source_name: str
    source_url: str
    license_type: str
    license_url: str = ""
    attribution_text: str = ""
    display_allowed: bool = False
    train_allowed: bool = False
    commercial_allowed: bool = False
    derivative_allowed: bool = False
    risk_level: str = "unknown"
    file_hash: str = ""
    image_url: str = ""
    metadata: dict = {}


class AssetSchema(AssetCreateRequest):
    id: str
    created_at: datetime = Field(default_factory=datetime.now)


class ReferenceUploadSchema(BaseModel):
    id: str
    original_filename: str
    file_url: str
    consent_scope: str = "personal_analysis"
    notes: str = ""
    metadata: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)


class LineDraftGenerateRequest(BaseModel):
    reference_upload_id: str
    line_strength: int = Field(default=3, ge=1, le=5)
    detail_level: int = Field(default=3, ge=1, le=5)
    preserve_texture: bool = True
    provider: str = "local_edge_preview"
    prompt: str = ""


class LineDraftSchema(BaseModel):
    id: str
    reference_upload_id: str
    file_url: str
    line_strength: int = 3
    detail_level: int = 3
    preserve_texture: bool = True
    provider: str = "local_edge_preview"
    status: str = "ready"
    metadata: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)


class ColorStepGenerateRequest(BaseModel):
    reference_upload_id: str
    line_draft_id: str
    step_type: str = "fenran"
    provider: str = "ai_fenran"
    prompt: str = ""


class GeneratedStepImageSchema(BaseModel):
    id: str
    reference_upload_id: str
    line_draft_id: str
    step_type: str
    file_url: str
    provider: str
    status: str = "ready"
    metadata: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)


class PracticeSessionCreateRequest(BaseModel):
    reference_upload_id: str
    line_draft_id: str
    title: str = "工笔花鸟白描临摹"


class PracticeStepRunSchema(BaseModel):
    id: str
    session_id: str
    step_num: int
    title: str
    instruction: str
    checklist: List[str] = Field(default_factory=list)
    common_mistakes: List[str] = Field(default_factory=list)
    status: str = "pending"
    submission_image_url: str = ""
    overlay_image_url: str = ""
    notes: str = ""


class PracticeSessionSchema(BaseModel):
    id: str
    reference_upload_id: str
    line_draft_id: str
    title: str
    status: str = "active"
    current_step_num: int = 1
    steps: List[PracticeStepRunSchema] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)


class StepSchema(BaseModel):
    id: str
    course_id: str
    step_num: int
    title: str
    instruction: str
    demo_image_url: str = ""
    checklist: List[str] = []
    materials: List[MaterialItemSchema] = []
    common_mistakes: List[str] = []


class CourseSchema(BaseModel):
    id: str
    artwork_id: str
    genre: str
    method: str
    template_version: str = "1.0"
    steps: List[StepSchema] = []
    created_at: datetime = Field(default_factory=datetime.now)


class ArtworkSchema(BaseModel):
    id: str
    title: str
    genre: str
    method: str
    image_url: str
    input_method: str = "photo"
    created_at: datetime = Field(default_factory=datetime.now)


class ArtworkCreateRequest(BaseModel):
    title: str
    genre: str
    method: str
    image_url: str
    input_method: str = "photo"


class SubmissionCreateRequest(BaseModel):
    user_id: str
    step_id: str
    image_url: str


class StepFeedbackSchema(BaseModel):
    step_id: str
    passed: bool
    overall_comment: str
    annotations: List[dict] = []
    structure_score: float = 0.0
    stroke_score: float = 0.0
    ink_score: float = 0.0
    color_score: float = 0.0
    style_score: float = 0.0


class SubmissionSchema(BaseModel):
    id: str
    user_id: str
    step_id: str
    image_url: str
    status: str = "pending"
    feedback: Optional[StepFeedbackSchema] = None
    submitted_at: datetime = Field(default_factory=datetime.now)


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.1.0"
    server: str = "国画临摹AI教练"
