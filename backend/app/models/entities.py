import enum
import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    CheckConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Role(str, enum.Enum):
    ADMIN = "ADMIN"
    ANNOTATOR = "ANNOTATOR"
    REVIEWER = "REVIEWER"


class TaskStatus(str, enum.Enum):
    INGESTED = "INGESTED"
    QUEUED = "QUEUED"
    ASSIGNED = "ASSIGNED"
    ANNOTATED = "ANNOTATED"
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"
    ESCALATED = "ESCALATED"


class AssignmentStatus(str, enum.Enum):
    ASSIGNED = "ASSIGNED"
    STARTED = "STARTED"
    COMPLETED = "COMPLETED"
    EXPIRED = "EXPIRED"


class StepType(str, enum.Enum):
    user_message = "user_message"
    assistant_message = "assistant_message"
    tool_call = "tool_call"
    tool_result = "tool_result"
    observation = "observation"
    final_answer = "final_answer"


json_type = JSON().with_variant(JSONB(), "postgresql")


class Identity:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))


class Timestamps:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class Organization(Identity, Base):
    __tablename__ = "organizations"
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class User(Identity, Timestamps, Base):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    full_name: Mapped[str] = mapped_column(String(200))
    role: Mapped[Role] = mapped_column(Enum(Role))
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)


class Project(Identity, Timestamps, Base):
    __tablename__ = "projects"
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    quality_rules: Mapped[dict] = mapped_column(json_type, default=dict, server_default="{}")
    __table_args__ = (CheckConstraint("status IN ('ACTIVE', 'ARCHIVED')"),)


class Task(Identity, Timestamps, Base):
    __tablename__ = "tasks"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    annotation_round: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    required_annotations: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    schema_id: Mapped[str | None] = mapped_column(ForeignKey("annotation_schemas.id", ondelete="RESTRICT"))
    external_id: Mapped[str | None] = mapped_column(String(200))
    task_type: Mapped[str] = mapped_column(String(100))
    status: Mapped[TaskStatus] = mapped_column(Enum(TaskStatus), default=TaskStatus.INGESTED, index=True)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    input_payload: Mapped[dict] = mapped_column(json_type, default=dict)
    metadata_: Mapped[dict] = mapped_column("metadata", json_type, default=dict)
    __table_args__ = (
        UniqueConstraint("project_id", "external_id"),
        CheckConstraint("priority >= 0 AND priority <= 100"),
        Index("ix_task_queue", "status", "priority", "created_at"),
    )


class AgentRun(Identity, Base):
    __tablename__ = "agent_runs"
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    model_name: Mapped[str] = mapped_column(String(200))
    model_version: Mapped[str] = mapped_column(String(200), default="")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_: Mapped[dict] = mapped_column("metadata", json_type, default=dict)


class TrajectoryStep(Identity, Base):
    __tablename__ = "trajectory_steps"
    agent_run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True)
    sequence_number: Mapped[int] = mapped_column(Integer)
    step_type: Mapped[StepType] = mapped_column(Enum(StepType))
    content: Mapped[str] = mapped_column(Text, default="")
    tool_name: Mapped[str | None] = mapped_column(String(200))
    tool_input: Mapped[dict | None] = mapped_column(json_type)
    tool_output: Mapped[dict | None] = mapped_column(json_type)
    metadata_: Mapped[dict] = mapped_column("metadata", json_type, default=dict)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (UniqueConstraint("agent_run_id", "sequence_number"), CheckConstraint("sequence_number >= 0"))


class AnnotationAssignment(Identity, Base):
    __tablename__ = "annotation_assignments"
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    round: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    annotator_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    status: Mapped[AssignmentStatus] = mapped_column(Enum(AssignmentStatus), default=AssignmentStatus.ASSIGNED)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        Index(
            "uq_active_assignment",
            "task_id",
            "annotator_id",
            "round",
            unique=True,
            postgresql_where=text("status IN ('ASSIGNED', 'STARTED')"),
            sqlite_where=text("status IN ('ASSIGNED', 'STARTED')"),
        ),
    )


class Annotation(Identity, Timestamps, Base):
    __tablename__ = "annotations"
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    annotator_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    assignment_id: Mapped[str] = mapped_column(ForeignKey("annotation_assignments.id", ondelete="CASCADE"), unique=True)
    values: Mapped[dict] = mapped_column(json_type, default=dict, server_default="{}")
    label: Mapped[str] = mapped_column(String(100))
    score: Mapped[int] = mapped_column(Integer)
    feedback: Mapped[str] = mapped_column(Text, default="")
    structured_payload: Mapped[dict] = mapped_column(json_type, default=dict)
    __table_args__ = (CheckConstraint("score >= 1 AND score <= 5"),)


class AuditEvent(Identity, Base):
    __tablename__ = "audit_events"
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), index=True)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"), index=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    event_type: Mapped[str] = mapped_column(String(100))
    payload: Mapped[dict] = mapped_column(json_type, default=dict)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)


# Register all tables on the shared metadata for Alembic and test databases.
from app.models import quality, datasets  # noqa: E402,F401
