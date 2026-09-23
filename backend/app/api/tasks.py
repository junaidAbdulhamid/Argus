from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select, func, or_
from app.db.session import get_db
from app.auth.security import current_user, roles
from app.models.entities import (
    Task,
    Project,
    Role,
    TaskStatus,
    AgentRun,
    TrajectoryStep,
    AuditEvent,
    Annotation,
    AnnotationAssignment,
    AssignmentStatus,
    User,
)
from app.schemas.requests import TaskCreate, BatchCreate, RunCreate, ReviewInput
from app.repositories.platform import project, task, serialize
from app.services.ingestion import ingest, ingest_run
from app.services.workflow import transition, audit
from app.queue.redis_queue import sync_task
from app.services.annotation_schema import active_schema
from app.services.quality_gate import policy
from app.services.review import submit_review

router = APIRouter(tags=["Tasks and trajectories"])


@router.post("/projects/{project_id}/tasks", status_code=201)
def create(project_id: str, data: TaskCreate, user=Depends(roles(Role.ADMIN)), db=Depends(get_db)):
    return serialize(ingest(db, user, project(db, user, project_id, lock=True), data))


@router.post("/projects/{project_id}/tasks/batch", status_code=201)
def batch(project_id: str, data: BatchCreate, user=Depends(roles(Role.ADMIN)), db=Depends(get_db)):
    p = project(db, user, project_id, lock=True)
    return [serialize(ingest(db, user, p, item)) for item in data.tasks]


