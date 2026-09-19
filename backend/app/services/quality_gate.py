from sqlalchemy import select
from app.models.entities import Project
from app.models.quality import Review, Escalation, GoldAttempt, GoldReference, QualityGateResult
from app.schemas.quality import QualityRules
from app.services.consensus import calculate, completed_annotations
from app.services.workflow import audit


def policy(project):
    return QualityRules(**project.quality_rules).model_dump()


def latest_reviews(db,task):
    reviews=db.scalars(select(Review).where(Review.task_id==task.id,Review.round==task.annotation_round).order_by(Review.created_at,Review.id)).all()
    latest={}
    for review in reviews:
        latest[review.reviewer_id]=review
    return list(latest.values())


def evaluate(db,user,task):
    project=db.get(Project,task.project_id)
    rules=policy(project)
    annotations=completed_annotations(db,task)
    consensus=calculate(db,task)
    reasons=[]
    required=max(task.required_annotations,rules['required_annotations'])
    if len({a.annotator_id for a in annotations})<required:
        reasons.append('insufficient_independent_annotations')
    authors={a.annotator_id for a in annotations}
    reviews=latest_reviews(db,task)
    current_ids=sorted(a.id for a in annotations)
    approved=[r for r in reviews if r.decision=='APPROVED' and r.reviewer_id not in authors and sorted(r.annotation_ids)==current_ids]
    if len(approved)<rules['required_reviews']:
        reasons.append('requires_reviewer_approval')
    if any(r.decision in {'REJECTED','REQUEST_CHANGES'} for r in reviews):
        reasons.append('unresolved_review_decision')
    if task.status.value in {'INGESTED','QUEUED','ASSIGNED','REJECTED','CHANGES_REQUESTED'}:
        reasons.append('task_not_review_ready')
    if db.scalar(select(Escalation.id).where(Escalation.task_id==task.id,Escalation.status=='OPEN').limit(1)):
        reasons.append('unresolved_escalation')
    if db.scalar(select(GoldReference.id).where(GoldReference.task_id==task.id)):
        reasons.append('gold_reference_excluded_from_training')
    categorical_metrics=[consensus['labels'],*[v for v in consensus['fields'].values() if v['kind']=='categorical']]
    if any(m['raw_agreement'] is not None and m['raw_agreement']<rules['minimum_agreement'] for m in categorical_metrics):
        reasons.append('agreement_below_threshold')
    if rules['minimum_agreement']>0 and any(m['raw_agreement'] is None for m in categorical_metrics):
        reasons.append('insufficient_agreement_evidence')
    if annotations and min(a.score for a in annotations)<rules['minimum_score']:
        reasons.append('annotation_quality_below_threshold')
    numeric_metrics=[consensus['scores'],*[v for v in consensus['fields'].values() if v['kind']=='numeric']]
    if rules['maximum_variance'] is not None and any(m['variance'] is not None and m['variance']>rules['maximum_variance'] for m in numeric_metrics):
        reasons.append('score_variance_above_threshold')
    gold_profiles={}
    if rules['minimum_gold_accuracy'] is not None:
        for author in authors:
            attempts=db.scalars(select(GoldAttempt).where(GoldAttempt.annotator_id==author).order_by(GoldAttempt.created_at.desc()).limit(20)).all()
            accuracy=sum(a.accuracy for a in attempts)/len(attempts) if attempts else None
            gold_profiles[author]={"attempts":len(attempts),"rolling_accuracy":accuracy}
            if len(attempts)<rules['minimum_gold_attempts']:
                reasons.append('insufficient_gold_history')
            elif accuracy<rules['minimum_gold_accuracy']:
                reasons.append('gold_accuracy_below_threshold')
    row=QualityGateResult(task_id=task.id,round=task.annotation_round,eligible=not reasons,reasons=sorted(set(reasons)),policy=rules,evidence={"annotation_ids":current_ids,"review_ids":[r.id for r in approved],"consensus":consensus,"gold_profiles":gold_profiles},evaluated_by=user.id)
    db.add(row)
    db.flush()
    audit(db,user,'QUALITY_GATE_EVALUATED',task,payload={"gate_result_id":row.id,"eligible":row.eligible,"reasons":row.reasons})
    return row
