from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from app.auth.security import current_user, roles
from app.db.session import get_db
from app.models.entities import Project, Task, TaskStatus, Role, Annotation, AnnotationAssignment, AssignmentStatus, User
from app.models.quality import AnnotationSchema, Review, Escalation, GoldReference, GoldAttempt
from app.repositories.platform import project, task, serialize
from app.schemas.quality import QualityRules, SchemaInput, ReviewCreate, EscalationInput, EscalationResolution, GoldInput
from app.services.annotation_schema import create_schema, schema_detail, active_schema, validate_values
from app.services.quality_gate import evaluate, policy
from app.services.consensus import calculate
from app.services.review import submit_review, escalate, resolve
from app.services.workflow import audit

router=APIRouter(tags=['Quality control'])
reviewer=roles(Role.ADMIN,Role.REVIEWER)
admin=roles(Role.ADMIN)


@router.get('/projects/{project_id}/quality-rules')
def get_rules(project_id:str,user=Depends(current_user),db=Depends(get_db)):
    return policy(project(db,user,project_id))


@router.put('/projects/{project_id}/quality-rules')
def set_rules(project_id:str,data:QualityRules,user=Depends(admin),db=Depends(get_db)):
    p=project(db,user,project_id,lock=True)
    p.quality_rules=data.model_dump()
    audit(db,user,'QUALITY_RULES_UPDATED',project_id=p.id,payload=p.quality_rules)
    return p.quality_rules


@router.get('/projects/{project_id}/annotation-schemas')
def schemas(project_id:str,user=Depends(current_user),db=Depends(get_db)):
    project(db,user,project_id)
    return [schema_detail(db,s) for s in db.scalars(select(AnnotationSchema).where(AnnotationSchema.project_id==project_id).order_by(AnnotationSchema.version.desc()))]


@router.post('/projects/{project_id}/annotation-schemas',status_code=201)
def schema_create(project_id:str,data:SchemaInput,user=Depends(admin),db=Depends(get_db)):
    return create_schema(db,user,project(db,user,project_id,lock=True),data)


@router.get('/review/queue')
def review_queue(project_id:str|None=None,status:str|None=None,user=Depends(reviewer),db=Depends(get_db)):
    q=select(Task).join(Project).where(Project.organization_id==user.organization_id,Task.status.in_([TaskStatus.PENDING_REVIEW,TaskStatus.ESCALATED,TaskStatus.CHANGES_REQUESTED]))
    if project_id:q=q.where(Task.project_id==project_id)
    if status:q=q.where(Task.status==status)
    return [{**serialize(t),"consensus":calculate(db,t,store=False),"project_name":db.get(Project,t.project_id).name} for t in db.scalars(q.order_by(Task.updated_at).limit(200))]


@router.get('/tasks/{task_id}/quality')
def task_quality(task_id:str,user=Depends(reviewer),db=Depends(get_db)):
    t=task(db,user,task_id)
    return {"consensus":calculate(db,t),"policy":policy(db.get(Project,t.project_id)),"schema":schema_detail(db,db.get(AnnotationSchema,t.schema_id)) if t.schema_id else None,"reviews":[{**serialize(r),"reviewer":db.get(User,r.reviewer_id).full_name} for r in db.scalars(select(Review).where(Review.task_id==t.id).order_by(Review.created_at.desc()))],"escalations":[serialize(e) for e in db.scalars(select(Escalation).where(Escalation.task_id==t.id).order_by(Escalation.created_at.desc()))]}


@router.post('/tasks/{task_id}/quality-gate')
def gate(task_id:str,user=Depends(reviewer),db=Depends(get_db)):
    return serialize(evaluate(db,user,task(db,user,task_id,lock=True)))


@router.post('/tasks/{task_id}/reviews',status_code=201)
def review(task_id:str,data:ReviewCreate,user=Depends(reviewer),db=Depends(get_db)):
    return serialize(submit_review(db,user,task(db,user,task_id,lock=True),data.decision,data.comments,data.metadata))


@router.post('/tasks/{task_id}/escalations',status_code=201)
def escalation(task_id:str,data:EscalationInput,user=Depends(current_user),db=Depends(get_db)):
    return serialize(escalate(db,user,task(db,user,task_id,lock=True),data.reason,'ANNOTATOR' if user.role==Role.ANNOTATOR else 'REVIEWER'))


@router.get('/escalations')
def inbox(project_id:str|None=None,status:str=Query('OPEN',pattern='^(OPEN|RESOLVED|DISMISSED)$'),user=Depends(reviewer),db=Depends(get_db)):
    q=select(Escalation).join(Task).join(Project).where(Project.organization_id==user.organization_id,Escalation.status==status)
    if project_id:q=q.where(Task.project_id==project_id)
    return [serialize(e) for e in db.scalars(q.order_by(Escalation.created_at.desc()).limit(200))]


@router.post('/escalations/{escalation_id}/resolve')
def resolution(escalation_id:str,data:EscalationResolution,user=Depends(reviewer),db=Depends(get_db)):
    e=db.scalar(select(Escalation).join(Task).join(Project).where(Escalation.id==escalation_id,Project.organization_id==user.organization_id))
    if not e:raise HTTPException(404,'Escalation not found')
    t=task(db,user,e.task_id,lock=True)
    db.refresh(e,with_for_update=True)
    return serialize(resolve(db,user,t,e,data))


@router.post('/tasks/{task_id}/gold',status_code=201)
def gold(task_id:str,data:GoldInput,user=Depends(admin),db=Depends(get_db)):
    t=task(db,user,task_id,lock=True)
    if t.status!=TaskStatus.INGESTED or db.scalar(select(GoldReference.id).where(GoldReference.task_id==t.id)):
        raise HTTPException(409,'Designate a gold reference once, before queueing')
    if not data.expected or set(data.expected)-{'label','score','values'}:
        raise HTTPException(422,'Expected answers must use label, score, and/or values')
    if 'label' in data.expected and data.expected['label'] not in {'SUCCESS','PARTIAL','FAILURE','UNSAFE'}:
        raise HTTPException(422,'Invalid expected label')
    if 'score' in data.expected and (type(data.expected['score']) not in (int,float) or not 1<=data.expected['score']<=5):
        raise HTTPException(422,'Expected score must be between 1 and 5')
    schema=active_schema(db,t.project_id)
    t.schema_id=schema.id if schema else None
    if 'values' in data.expected:
        if not isinstance(data.expected['values'],dict) or not data.expected['values']:
            raise HTTPException(422,'Expected values must be a nonempty object')
        validate_values(db,t,data.expected['values'])
    reference=GoldReference(task_id=t.id,expected=data.expected,tolerance=data.tolerance,created_by=user.id)
    db.add(reference)
    db.flush()
    audit(db,user,'GOLD_REFERENCE_CREATED',t,payload={"reference_id":reference.id})
    return serialize(reference)


@router.get('/gold-tasks')
def gold_list(user=Depends(admin),db=Depends(get_db)):
    return [{**serialize(g),"external_id":t.external_id,"project_id":t.project_id} for g,t in db.execute(select(GoldReference,Task).join(Task).join(Project).where(Project.organization_id==user.organization_id))]