@router.get("/tasks")
def listing(
    project_id: str | None = None,
    status: TaskStatus | None = None,
    priority: int | None = Query(None, ge=0, le=100),
    search: str = "",
    sort: str = Query("created_at", pattern="^(created_at|priority|status)$"),
    direction: str = Query("desc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user=Depends(current_user),
    db=Depends(get_db),
):
    q = select(Task).join(Project).where(Project.organization_id == user.organization_id)
    if user.role == Role.ANNOTATOR:
        q = q.where(
            Task.id.in_(select(AnnotationAssignment.task_id).where(AnnotationAssignment.annotator_id == user.id))
        )
    if project_id:
        q = q.where(Task.project_id == project_id)
    if status:
        q = q.where(Task.status == status)
    if priority is not None:
        q = q.where(Task.priority == priority)
    if search:
        q = q.where(
            or_(
                Task.id.ilike(f"%{search}%"), Task.external_id.ilike(f"%{search}%"), Task.task_type.ilike(f"%{search}%")
            )
        )
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    column = getattr(Task, sort)
    rows = db.scalars(
        q.order_by(column.desc() if direction == "desc" else column.asc(), Task.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    assignees = dict(
        db.execute(
            select(AnnotationAssignment.task_id, User.full_name)
            .join(User, User.id == AnnotationAssignment.annotator_id)
            .where(
                AnnotationAssignment.task_id.in_([t.id for t in rows]),
                AnnotationAssignment.status.in_([AssignmentStatus.ASSIGNED, AssignmentStatus.STARTED]),
            )
        ).all()
    )
    return {
        "items": [{**serialize(t), "annotator": assignees.get(t.id)} for t in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/tasks/{task_id}")
def get(task_id: str, user=Depends(current_user), db=Depends(get_db)):
    obj = task(db, user, task_id)
    p = project(db, user, obj.project_id)
    own_completed = db.scalar(
        select(AnnotationAssignment.id).where(
            AnnotationAssignment.task_id == obj.id,
            AnnotationAssignment.annotator_id == user.id,
            AnnotationAssignment.round == obj.annotation_round,
            AnnotationAssignment.status == AssignmentStatus.COMPLETED,
        )
    )
    reveal = user.role != Role.ANNOTATOR or (
        policy(p)["reveal_after_completion"]
        and own_completed
        and obj.status in {TaskStatus.PENDING_REVIEW, TaskStatus.APPROVED, TaskStatus.REJECTED}
    )
    annotations = select(Annotation).where(Annotation.task_id == obj.id)
    assignments = select(AnnotationAssignment).where(AnnotationAssignment.task_id == obj.id)
    if not reveal:
        annotations = annotations.where(Annotation.annotator_id == user.id)
        assignments = assignments.where(AnnotationAssignment.annotator_id == user.id)
    return {
        **serialize(obj),
        "project": serialize(project(db, user, obj.project_id)),
        "annotations": [serialize(a) for a in db.scalars(annotations)],
        "assignments": [
            serialize(a) for a in db.scalars(assignments.order_by(AnnotationAssignment.assigned_at.desc()))
        ],
    }


@router.post("/tasks/{task_id}/runs", status_code=201)
def run(task_id: str, data: RunCreate, user=Depends(roles(Role.ADMIN)), db=Depends(get_db)):
    return serialize(ingest_run(db, user, task(db, user, task_id, lock=True), data))


@router.get("/tasks/{task_id}/trajectory")
def trajectory(task_id: str, user=Depends(current_user), db=Depends(get_db)):
    task(db, user, task_id)
    runs = db.scalars(
        select(AgentRun).where(AgentRun.task_id == task_id).order_by(AgentRun.started_at, AgentRun.id)
    ).all()
    return [
        {
            **serialize(r),
            "steps": [
                serialize(s)
                for s in db.scalars(
                    select(TrajectoryStep)
                    .where(TrajectoryStep.agent_run_id == r.id)
                    .order_by(TrajectoryStep.sequence_number)
                )
            ],
        }
        for r in runs
    ]


@router.get("/tasks/{task_id}/audit")
def events(task_id: str, user=Depends(current_user), db=Depends(get_db)):
    task(db, user, task_id)
    q = (
        select(AuditEvent, User.full_name)
        .outerjoin(User, AuditEvent.user_id == User.id)
        .where(AuditEvent.task_id == task_id)
    )
    if user.role == Role.ANNOTATOR:
        q = q.where(
            AuditEvent.user_id == user.id,
            AuditEvent.event_type.in_(
                [
                    "TASK_ASSIGNED",
                    "ANNOTATION_STARTED",
                    "ANNOTATION_SAVED",
                    "ANNOTATION_UPDATED",
                    "ANNOTATION_SUBMITTED",
                ]
            ),
        )
    return [
        {**serialize(e), "actor": name or "Deleted user"} for e, name in db.execute(q.order_by(AuditEvent.timestamp))
    ]


@router.post("/tasks/{task_id}/queue")
def enqueue(task_id: str, user=Depends(roles(Role.ADMIN)), db=Depends(get_db)):
    obj = task(db, user, task_id, lock=True)
    if not db.scalar(select(AgentRun.id).where(AgentRun.task_id == obj.id).limit(1)):
        raise HTTPException(409, "Ingest an agent trajectory before queueing this task")
    if obj.status in {TaskStatus.REJECTED, TaskStatus.CHANGES_REQUESTED}:
        obj.annotation_round += 1
    rules = policy(project(db, user, obj.project_id))
    obj.required_annotations = rules["required_annotations"]
    from app.models.quality import GoldReference

    if not db.scalar(select(GoldReference.id).where(GoldReference.task_id == obj.id)):
        schema = active_schema(db, obj.project_id)
        obj.schema_id = schema.id if schema else None
    transition(db, user, obj, TaskStatus.QUEUED)
    audit(db, user, "TASK_QUEUED", obj)
    db.commit()
    sync_task(obj.id, user.organization_id, obj.priority, True)
    return serialize(obj)


@router.post("/tasks/{task_id}/review")
def review(task_id: str, data: ReviewInput, user=Depends(roles(Role.ADMIN, Role.REVIEWER)), db=Depends(get_db)):
    obj = task(db, user, task_id, lock=True)
    submit_review(db, user, obj, data.decision, data.reason)
    return serialize(obj)
