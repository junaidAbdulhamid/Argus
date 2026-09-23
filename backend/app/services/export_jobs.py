import hashlib
import logging
import os
from datetime import timedelta
from pathlib import Path
from fastapi import HTTPException
from sqlalchemy import select, or_, and_
from redis.exceptions import RedisError
from app.core.config import settings
from app.db.session import SessionLocal
from app.models.entities import User, now
from app.models.datasets import ExportJob, DatasetVersion, TrainingExample, DatasetExample
from app.models.quality import QualityGateResult
from app.services.datasets import canonical
from app.services.export_formats import export_record
from app.services.workflow import audit
from app.queue.redis_queue import client

logger = logging.getLogger(__name__)


def request_export(db, user, version, data):
    if version.status != "FINALIZED":
        raise HTTPException(409, "Finalize the dataset version before exporting")
    # Source compatibility and serialization run in the worker, not the HTTP request.
    job = ExportJob(version_id=version.id, requested_by=user.id, format=data.format, container=data.container)
    db.add(job)
    db.flush()
    audit(db, user, "EXPORT_REQUESTED", payload={"job_id": job.id, "version_id": version.id, "format": job.format})
    db.commit()
    try:
        client().lpush("argus:exports", job.id)
    except RedisError:
        logger.warning("Export notification unavailable; worker will discover the persisted job")
    return job


def artifact_directory(job_id):
    # IDs are server-generated UUIDs; never accept user-controlled filesystem paths.
    import uuid

    return Path(settings().export_directory) / str(uuid.UUID(job_id))


def generate_artifacts(db, job):
    version = db.get(DatasetVersion, job.version_id)
    directory = artifact_directory(job.id)
    directory.mkdir(parents=True, exist_ok=True)
    file = directory / f"dataset.{job.container}"
    temporary = directory / f"dataset.{job.container}.tmp"
    digest = hashlib.sha256()
    count = 0
    provenance = []

    def write(stream, value):
        encoded = value.encode("utf-8")
        stream.write(encoded)
        digest.update(encoded)

    q = (
        select(DatasetExample, TrainingExample)
        .join(TrainingExample)
        .where(DatasetExample.version_id == version.id)
        .order_by(DatasetExample.position)
        .execution_options(yield_per=100)
    )
    with temporary.open("wb") as stream:
        if job.container == "json":
            write(stream, "[")
        for member, example in db.execute(q):
            record = export_record(example.snapshot, job.format)
            if job.container == "json" and count:
                write(stream, ",")
            write(stream, canonical(record) + ("\n" if job.container == "jsonl" else ""))
            provenance.append(
                {
                    "row": count,
                    "example_id": example.id,
                    "task_id": example.task_id,
                    "example_checksum": example.checksum,
                    "source_gate_id": example.gate_result_id,
                    "finalization_gate": db.get(QualityGateResult, member.gate_result_id).evidence,
                    "finalization_gate_id": member.gate_result_id,
                    "annotation_ids": [a["id"] for a in example.snapshot["annotations"]],
                    "review_ids": [r["id"] for r in example.snapshot["reviews"]],
                    "agent_run_ids": [r["id"] for r in example.snapshot["runs"]],
                }
            )
            count += 1
        if job.container == "json":
            write(stream, "]\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, file)
    provenance_bytes = (canonical(provenance) + "\n").encode()
    (directory / "provenance.json").write_bytes(provenance_bytes)
    schema = {
        "schema_version": version.schema_version,
        "format": job.format,
        "container": job.container,
        "fields": {
            "sft": ["messages"],
            "dpo": ["prompt", "chosen", "rejected"],
            "reward": ["prompt", "response", "score"],
            "trajectory": ["task", "trajectory", "reward", "metadata"],
        }[job.format],
        "reward_normalization": "(mean human 1–5 quality score - 1) / 4",
        "sft_policy": "Prompt and final answer only; full agent trace is available in trajectory format and provenance.",
    }
    schema_bytes = (canonical(schema) + "\n").encode()
    (directory / "schema.json").write_bytes(schema_bytes)
    manifest = {
        "job_id": job.id,
        "dataset_version_id": version.id,
        "dataset_version": version.version,
        "version_checksum": version.checksum,
        "schema_version": version.schema_version,
        "format": job.format,
        "container": job.container,
        "example_count": count,
        "created_at": now().isoformat(),
        "files": {
            "dataset": {"name": file.name, "sha256": digest.hexdigest(), "bytes": file.stat().st_size},
            "provenance": {"name": "provenance.json", "sha256": hashlib.sha256(provenance_bytes).hexdigest()},
            "schema": {"name": "schema.json", "sha256": hashlib.sha256(schema_bytes).hexdigest()},
        },
    }
    (directory / "manifest.json").write_text(canonical(manifest) + "\n")
    return manifest


def process_next(factory=SessionLocal):
    with factory() as db:
        cutoff = now() - timedelta(minutes=15)
        job = db.scalar(
            select(ExportJob)
            .where(
                or_(ExportJob.status == "PENDING", and_(ExportJob.status == "RUNNING", ExportJob.started_at < cutoff))
            )
            .order_by(ExportJob.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if not job:
            return False
        job.status = "RUNNING"
        job.started_at = now()
        job.error = None
        job_id = job.id
        db.commit()
        # Keep a row lock throughout generation. Recovery skips live workers.
        job = db.scalar(select(ExportJob).where(ExportJob.id == job_id).with_for_update())
        if job.status != "RUNNING":
            return True
        user = db.get(User, job.requested_by)
        try:
            manifest = generate_artifacts(db, job)
            job.manifest = manifest
            job.status = "COMPLETED"
            job.completed_at = now()
            audit(
                db,
                user,
                "EXPORT_COMPLETED",
                payload={"job_id": job.id, "checksum": manifest["files"]["dataset"]["sha256"]},
            )
            db.commit()
        except Exception as exc:
            db.rollback()
            logger.exception("Export failed job_id=%s", job_id)
            job = db.get(ExportJob, job_id)
            job.status = "FAILED"
            job.error = str(exc)[:2000]
            job.completed_at = now()
            audit(db, user, "EXPORT_FAILED", payload={"job_id": job.id, "error": job.error})
            db.commit()
        return True
