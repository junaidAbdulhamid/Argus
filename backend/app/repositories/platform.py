from fastapi import HTTPException
from sqlalchemy import select, func
from app.models.entities import Project, Task, AnnotationAssignment, Role


def project(db, user, project_id, lock=False):
    q = select(Project).where(Project.id == project_id, Project.organization_id == user.organization_id)
    obj = db.scalar(q.with_for_update() if lock else q)
    if not obj:
        raise HTTPException(404, "Project not found")
    return obj


def task(db, user, task_id, lock=False):
    q = select(Task).join(Project).where(Task.id == task_id, Project.organization_id == user.organization_id)
    if user.role == Role.ANNOTATOR:
        q = q.where(
            Task.id.in_(select(AnnotationAssignment.task_id).where(AnnotationAssignment.annotator_id == user.id))
        )
    obj = db.scalar(q.with_for_update(of=Task) if lock else q)
    if not obj:
        raise HTTPException(404, "Task not found")
    return obj


def counts(db, project_ids):
    values = db.execute(
        select(Task.status, func.count()).where(Task.project_id.in_(project_ids)).group_by(Task.status)
    ).all()
    result = {status.value: count for status, count in values}
    result["total"] = sum(result.values())
    return result


def serialize(obj):
    return {
        col.name: getattr(obj, "metadata_" if col.name == "metadata" else col.name)
        for col in obj.__table__.columns
        if col.name != "password_hash"
    }
