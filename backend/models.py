"""SQLAlchemy ORM 妯″瀷 (淇敼鐗? 鏃?teacher/classroom 琛?"""

from datetime import datetime
from sqlalchemy import Boolean, Column, String, Integer, DateTime, JSON, ForeignKey
from sqlalchemy.orm import relationship

from .database import Base


class AssetModel(Base):
    __tablename__ = "assets"
    id = Column(String, primary_key=True)
    title = Column(String, nullable=False)
    source_name = Column(String, nullable=False)
    source_url = Column(String, nullable=False)
    license_type = Column(String, nullable=False)
    license_url = Column(String, default="")
    attribution_text = Column(String, default="")
    display_allowed = Column(Boolean, default=False)
    train_allowed = Column(Boolean, default=False)
    commercial_allowed = Column(Boolean, default=False)
    derivative_allowed = Column(Boolean, default=False)
    risk_level = Column(String, default="unknown")
    file_hash = Column(String, default="")
    image_url = Column(String, default="")
    metadata_ = Column("metadata", JSON, default=dict)
    created_at = Column(DateTime, default=datetime.now)


class ArtworkModel(Base):
    __tablename__ = "artworks"
    id = Column(String, primary_key=True)
    title = Column(String, nullable=False)
    genre = Column(String, nullable=False)
    method = Column(String, nullable=False)
    image_url = Column(String)
    input_method = Column(String, default="photo")
    metadata_ = Column("metadata", JSON, default=dict)
    created_at = Column(DateTime, default=datetime.now)
    courses = relationship("CourseModel", back_populates="artwork")


class CourseModel(Base):
    __tablename__ = "courses"
    id = Column(String, primary_key=True)
    artwork_id = Column(String, ForeignKey("artworks.id"))
    genre = Column(String, nullable=False)
    method = Column(String, nullable=False)
    template_version = Column(String, default="1.0")
    created_at = Column(DateTime, default=datetime.now)
    artwork = relationship("ArtworkModel", back_populates="courses")
    steps = relationship("StepModel", back_populates="course", order_by="StepModel.step_num")


class StepModel(Base):
    __tablename__ = "steps"
    id = Column(String, primary_key=True)
    course_id = Column(String, ForeignKey("courses.id"))
    step_num = Column(Integer, nullable=False)
    title = Column(String, nullable=False)
    instruction = Column(String, nullable=False)
    demo_image_url = Column(String, default="")
    checklist = Column(JSON, default=list)
    materials = Column(JSON, default=list)
    common_mistakes = Column(JSON, default=list)
    course = relationship("CourseModel", back_populates="steps")
    submissions = relationship("SubmissionModel", back_populates="step")


class SubmissionModel(Base):
    __tablename__ = "submissions"
    id = Column(String, primary_key=True)
    user_id = Column(String, nullable=False)
    step_id = Column(String, ForeignKey("steps.id"))
    image_url = Column(String, nullable=False)
    status = Column(String, default="pending")
    feedback = Column("feedback", JSON, nullable=True)
    submitted_at = Column(DateTime, default=datetime.now)
    step = relationship("StepModel", back_populates="submissions")


class ErrorProfileModel(Base):
    __tablename__ = "error_profiles"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, nullable=False)
    error_type = Column(String, nullable=False)
    frequency = Column(Integer, default=0)
    trend = Column(String, default="stable")
    last_updated = Column(DateTime, default=datetime.now)


class ReferenceUploadModel(Base):
    __tablename__ = "reference_uploads"
    id = Column(String, primary_key=True)
    original_filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_url = Column(String, nullable=False)
    consent_scope = Column(String, default="personal_analysis")
    notes = Column(String, default="")
    metadata_ = Column("metadata", JSON, default=dict)
    created_at = Column(DateTime, default=datetime.now)
    line_drafts = relationship("LineDraftModel", back_populates="reference")
    practice_sessions = relationship("PracticeSessionModel", back_populates="reference")


class LineDraftModel(Base):
    __tablename__ = "line_drafts"
    id = Column(String, primary_key=True)
    reference_upload_id = Column(String, ForeignKey("reference_uploads.id"), nullable=False)
    file_path = Column(String, nullable=False)
    file_url = Column(String, nullable=False)
    line_strength = Column(Integer, default=3)
    detail_level = Column(Integer, default=3)
    preserve_texture = Column(Boolean, default=True)
    provider = Column(String, default="local_edge_preview")
    status = Column(String, default="ready")
    metadata_ = Column("metadata", JSON, default=dict)
    created_at = Column(DateTime, default=datetime.now)
    reference = relationship("ReferenceUploadModel", back_populates="line_drafts")
    practice_sessions = relationship("PracticeSessionModel", back_populates="line_draft")


class PracticeSessionModel(Base):
    __tablename__ = "practice_sessions"
    id = Column(String, primary_key=True)
    reference_upload_id = Column(String, ForeignKey("reference_uploads.id"), nullable=False)
    line_draft_id = Column(String, ForeignKey("line_drafts.id"), nullable=False)
    title = Column(String, nullable=False)
    status = Column(String, default="active")
    current_step_num = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.now)
    reference = relationship("ReferenceUploadModel", back_populates="practice_sessions")
    line_draft = relationship("LineDraftModel", back_populates="practice_sessions")
    step_runs = relationship("PracticeStepRunModel", back_populates="session", order_by="PracticeStepRunModel.step_num")


class PracticeStepRunModel(Base):
    __tablename__ = "practice_step_runs"
    id = Column(String, primary_key=True)
    session_id = Column(String, ForeignKey("practice_sessions.id"), nullable=False)
    step_num = Column(Integer, nullable=False)
    title = Column(String, nullable=False)
    instruction = Column(String, nullable=False)
    checklist = Column(JSON, default=list)
    common_mistakes = Column(JSON, default=list)
    status = Column(String, default="pending")
    submission_image_url = Column(String, default="")
    submission_image_path = Column(String, default="")
    overlay_image_url = Column(String, default="")
    overlay_image_path = Column(String, default="")
    notes = Column(String, default="")
    updated_at = Column(DateTime, default=datetime.now)
    session = relationship("PracticeSessionModel", back_populates="step_runs")
