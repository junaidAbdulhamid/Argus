from fastapi import HTTPException
from sqlalchemy import select
from app.models.entities import Task, AgentRun, TrajectoryStep, TaskStatus
from app.services.workflow import audit


def ingest(db, user, project, data):
    if project.status != "ACTIVE":
        raise HTTPException(409, "Archived projects do not accept ingestion")
    if data.external_id:
        existing = db.scalar(select(Task).where(Task.project_id == project.id, Task.external_id == data.external_id))
        if existing:
            if (existing.task_type, existing.priority, existing.input_payload, existing.metadata_) != (
                data.task_type,
                data.priority,
                data.input_payload,
                data.metadata,
            ):
                raise HTTPException(409, "External ID already exists with different task content")
            return existing
    payload = data.model_dump()
    payload["metadata_"] = payload.pop("metadata")
    task = Task(project_id=project.id, **payload)
    db.add(task)
    db.flush()
    audit(db, user, "TASK_CREATED", task, payload={"external_id": task.external_id})
    return task


def ingest_run(db, user, task, data):
    if task.status != TaskStatus.INGESTED:
        raise HTTPException(409, "Trajectories are immutable after a task enters the annotation queue")
    payload = data.model_dump(exclude={"steps"}, exclude_none=True)
    payload["metadata_"] = payload.pop("metadata")
    run = AgentRun(task_id=task.id, **payload)
    db.add(run)
    db.flush()
    for step in data.steps:
        payload = step.model_dump(exclude_none=True)
        payload["metadata_"] = payload.pop("metadata")
        db.add(TrajectoryStep(agent_run_id=run.id, **payload))
    audit(db, user, "RUN_INGESTED", task, payload={"run_id": run.id, "steps": len(data.steps)})
    db.flush()
    return run
