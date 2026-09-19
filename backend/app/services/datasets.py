import hashlib
import json
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select, func
from app.models.entities import Task, Project, AgentRun, TrajectoryStep, User
from app.models.quality import Review, AnnotationSchema, PreferencePair
from app.models.datasets import TrainingExample, Dataset, DatasetVersion, DatasetExample
from app.repositories.platform import serialize
from app.services.quality_gate import evaluate
from app.services.annotation_schema import schema_detail
from app.services.consensus import completed_annotations
from app.services.workflow import audit
from app.models.entities import now


def canonical(value):
    return json.dumps(jsonable_encoder(value),sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)


def checksum(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def get_dataset(db,user,dataset_id,lock=False):
    q=select(Dataset).where(Dataset.id==dataset_id,Dataset.organization_id==user.organization_id)
    d=db.scalar(q.with_for_update() if lock else q)
    if not d:raise HTTPException(404,'Dataset not found')
    return d


def get_version(db,user,version_id,lock=False):
    q=select(DatasetVersion).join(Dataset).where(DatasetVersion.id==version_id,Dataset.organization_id==user.organization_id)
    v=db.scalar(q.with_for_update(of=DatasetVersion) if lock else q)
    if not v:raise HTTPException(404,'Dataset version not found')
    return v


def snapshot(db,task,gate):
    runs=[]
    for r in db.scalars(select(AgentRun).where(AgentRun.task_id==task.id).order_by(AgentRun.started_at,AgentRun.id)):
        runs.append({**serialize(r),'steps':[serialize(s) for s in db.scalars(select(TrajectoryStep).where(TrajectoryStep.agent_run_id==r.id).order_by(TrajectoryStep.sequence_number))]})
    annotations=completed_annotations(db,task)
    reviews=db.scalars(select(Review).where(Review.id.in_(gate.evidence['review_ids']))).all()
    pair=db.scalar(select(PreferencePair).where(PreferencePair.task_id==task.id,PreferencePair.round==task.annotation_round))
    return jsonable_encoder({'schema_version':'argus.training.v1','task':serialize(task),'project':{'id':task.project_id,'name':db.get(Project,task.project_id).name},'runs':runs,'annotations':[serialize(a) for a in annotations],'reviews':[serialize(r) for r in reviews],'quality_gate':serialize(gate),'annotation_schema':schema_detail(db,db.get(AnnotationSchema,task.schema_id)) if task.schema_id else None,'preference_pair':serialize(pair) if pair else None})


def create_example(db,user,task):
    gate=evaluate(db,user,task)
    if not gate.eligible:
        # Persist failed gate evaluations as evidence even though the command is rejected.
        db.commit()
        raise HTTPException(409,{'message':'Task failed quality gates','reasons':gate.reasons,'gate_result_id':gate.id})
    content=snapshot(db,task,gate)
    # Repeated creation reuses unchanged evidence while keeping evaluations auditable.
    fingerprint=checksum({k:v for k,v in content.items() if k!='quality_gate'})
    existing=db.scalar(select(TrainingExample).where(TrainingExample.task_id==task.id,TrainingExample.round==task.annotation_round,TrainingExample.checksum==fingerprint))
    if existing:return existing
    e=TrainingExample(organization_id=user.organization_id,task_id=task.id,round=task.annotation_round,gate_result_id=gate.id,snapshot=content,checksum=fingerprint,created_by=user.id)
    db.add(e)
    db.flush()
    audit(db,user,'TRAINING_EXAMPLE_CREATED',task,payload={'example_id':e.id,'gate_result_id':gate.id})
    return e


def matches_filter(example,filters):
    s=example.snapshot;t=s['task'];annotations=s['annotations']
    if filters.project_id and t['project_id']!=filters.project_id:return False
    if filters.task_type and t['task_type']!=filters.task_type:return False
    if filters.model and not any(filters.model.lower() in r['model_name'].lower() for r in s['runs']):return False
    if annotations and min(a['score'] for a in annotations)<filters.minimum_score:return False
    if filters.annotation_label and not any(a['label']==filters.annotation_label for a in annotations):return False
    if filters.reviewer_decision and not any(r['decision']==filters.reviewer_decision for r in s['reviews']):return False
    if any(t['metadata'].get(k)!=v for k,v in filters.metadata.items()):return False
    from datetime import datetime
    created=datetime.fromisoformat(t['created_at'])
    if created.tzinfo is None:created=created.replace(tzinfo=now().tzinfo)
    if filters.date_from and created<filters.date_from:return False
    if filters.date_to and created>filters.date_to:return False
    return True


def preview(db,user,filters):
    rows=db.scalars(select(TrainingExample).where(TrainingExample.organization_id==user.organization_id).order_by(TrainingExample.created_at.desc())).all()
    result=[]
    seen=set()
    for row in rows:
        if row.task_id in seen or not matches_filter(row,filters):continue
        task=db.scalar(select(Task).where(Task.id==row.task_id).with_for_update())
        gate=evaluate(db,user,task)
        if gate.eligible and row.round==task.annotation_round and sorted(gate.evidence['annotation_ids'])==sorted(a['id'] for a in row.snapshot['annotations']):
            result.append({'id':row.id,'task_id':row.task_id,'external_id':row.snapshot['task']['external_id'],'project_id':row.snapshot['task']['project_id'],'task_type':row.snapshot['task']['task_type'],'score':gate.evidence['consensus']['scores']['mean'],'models':[r['model_name'] for r in row.snapshot['runs']],'created_at':row.created_at,'labels':[a['label'] for a in row.snapshot['annotations']]})
            seen.add(row.task_id)
    return result


def create_version(db,user,dataset,data):
    version=(db.scalar(select(func.max(DatasetVersion.version)).where(DatasetVersion.dataset_id==dataset.id)) or 0)+1
    examples=db.scalars(select(TrainingExample).where(TrainingExample.id.in_(data.example_ids),TrainingExample.organization_id==user.organization_id)).all()
    if len(examples)!=len(data.example_ids):raise HTTPException(404,'One or more examples were not found')
    if len({e.task_id for e in examples})!=len(examples):raise HTTPException(422,'Select at most one example per originating task')
    if any(not matches_filter(e,data.filters) for e in examples):raise HTTPException(422,'Selected examples do not match the recorded filters')
    row=DatasetVersion(dataset_id=dataset.id,version=version,created_by=user.id,filters=data.filters.model_dump(mode='json'),metadata_=data.metadata,example_count=len(examples))
    db.add(row);db.flush()
    for position,example_id in enumerate(data.example_ids):
        db.add(DatasetExample(version_id=row.id,example_id=example_id,position=position))
    audit(db,user,'DATASET_VERSION_CREATED',payload={'dataset_id':dataset.id,'version_id':row.id,'example_count':len(examples)})
    db.flush()
    return row


def finalized_content(db,version):
    rows=db.execute(select(DatasetExample,TrainingExample).join(TrainingExample).where(DatasetExample.version_id==version.id).order_by(DatasetExample.position)).all()
    return rows


def finalize(db,user,version):
    if version.status!='DRAFT':raise HTTPException(409,'Finalized versions are immutable')
    rows=finalized_content(db,version)
    if not rows:raise HTTPException(409,'Cannot finalize an empty version')
    failures=[]
    # Deterministic task lock order avoids competing builders deadlocking.
    tasks={t.id:t for t in db.scalars(select(Task).where(Task.id.in_([e.task_id for _,e in rows])).order_by(Task.id).with_for_update())}
    # Lock project policies too: gate configuration cannot change during finalization.
    list(db.scalars(select(Project).where(Project.id.in_({t.project_id for t in tasks.values()})).order_by(Project.id).with_for_update()))
    gates=[]
    for membership,e in rows:
        task=tasks[e.task_id]
        gate=evaluate(db,user,task)
        if not gate.eligible or task.annotation_round!=e.round or sorted(gate.evidence['annotation_ids'])!=sorted(a['id'] for a in e.snapshot['annotations']):
            failures.append({'example_id':e.id,'reasons':gate.reasons or ['source_round_changed']})
        gates.append((membership,gate))
    if failures:
        db.commit()
        raise HTTPException(409,{'message':'Finalization blocked by quality gates','failures':failures})
    for membership,gate in gates:membership.gate_result_id=gate.id
    version.checksum=checksum({'schema_version':version.schema_version,'filters':version.filters,'metadata':version.metadata_,'examples':[{'id':e.id,'snapshot':e.snapshot,'finalization_gate':serialize(gate)} for (_,e),(_,gate) in zip(rows,gates)]})
    version.status='FINALIZED';version.finalized_at=now();version.example_count=len(rows)
    audit(db,user,'DATASET_FINALIZED',payload={'dataset_id':version.dataset_id,'version_id':version.id,'checksum':version.checksum,'example_count':len(rows)})
    db.flush()
    return version
