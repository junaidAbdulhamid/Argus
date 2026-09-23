from datetime import timedelta
from fastapi import HTTPException
from sqlalchemy import select, func
from app.models.entities import (
    Task,
    TaskStatus,
    Project,
    AuditEvent,
    AnnotationAssignment,
    AssignmentStatus,
    Annotation,
    User,
    now,
)
from app.core.config import settings
from app.queue.redis_queue import sync_task, pop_priority_hint

TRANSITIONS = {
    TaskStatus.INGESTED: {TaskStatus.QUEUED},
    TaskStatus.QUEUED: {TaskStatus.ASSIGNED, TaskStatus.ESCALATED},
    TaskStatus.ASSIGNED: {TaskStatus.ANNOTATED, TaskStatus.QUEUED, TaskStatus.ESCALATED},
    TaskStatus.ANNOTATED: {TaskStatus.PENDING_REVIEW},
    TaskStatus.PENDING_REVIEW: {
        TaskStatus.APPROVED,
        TaskStatus.REJECTED,
        TaskStatus.CHANGES_REQUESTED,
        TaskStatus.ESCALATED,
    },
    TaskStatus.REJECTED: {TaskStatus.QUEUED, TaskStatus.ESCALATED},
    TaskStatus.CHANGES_REQUESTED: {TaskStatus.QUEUED, TaskStatus.ESCALATED},
    TaskStatus.ESCALATED: {
        TaskStatus.PENDING_REVIEW,
        TaskStatus.ASSIGNED,
        TaskStatus.QUEUED,
        TaskStatus.REJECTED,
        TaskStatus.CHANGES_REQUESTED,
    },
    TaskStatus.APPROVED: {
        TaskStatus.PENDING_REVIEW,
        TaskStatus.REJECTED,
        TaskStatus.CHANGES_REQUESTED,
        TaskStatus.ESCALATED,
    },
}


def audit(db, user, event, task=None, project_id=None, payload=None):
    db.add(
        AuditEvent(
            organization_id=user.organization_id,
            project_id=task.project_id if task else project_id,
            task_id=task.id if task else None,
            user_id=user.id,
            event_type=event,
            payload=payload or {},
        )
    )


def transition(db, user, task, target):
    if target not in TRANSITIONS[task.status]:
        raise HTTPException(409, f"Cannot transition task from {task.status.value} to {target.value}")
    before = task.status
    task.status = target
    audit(db, user, "TASK_STATE_CHANGED", task, payload={"from": before.value, "to": target.value})


def recover(db, user):
    cutoff = now() - timedelta(minutes=settings().assignment_timeout_minutes)
    tasks = (
        db.scalars(
            select(Task)
            .join(Project)
            .join(AnnotationAssignment)
            .where(
                Project.organization_id == user.organization_id,
                AnnotationAssignment.status.in_([AssignmentStatus.ASSIGNED, AssignmentStatus.STARTED]),
                AnnotationAssignment.assigned_at < cutoff,
            )
            .with_for_update(of=Task, skip_locked=True)
        )
        .unique()
        .all()
    )
    for task in tasks:
        expired = db.scalars(
            select(AnnotationAssignment)
            .where(
                AnnotationAssignment.task_id == task.id,
                AnnotationAssignment.status.in_([AssignmentStatus.ASSIGNED, AssignmentStatus.STARTED]),
                AnnotationAssignment.assigned_at < cutoff,
            )
            .with_for_update()
        ).all()
        for assignment in expired:
            assignment.status = AssignmentStatus.EXPIRED
            audit(db, user, "ASSIGNMENT_EXPIRED", task, payload={"assignment_id": assignment.id})
        db.flush()
        active = db.scalar(
            select(AnnotationAssignment.id)
            .where(
                AnnotationAssignment.task_id == task.id,
                AnnotationAssignment.status.in_([AssignmentStatus.ASSIGNED, AssignmentStatus.STARTED]),
            )
            .limit(1)
        )
        if not active and task.status == TaskStatus.ASSIGNED:
            transition(db, user, task, TaskStatus.QUEUED)
    db.flush()


