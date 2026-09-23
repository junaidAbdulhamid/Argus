from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from app.db.session import get_db
from app.auth.security import roles
from app.models.entities import Role, AnnotationAssignment, AssignmentStatus, Annotation, now
from app.schemas.requests import AnnotationInput
from app.repositories.platform import serialize
from app.services.annotation_schema import validate_values, schema_detail
from app.models.quality import AnnotationSchema
from app.models.entities import Task
from app.services.workflow import claim, owned_assignment, complete, audit

router = APIRouter(tags=["Annotation"])
annotator = roles(Role.ANNOTATOR, Role.ADMIN)


@router.post("/annotation/next")
def next_task(project_id: str | None = None, user=Depends(annotator), db=Depends(get_db)):
    return serialize(claim(db, user, project_id))


@router.get("/annotation/assignments")
def assignments(user=Depends(annotator), db=Depends(get_db)):
    return [
        serialize(a)
        for a in db.scalars(
            select(AnnotationAssignment)
            .where(AnnotationAssignment.annotator_id == user.id)
            .order_by(AnnotationAssignment.assigned_at.desc())
        )
    ]


@router.get("/annotation/assignments/{assignment_id}")
def get_assignment(assignment_id: str, user=Depends(annotator), db=Depends(get_db)):
    row = db.scalar(
        select(AnnotationAssignment).where(
            AnnotationAssignment.id == assignment_id, AnnotationAssignment.annotator_id == user.id
        )
    )
    if not row:
        raise HTTPException(404, "Assignment not found")
    annotation = db.scalar(select(Annotation).where(Annotation.assignment_id == row.id))
    task = db.get(Task, row.task_id)
    schema = db.get(AnnotationSchema, task.schema_id) if task.schema_id else None
    return {
        **serialize(row),
        "annotation": serialize(annotation) if annotation else None,
        "schema": schema_detail(db, schema),
    }


@router.post("/assignments/{assignment_id}/start")
def start(assignment_id: str, user=Depends(annotator), db=Depends(get_db)):
    row, task = owned_assignment(db, user, assignment_id)
    if row.status == AssignmentStatus.ASSIGNED:
        row.status = AssignmentStatus.STARTED
        row.started_at = now()
        audit(db, user, "ANNOTATION_STARTED", task)
    return serialize(row)


@router.post("/assignments/{assignment_id}/annotations", status_code=201)
def annotate(assignment_id: str, data: AnnotationInput, user=Depends(annotator), db=Depends(get_db)):
    row, task = owned_assignment(db, user, assignment_id)
    if row.status != AssignmentStatus.STARTED:
        raise HTTPException(409, "Start the assignment before annotating")
    if db.scalar(select(Annotation).where(Annotation.assignment_id == row.id)):
        raise HTTPException(409, "Annotation exists; use PATCH to update it")
    validate_values(db, task, data.values)
    annotation = Annotation(task_id=task.id, annotator_id=user.id, assignment_id=row.id, **data.model_dump())
    db.add(annotation)
    db.flush()
    audit(db, user, "ANNOTATION_SAVED", task, payload={"annotation_id": annotation.id})
    return serialize(annotation)


@router.patch("/annotations/{annotation_id}")
def update(annotation_id: str, data: AnnotationInput, user=Depends(annotator), db=Depends(get_db)):
    row = db.scalar(select(Annotation).where(Annotation.id == annotation_id, Annotation.annotator_id == user.id))
    if not row:
        raise HTTPException(404, "Annotation not found")
    _, task = owned_assignment(db, user, row.assignment_id)
    validate_values(db, task, data.values)
    for key, value in data.model_dump().items():
        setattr(row, key, value)
    audit(db, user, "ANNOTATION_UPDATED", task, payload={"annotation_id": row.id})
    db.flush()
    return serialize(row)


@router.post("/assignments/{assignment_id}/complete")
def finish(assignment_id: str, user=Depends(annotator), db=Depends(get_db)):
    return serialize(complete(db, user, assignment_id))
