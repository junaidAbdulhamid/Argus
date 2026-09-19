from datetime import datetime
from sqlalchemy import ForeignKey, String, Text, Integer, DateTime, UniqueConstraint, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.models.entities import Base, Identity, json_type, now


class TrainingExample(Identity, Base):
    __tablename__ = "training_examples"
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="RESTRICT"), index=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="RESTRICT"), index=True)
    gate_result_id: Mapped[str] = mapped_column(ForeignKey("quality_gate_results.id", ondelete="RESTRICT"))
    round: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[dict] = mapped_column(json_type)
    checksum: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (UniqueConstraint("task_id", "round", "checksum"),)


class Dataset(Identity, Base):
    __tablename__ = "datasets"
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="RESTRICT"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class DatasetVersion(Identity, Base):
    __tablename__ = "dataset_versions"
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id", ondelete="RESTRICT"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="DRAFT")
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    example_count: Mapped[int] = mapped_column(Integer, default=0)
    filters: Mapped[dict] = mapped_column(json_type, default=dict)
    schema_version: Mapped[str] = mapped_column(String(30), default="argus.training.v1")
    checksum: Mapped[str | None] = mapped_column(String(64))
    metadata_: Mapped[dict] = mapped_column("metadata", json_type, default=dict)
    __table_args__ = (UniqueConstraint("dataset_id", "version"), CheckConstraint("status IN ('DRAFT','FINALIZED')"))


class DatasetExample(Identity, Base):
    __tablename__ = "dataset_examples"
    version_id: Mapped[str] = mapped_column(ForeignKey("dataset_versions.id", ondelete="RESTRICT"), index=True)
    example_id: Mapped[str] = mapped_column(ForeignKey("training_examples.id", ondelete="RESTRICT"))
    position: Mapped[int] = mapped_column(Integer)
    gate_result_id: Mapped[str | None] = mapped_column(ForeignKey("quality_gate_results.id", ondelete="RESTRICT"))
    __table_args__ = (UniqueConstraint("version_id", "example_id"), UniqueConstraint("version_id", "position"))


class ExportJob(Identity, Base):
    __tablename__ = "export_jobs"
    version_id: Mapped[str] = mapped_column(ForeignKey("dataset_versions.id", ondelete="RESTRICT"), index=True)
    requested_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    format: Mapped[str] = mapped_column(String(30))
    container: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(20), default="PENDING", index=True)
    error: Mapped[str | None] = mapped_column(Text)
    manifest: Mapped[dict] = mapped_column(json_type, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (CheckConstraint("status IN ('PENDING','RUNNING','COMPLETED','FAILED')"),)
