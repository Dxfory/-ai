"""共享类型定义和工具函数包"""

from .types import (
    ArtworkMethod,
    ArtGenre,
    Artwork,
    Course,
    Step,
    Submission,
    ErrorProfile,
    MaterialItem,
    SubmissionStatus,
    StepFeedback,
)
from .utils import validate_image_format, generate_uuid

__all__ = [
    "ArtworkMethod", "ArtGenre", "Artwork", "Course", "Step",
    "Submission", "ErrorProfile", "MaterialItem",
    "SubmissionStatus", "StepFeedback",
    "validate_image_format", "generate_uuid",
]
