from fastapi import HTTPException
from sqlalchemy import select
from app.models.entities import Annotation, TaskStatus, AnnotationAssignment, AssignmentStatus, now
from app.models.quality import Review, Escalation
from app.services.consensus import completed_annotations
from app.services.workflow import audit, transition
from app.services.quality_gate import evaluate


def escalate(db,user,task,reason,source='REVIEWER'):
    escalation=Escalation(task_id=task.id,created_by=user.id,reason=reason,source=source)
    db.add(escalation)
    if task.status not in {TaskStatus.INGESTED,TaskStatus.ESCALATED}:
        transition(db,user,task,TaskStatus.ESCALATED)
    audit(db,user,'ESCALATION_CREATED',task,payload={"source":source,"reason":reason})
    db.flush()
    return escalation


def resolve(db,user,task,escalation,data):
    if escalation.status!='OPEN':
        raise HTTPException(409,'Escalation has already been resolved')
    escalation.status=data.status
    escalation.resolution=data.resolution
    escalation.resolved_by=user.id
    escalation.resolved_at=now()
    db.flush()
    if task.status==TaskStatus.ESCALATED and not db.scalar(select(Escalation.id).where(Escalation.task_id==task.id,Escalation.status=='OPEN')):
        completed=len(completed_annotations(db,task))
        active=db.scalar(select(AnnotationAssignment.id).where(AnnotationAssignment.task_id==task.id,AnnotationAssignment.round==task.annotation_round,AnnotationAssignment.status.in_([AssignmentStatus.ASSIGNED,AssignmentStatus.STARTED])))
        transition(db,user,task,TaskStatus.PENDING_REVIEW if completed>=task.required_annotations else TaskStatus.ASSIGNED if active else TaskStatus.QUEUED)
    audit(db,user,'ESCALATION_RESOLVED',task,payload={"escalation_id":escalation.id,"status":data.status,"resolution":data.resolution})
    return escalation


def submit_review(db,user,task,decision,comments,metadata=None):
    if task.status not in {TaskStatus.PENDING_REVIEW,TaskStatus.APPROVED,TaskStatus.ESCALATED}:
        raise HTTPException(409,'Task is not ready for review')
    if db.scalar(select(Annotation.id).where(Annotation.task_id==task.id,Annotation.annotator_id==user.id)):
        raise HTTPException(403,'An independent reviewer must review this task')
    annotations=completed_annotations(db,task)
    if len(annotations)<task.required_annotations:
        raise HTTPException(409,'Required independent annotations are incomplete')
    if decision=='APPROVED' and db.scalar(select(Escalation.id).where(Escalation.task_id==task.id,Escalation.status=='OPEN')):
        raise HTTPException(409,'Resolve open escalations before approval')
    row=Review(task_id=task.id,reviewer_id=user.id,round=task.annotation_round,annotation_ids=[a.id for a in annotations],decision=decision,comments=comments,metadata_=metadata or {})
    db.add(row)
    db.flush()
    audit(db,user,'REVIEW_CREATED',task,payload={"review_id":row.id,"decision":decision,"comments":comments})
    # Preserve Phase 1 event consumers while maintaining normalized review evidence.
    audit(db,user,'TASK_REVIEWED',task,payload={"review_id":row.id,"decision":decision})
    if decision=='ESCALATED':
        escalate(db,user,task,comments)
    elif decision in {'REJECTED','REQUEST_CHANGES'}:
        target=TaskStatus.REJECTED if decision=='REJECTED' else TaskStatus.CHANGES_REQUESTED
        transition(db,user,task,target)
    else:
        if task.status==TaskStatus.APPROVED:
            transition(db,user,task,TaskStatus.PENDING_REVIEW)
        gate=evaluate(db,user,task)
        if gate.eligible:
            transition(db,user,task,TaskStatus.APPROVED)
    db.flush()
    return row
