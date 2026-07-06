"""shared 包单元测试"""

import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.types import (
    ArtworkMethod, ArtGenre, SubmissionStatus,
    ArtworkInputMethod, MaterialItem, Artwork,
    Course, Step, StepFeedback, Submission, ErrorProfile,
)
from shared.utils import validate_image_format, generate_uuid


class TestEnums:
    """枚举类型测试"""
    def test_artwork_method_values(self):
        assert ArtworkMethod.GONGBI.value == "gongbi"
        assert ArtworkMethod.XIEYI.value == "xieyi"

    def test_art_genre_values(self):
        assert ArtGenre.FLOWER_BIRD.value == "flower_bird"
        assert ArtGenre.LANDSCAPE.value == "landscape"
        assert ArtGenre.FIGURE.value == "figure"

    def test_submission_status(self):
        assert SubmissionStatus.PENDING.value == "pending"
        assert SubmissionStatus.GRADED.value == "graded"
        assert SubmissionStatus.COMPLETED.value == "completed"
        assert SubmissionStatus.REVISION.value == "revision"

    def test_input_methods(self):
        assert ArtworkInputMethod.PHOTO.value == "photo"
        assert ArtworkInputMethod.SCAN.value == "scan"
        assert ArtworkInputMethod.PARTIAL.value == "partial"
        assert ArtworkInputMethod.SEARCH.value == "search"


class TestDataclasses:
    """数据类测试"""
    def test_material_item(self):
        item = MaterialItem(
            category="brush", name="兼毫勾线笔",
            description="用于工笔勾线", step=1
        )
        assert item.category == "brush"
        assert item.name == "兼毫勾线笔"
        assert item.step == 1

    def test_artwork_gongbi(self):
        artwork = Artwork(
            id="a001", title="出水芙蓉图",
            genre=ArtGenre.FLOWER_BIRD, method=ArtworkMethod.GONGBI,
            image_url="/images/a001.jpg",
            input_method=ArtworkInputMethod.PHOTO
        )
        assert artwork.genre == ArtGenre.FLOWER_BIRD
        assert artwork.method == ArtworkMethod.GONGBI
        assert artwork.input_method == ArtworkInputMethod.PHOTO

    def test_artwork_xieyi(self):
        artwork = Artwork(
            id="a002", title="墨葡萄图",
            genre=ArtGenre.FLOWER_BIRD, method=ArtworkMethod.XIEYI,
            image_url="/images/a002.jpg",
            input_method=ArtworkInputMethod.SEARCH
        )
        assert artwork.method == ArtworkMethod.XIEYI
        assert artwork.input_method == ArtworkInputMethod.SEARCH

    def test_step_with_materials(self):
        materials = [
            MaterialItem("brush", "兼毫勾线笔", "中锋勾线", 1),
        ]
        step = Step(
            id="s001", course_id="c001", step_num=1,
            title="勾线", instruction="中锋行笔勾勒轮廓",
            materials=materials, checklist=["线条均匀", "起收笔含蓄"],
            common_mistakes=["线条粗细不匀", "断线"]
        )
        assert step.step_num == 1
        assert len(step.materials) == 1
        assert len(step.checklist) == 2

    def test_course(self):
        step = Step(id="s001", course_id="c001", step_num=1,
                    title="勾线", instruction="中锋行笔")
        course = Course(
            id="c001", artwork_id="a001",
            genre=ArtGenre.FLOWER_BIRD, method=ArtworkMethod.GONGBI,
            steps=[step], template_version="1.0"
        )
        assert len(course.steps) == 1
        assert course.genre == ArtGenre.FLOWER_BIRD

    def test_submission(self):
        sub = Submission(
            id="sub001", user_id="u001", step_id="s001",
            image_url="/submissions/sub001.jpg"
        )
        assert sub.status == SubmissionStatus.PENDING
        assert sub.feedback is None

    def test_submission_with_feedback(self):
        fb = StepFeedback(
            step_id="s001", passed=True,
            overall_comment="线条匀净，勾线到位",
            structure_score=0.85, stroke_score=0.90,
            ink_score=0.80, color_score=0.75, style_score=0.82
        )
        sub = Submission(
            id="sub001", user_id="u001", step_id="s001",
            image_url="/submissions/sub001.jpg",
            status=SubmissionStatus.GRADED, feedback=fb
        )
        assert sub.feedback.passed is True
        assert sub.feedback.structure_score == 0.85
        assert sub.feedback.stroke_score == 0.90

    def test_error_profile(self):
        ep = ErrorProfile(
            user_id="u001", error_type="structure",
            frequency=3, trend="improving"
        )
        assert ep.user_id == "u001"
        assert ep.error_type == "structure"
        assert ep.frequency == 3


class TestUtils:
    """工具函数测试"""
    def test_validate_image_format_valid(self):
        assert validate_image_format("test.jpg")
        assert validate_image_format("test.png")
        assert validate_image_format("test.tiff")
        assert validate_image_format("test.webp")

    def test_validate_image_format_invalid(self):
        assert not validate_image_format("test.bmp")
        assert not validate_image_format("test.gif")
        assert not validate_image_format("test.pdf")
        assert not validate_image_format("noext")

    def test_generate_uuid(self):
        uid = generate_uuid()
        assert len(uid) == 32
        assert isinstance(uid, str)
        uid2 = generate_uuid()
        assert uid != uid2
