"""Versioned quality configuration and append-oriented human decisions."""
from datetime import datetime
from sqlalchemy import ForeignKey, String, Text, Integer, Float, Boolean, DateTime, UniqueConstraint, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.models.entities import Base, Identity, json_type, now


class AnnotationSchema(Identity, Base):
    __tablename__ = "annotation_schemas"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(200))
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (UniqueConstraint("project_id", "version"),)


class AnnotationField(Identity, Base):
    __tablename__ = "annotation_fields"
    schema_id: Mapped[str] = mapped_column(ForeignKey("annotation_schemas.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(100))
    label: Mapped[str] = mapped_column(String(200))
    field_type: Mapped[str] = mapped_column(String(30))
    description: Mapped[str] = mapped_column(Text, default="")
    required: Mapped[bool] = mapped_column(Boolean, default=False)
    constraints: Mapped[dict] = mapped_column(json_type, default=dict)
    options: Mapped[list] = mapped_column(json_type, default=list)
    position: Mapped[int] = mapped_column(Integer)
    __table_args__ = (UniqueConstraint("schema_id", "key"), CheckConstraint("field_type IN ('boolean','single_select','multi_select','integer_rating','continuous_score','text','json')"))


class Review(Identity, Base):
    __tablename__ = "reviews"
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    reviewer_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    round: Mapped[int] = mapped_column(Integer)
    annotation_ids: Mapped[list] = mapped_column(json_type)
    decision: Mapped[str] = mapped_column(String(30))
    comments: Mapped[str] = mapped_column(Text)
    metadata_: Mapped[dict] = mapped_column("metadata", json_type, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (CheckConstraint("decision IN ('APPROVED','REJECTED','REQUEST_CHANGES','ESCALATED')"),)


class ConsensusResult(Identity, Base):
    __tablename__ = "consensus_results"
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    round: Mapped[int] = mapped_column(Integer)
    annotation_ids: Mapped[list] = mapped_column(json_type)
    metrics: Mapped[dict] = mapped_column(json_type)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Escalation(Identity, Base):
    __tablename__ = "escalations"
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    source: Mapped[str] = mapped_column(String(30))
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="OPEN")
    resolution: Mapped[str | None] = mapped_column(Text)
    resolved_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (CheckConstraint("status IN ('OPEN','RESOLVED','DISMISSED')"),)


class GoldReference(Identity, Base):
    __tablename__ = "gold_references"
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), unique=True)
    expected: Mapped[dict] = mapped_column(json_type)
    tolerance: Mapped[float] = mapped_column(Float, default=0)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class GoldAttempt(Identity, Base):
    __tablename__ = "gold_attempts"
    reference_id: Mapped[str] = mapped_column(ForeignKey("gold_references.id", ondelete="RESTRICT"))
    annotator_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    annotation_id: Mapped[str] = mapped_column(ForeignKey("annotations.id", ondelete="RESTRICT"), unique=True)
    accuracy: Mapped[float] = mapped_column(Float)
    comparison: Mapped[dict] = mapped_column(json_type)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class QualityGateResult(Identity, Base):
    __tablename__ = "quality_gate_results"
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    round: Mapped[int] = mapped_column(Integer)
    eligible: Mapped[bool] = mapped_column(Boolean)
    reasons: Mapped[list] = mapped_column(json_type)
    policy: Mapped[dict] = mapped_column(json_type)
    evidence: Mapped[dict] = mapped_column(json_type)
    evaluated_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class PreferencePair(Identity, Base):
    __tablename__ = 'preference_pairs'
    task_id: Mapped[str] = mapped_column(ForeignKey('tasks.id', ondelete='RESTRICT'), index=True)
    round: Mapped[int] = mapped_column(Integer)
    chosen_run_id: Mapped[str] = mapped_column(ForeignKey('agent_runs.id', ondelete='RESTRICT'))
    rejected_run_id: Mapped[str] = mapped_column(ForeignKey('agent_runs.id', ondelete='RESTRICT'))
    reviewer_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='RESTRICT'))
    rationale: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (UniqueConstraint('task_id','round'), CheckConstraint('chosen_run_id != rejected_run_id'))
