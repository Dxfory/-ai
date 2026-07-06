"""核心数据类型定义 - 国画临摹 AI 教练 (Phase 0)"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class ArtworkMethod(str, Enum):
    """画法类型"""
    GONGBI = "gongbi"
    XIEYI = "xieyi"


class ArtGenre(str, Enum):
    """画种"""
    FLOWER_BIRD = "flower_bird"
    LANDSCAPE = "landscape"
    FIGURE = "figure"


class SubmissionStatus(str, Enum):
    """作业提交状态"""
    PENDING = "pending"
    GRADED = "graded"
    COMPLETED = "completed"
    REVISION = "revision"


class ArtworkInputMethod(str, Enum):
    """范本输入方式"""
    PHOTO = "photo"
    SCAN = "scan"
    PARTIAL = "partial"
    SEARCH = "search"


@dataclass
class MaterialItem:
    """画材项目"""
    category: str
    name: str
    description: str
    step: Optional[int] = None


@dataclass
class Artwork:
    """范本作品"""
    id: str
    title: str
    genre: ArtGenre
    method: ArtworkMethod
    image_url: str
    input_method: ArtworkInputMethod
    metadata: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class Course:
    """课程模板"""
    id: str
    artwork_id: str
    genre: ArtGenre
    method: ArtworkMethod
    steps: list = field(default_factory=list)
    template_version: str = "1.0"
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class Step:
    """单步内容"""
    id: str
    course_id: str
    step_num: int
    title: str
    instruction: str
    demo_image_url: str = ""
    checklist: list[str] = field(default_factory=list)
    materials: list[MaterialItem] = field(default_factory=list)
    common_mistakes: list[str] = field(default_factory=list)


@dataclass
class StepFeedback:
    """单步反馈"""
    step_id: str
    passed: bool
    overall_comment: str
    annotations: list[dict] = field(default_factory=list)
    structure_score: float = 0.0
    stroke_score: float = 0.0
    ink_score: float = 0.0
    color_score: float = 0.0
    style_score: float = 0.0


@dataclass
class Submission:
    """学生作业"""
    id: str
    user_id: str
    step_id: str
    image_url: str
    status: SubmissionStatus = SubmissionStatus.PENDING
    feedback: Optional[StepFeedback] = None
    submitted_at: datetime = field(default_factory=datetime.now)


@dataclass
class ErrorProfile:
    """用户错误画像（修改版：个人级，非班级级）"""
    user_id: str
    error_type: str
    frequency: int = 0
    trend: str = "stable"
    last_updated: datetime = field(default_factory=datetime.now)