def claim(db, user, project_id=None):
    from app.models.quality import GoldReference
    from app.services.quality_gate import policy

    db.scalar(select(User).where(User.id == user.id).with_for_update())
    recover(db, user)
    existing = db.scalar(
        select(AnnotationAssignment).where(
            AnnotationAssignment.annotator_id == user.id,
            AnnotationAssignment.status.in_([AssignmentStatus.ASSIGNED, AssignmentStatus.STARTED]),
        )
    )
    if existing:
        return existing
    reservations = (
        select(func.count(AnnotationAssignment.id))
        .where(
            AnnotationAssignment.task_id == Task.id,
            AnnotationAssignment.round == Task.annotation_round,
            AnnotationAssignment.status.in_(
                [AssignmentStatus.ASSIGNED, AssignmentStatus.STARTED, AssignmentStatus.COMPLETED]
            ),
        )
        .correlate(Task)
        .scalar_subquery()
    )
    previous = (
        select(AnnotationAssignment.id)
        .where(
            AnnotationAssignment.task_id == Task.id,
            AnnotationAssignment.annotator_id == user.id,
            AnnotationAssignment.round == Task.annotation_round,
            AnnotationAssignment.status != AssignmentStatus.EXPIRED,
        )
        .correlate(Task)
        .exists()
    )
    query = (
        select(Task)
        .join(Project)
        .where(
            Project.organization_id == user.organization_id,
            Project.status == "ACTIVE",
            Task.status.in_([TaskStatus.QUEUED, TaskStatus.ASSIGNED]),
            (reservations < Task.required_annotations) | Task.id.in_(select(GoldReference.task_id)),
            ~previous,
        )
    )
    if project_id:
        query = query.where(Task.project_id == project_id)
    completed = (
        db.scalar(
            select(func.count(AnnotationAssignment.id)).where(
                AnnotationAssignment.annotator_id == user.id, AnnotationAssignment.status == AssignmentStatus.COMPLETED
            )
        )
        or 0
    )
    # Interleave references at the configured cadence; lock only one candidate.
    projects = db.scalars(select(Project).where(Project.organization_id == user.organization_id)).all()
    due = [p.id for p in projects if (completed + 1) % policy(p)["gold_every"] == 0]
    gold = select(GoldReference.task_id)
    ordered = (
        query.order_by(Task.priority.desc(), Task.created_at, Task.id)
        .with_for_update(of=Task, skip_locked=True)
        .limit(1)
    )
    hint = pop_priority_hint(user.organization_id)
    while True:
        task = db.scalar(ordered.where(Task.project_id.in_(due), Task.id.in_(gold))) if due else None
        if task is None and hint is not None:
            task = db.scalar(ordered.where(Task.id.not_in(gold), Task.priority >= hint))
        if task is None:
            task = db.scalar(ordered.where(Task.id.not_in(gold)))
        if task is None:
            task = db.scalar(ordered)
        if not task:
            raise HTTPException(404, "No tasks are available in this queue")
        # Recheck in a fresh statement while holding the task lock: another claim
        # may have committed after the candidate query's READ COMMITTED snapshot.
        is_gold = db.scalar(select(GoldReference.id).where(GoldReference.task_id == task.id))
        reserved = db.scalar(
            select(func.count(AnnotationAssignment.id)).where(
                AnnotationAssignment.task_id == task.id,
                AnnotationAssignment.round == task.annotation_round,
                AnnotationAssignment.status.in_(
                    [AssignmentStatus.ASSIGNED, AssignmentStatus.STARTED, AssignmentStatus.COMPLETED]
                ),
            )
        )
        if is_gold or reserved < task.required_annotations:
            break
        ordered = ordered.where(Task.id != task.id)
    if task.status == TaskStatus.QUEUED:
        transition(db, user, task, TaskStatus.ASSIGNED)
    assignment = AnnotationAssignment(task_id=task.id, annotator_id=user.id, round=task.annotation_round)
    db.add(assignment)
    db.flush()
    audit(db, user, "TASK_ASSIGNED", task, payload={"assignment_id": assignment.id, "round": task.annotation_round})
    db.commit()
    sync_task(task.id, user.organization_id, task.priority, False)
    return assignment


def owned_assignment(db, user, assignment_id):
    # Always lock task before assignment, matching recovery's lock order.
    row = db.scalar(
        select(AnnotationAssignment).where(
            AnnotationAssignment.id == assignment_id, AnnotationAssignment.annotator_id == user.id
        )
    )
    if not row:
        raise HTTPException(404, "Assignment not found")
    task = db.scalar(select(Task).where(Task.id == row.task_id).with_for_update())
    db.refresh(row, with_for_update=True)
    if row.status not in [AssignmentStatus.ASSIGNED, AssignmentStatus.STARTED]:
        raise HTTPException(409, "Assignment is no longer active")
    if row.assigned_at.replace(tzinfo=now().tzinfo) < now() - timedelta(minutes=settings().assignment_timeout_minutes):
        raise HTTPException(409, "Assignment expired; request the next task to recover it")
    return row, task


def complete(db, user, assignment_id):
    from app.services.annotation_schema import validate_values
    from app.services.consensus import completed_annotations, calculate
    from app.services.quality_gate import policy
    from app.services.gold import grade
    from app.services.review import escalate

    assignment, task = owned_assignment(db, user, assignment_id)
    annotation = db.scalar(select(Annotation).where(Annotation.assignment_id == assignment.id))
    if not annotation:
        raise HTTPException(409, "Save an annotation before completing the assignment")
    validate_values(db, task, annotation.values)
    assignment.status = AssignmentStatus.COMPLETED
    assignment.completed_at = now()
    db.flush()
    audit(
        db, user, "ANNOTATION_SUBMITTED", task, payload={"assignment_id": assignment.id, "round": task.annotation_round}
    )
    gold_attempt = grade(db, user, task, annotation)
    if gold_attempt:
        if task.status == TaskStatus.ASSIGNED:
            transition(db, user, task, TaskStatus.QUEUED)
        db.flush()
        return assignment
    if len(completed_annotations(db, task)) >= task.required_annotations:
        if task.status != TaskStatus.ESCALATED:
            transition(db, user, task, TaskStatus.ANNOTATED)
            transition(db, user, task, TaskStatus.PENDING_REVIEW)
        consensus = calculate(db, task)
        rules = policy(db.get(Project, task.project_id))
        if consensus["conflicting"] and rules["auto_escalate_disagreement"]:
            escalate(
                db, user, task, "Independent annotations disagree; human adjudication is required.", "DISAGREEMENT"
            )
    db.flush()
    return assignment
