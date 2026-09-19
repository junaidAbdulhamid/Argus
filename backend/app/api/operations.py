from datetime import timedelta
from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from app.auth.security import current_user
from app.db.session import get_db
from app.models.entities import Project, Task, AuditEvent, AnnotationAssignment, AssignmentStatus, User, now
from app.repositories.platform import counts, serialize
from app.queue.redis_queue import health

router = APIRouter(tags=["Operations"])


@router.get("/overview")
def overview(project_id: str | None = None, user=Depends(current_user), db=Depends(get_db)):
    projects = select(Project.id).where(Project.organization_id == user.organization_id)
    if project_id:
        projects = projects.where(Project.id == project_id)
    ids = list(db.scalars(projects))
    summary = counts(db, ids)
    recent = db.execute(
        select(AuditEvent, User.full_name)
        .outerjoin(User, AuditEvent.user_id == User.id)
        .where(AuditEvent.organization_id == user.organization_id, AuditEvent.project_id.in_(ids))
        .order_by(AuditEvent.timestamp.desc())
        .limit(20)
    ).all()
    cutoff = now() - timedelta(days=7)
    completed = list(
        db.scalars(
            select(AnnotationAssignment.completed_at)
            .join(Task)
            .where(
                Task.project_id.in_(ids),
                AnnotationAssignment.status == AssignmentStatus.COMPLETED,
                AnnotationAssignment.completed_at >= cutoff,
            )
        )
    )
    throughput = [
        {
            "date": (now() - timedelta(days=d)).date().isoformat(),
            "count": sum(t.date() == (now() - timedelta(days=d)).date() for t in completed),
        }
        for d in range(6, -1, -1)
    ]
    oldest = db.scalar(select(func.min(Task.created_at)).where(Task.project_id.in_(ids), Task.status == "QUEUED"))
    return {
        "counts": summary,
        "throughput": throughput,
        "completed_this_week": len(completed),
        "queue": {"length": summary.get("QUEUED", 0), "redis": health(), "oldest_queued_at": oldest},
        "activity": [{**serialize(e), "actor": name or "Deleted user"} for e, name in recent],
    }
