from collections import Counter, defaultdict
from statistics import mean, median
from sqlalchemy import select
from app.models.entities import (
    User,
    Task,
    Project,
    Annotation,
    AnnotationAssignment,
    AssignmentStatus,
    TaskStatus,
    Role,
)
from app.models.quality import GoldAttempt, GoldReference, Review, Escalation, QualityGateResult
from app.services.consensus import calculate, cohen_kappa, fleiss_kappa


def dashboard(db, user, project_id=None, date_from=None, date_to=None):
    q = select(Task).join(Project).where(Project.organization_id == user.organization_id)
    if project_id:
        q = q.where(Task.project_id == project_id)
    if date_from:
        q = q.where(Task.created_at >= date_from)
    if date_to:
        q = q.where(Task.created_at <= date_to)
    tasks = db.scalars(q).all()
    ids = [t.id for t in tasks]
    reviews = db.scalars(select(Review).where(Review.task_id.in_(ids))).all()
    escalations = db.scalars(select(Escalation).where(Escalation.task_id.in_(ids))).all()
    completed = db.execute(
        select(AnnotationAssignment, Annotation)
        .join(Annotation)
        .where(AnnotationAssignment.task_id.in_(ids), AnnotationAssignment.status == AssignmentStatus.COMPLETED)
    ).all()
    attempts = db.scalars(
        select(GoldAttempt).join(GoldReference).where(GoldReference.task_id.in_(ids)).order_by(GoldAttempt.created_at)
    ).all()
    summaries = [calculate(db, t, store=False) for t in tasks]
    measured = [s for s in summaries if s["labels"]["raw_agreement"] is not None]
    gates = db.scalars(
        select(QualityGateResult).where(QualityGateResult.task_id.in_(ids)).order_by(QualityGateResult.created_at)
    ).all()
    latest_gates = {g.task_id: g for g in gates}
    cohorts = defaultdict(dict)
    task_rounds = {t.id: t.annotation_round for t in tasks}
    for assignment, annotation in completed:
        if assignment.round == task_rounds[assignment.task_id]:
            cohorts[assignment.task_id][annotation.annotator_id] = annotation.label
    pair_tasks = defaultdict(list)
    for answers in cohorts.values():
        authors = sorted(answers)
        for i, a in enumerate(authors):
            for b in authors[i + 1 :]:
                pair_tasks[(a, b)].append((answers[a], answers[b]))
    cohen = [
        {
            "annotator_ids": list(pair),
            "annotator_names": [db.get(User, uid).full_name for uid in pair],
            "tasks": len(values),
            "kappa": cohen_kappa(values),
        }
        for pair, values in pair_tasks.items()
        if len(values) >= 2
    ]
    by_size = defaultdict(list)
    for answers in cohorts.values():
        if len(answers) > 1:
            by_size[len(answers)].append(list(answers.values()))
    fleiss = [{"raters_per_task": n, "tasks": len(rows), "kappa": fleiss_kappa(rows)} for n, rows in by_size.items()]
    profiles = []
    users = db.scalars(
        select(User).where(User.organization_id == user.organization_id, User.role.in_([Role.ANNOTATOR, Role.ADMIN]))
    ).all()
    for worker in users:
        work = [(a, n) for a, n in completed if a.annotator_id == worker.id]
        times = [
            (a.completed_at - a.started_at).total_seconds() / 60 for a, _ in work if a.started_at and a.completed_at
        ]
        gold = [a for a in attempts if a.annotator_id == worker.id]
        rolling = gold[-20:]
        work_ids = {a.task_id for a, _ in work}
        reviewed = {r.task_id for r in reviews if r.task_id in work_ids}
        rejected = {r.task_id for r in reviews if r.task_id in work_ids and r.decision == "REJECTED"}
        revised = {r.task_id for r in reviews if r.task_id in work_ids and r.decision == "REQUEST_CHANGES"}
        agreements = []
        for a, n in work:
            if a.round != task_rounds[a.task_id]:
                continue
            answers = cohorts.get(a.task_id, {})
            others = [label for uid, label in answers.items() if uid != worker.id]
            if others:
                counts = Counter(others)
                top = counts.most_common()
                if len(top) == 1 or top[0][1] > top[1][1]:
                    agreements.append(n.label == top[0][0])
        throughput = Counter(a.completed_at.date().isoformat() for a, _ in work)
        profiles.append(
            {
                "user_id": worker.id,
                "name": worker.full_name,
                "tasks_completed": len(work),
                "median_minutes": median(times) if times else None,
                "agreement_with_others": mean(agreements) if agreements else None,
                "agreement_samples": len(agreements),
                "gold_attempted": len(gold),
                "gold_accuracy": mean(a.accuracy for a in gold) if gold else None,
                "rolling_gold_accuracy": mean(a.accuracy for a in rolling) if rolling else None,
                "recent_failures": sum(a.accuracy < 1 for a in rolling),
                "rejection_rate": len(rejected) / len(reviewed) if reviewed else None,
                "revision_rate": len(revised) / len(reviewed) if reviewed else None,
                "reviewed_tasks": len(reviewed),
                "throughput": [{"date": d, "count": n} for d, n in sorted(throughput.items())],
                "quality_trend": [
                    {
                        "date": a.created_at.isoformat(),
                        "accuracy": a.accuracy,
                        "annotation_id": a.annotation_id,
                        "comparison": a.comparison,
                    }
                    for a in rolling
                ],
            }
        )
    latest_review = {}
    for r in sorted(reviews, key=lambda x: x.created_at):
        latest_review[r.task_id] = r
    return {
        "tasks": len(tasks),
        "pending_reviews": sum(t.status == TaskStatus.PENDING_REVIEW for t in tasks),
        "approval_rate": sum(r.decision == "APPROVED" for r in latest_review.values()) / len(latest_review)
        if latest_review
        else None,
        "disagreement_rate": mean(s["labels"]["disagreement_rate"] for s in measured) if measured else None,
        "agreement_task_count": len(measured),
        "open_escalations": sum(e.status == "OPEN" for e in escalations),
        "gold_attempts": len(attempts),
        "gold_accuracy": mean(a.accuracy for a in attempts) if attempts else None,
        "annotations_completed": len(completed),
        "eligibility_rate": sum(g.eligible for g in latest_gates.values()) / len(latest_gates)
        if latest_gates
        else None,
        "eligibility_evaluated_tasks": len(latest_gates),
        "eligibility_note": "Most recent recorded gate evaluation per task; builders always re-evaluate current evidence.",
        "cohen_kappa": cohen,
        "fleiss_kappa": fleiss,
        "annotators": profiles if user.role == Role.ADMIN else [],
        "filter_basis": "Task creation date; metrics include the selected tasks’ recorded work.",
    }
