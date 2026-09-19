"""Agreement describes consistency, not correctness. Undefined kappas stay null."""
import json
from collections import Counter
from statistics import mean, median, pstdev, pvariance
from sqlalchemy import select
from app.models.entities import Annotation, AnnotationAssignment, AssignmentStatus
from app.models.quality import ConsensusResult, AnnotationField


def completed_annotations(db,task):
    return db.scalars(select(Annotation).join(AnnotationAssignment).where(Annotation.task_id==task.id,AnnotationAssignment.round==task.annotation_round,AnnotationAssignment.status==AssignmentStatus.COMPLETED).order_by(Annotation.created_at,Annotation.id)).all()


def categorical(values):
    n=len(values)
    counts=Counter(json.dumps(v,sort_keys=True) for v in values)
    agreement=sum(c*(c-1) for c in counts.values())/(n*(n-1)) if n>1 else None
    return {"count":n,"raw_agreement":agreement,"disagreement_rate":1-agreement if agreement is not None else None,"counts":dict(counts),"conflicting":len(counts)>1}


def numeric(values):
    if not values:
        return {"count":0,"mean":None,"median":None,"standard_deviation":None,"variance":None}
    return {"count":len(values),"mean":mean(values),"median":median(values),"standard_deviation":pstdev(values),"variance":pvariance(values)}


def cohen_kappa(pairs):
    if len(pairs)<2:
        return None
    left=Counter(a for a,_ in pairs)
    right=Counter(b for _,b in pairs)
    n=len(pairs)
    observed=sum(a==b for a,b in pairs)/n
    expected=sum(left[k]*right[k] for k in left.keys()|right.keys())/(n*n)
    return (observed-expected)/(1-expected) if expected<1 else None


def fleiss_kappa(rows):
    if len(rows)<2 or len({len(r) for r in rows})!=1 or len(rows[0])<2:
        return None
    n=len(rows[0])
    observed=mean(sum(c*(c-1) for c in Counter(r).values())/(n*(n-1)) for r in rows)
    frequencies=Counter(v for r in rows for v in r)
    expected=sum((count/(len(rows)*n))**2 for count in frequencies.values())
    return (observed-expected)/(1-expected) if expected<1 else None


def calculate(db,task,store=True):
    annotations=completed_annotations(db,task)
    labels=categorical([a.label for a in annotations])
    scores=numeric([a.score for a in annotations])
    fields={}
    definitions=db.scalars(select(AnnotationField).where(AnnotationField.schema_id==task.schema_id)).all() if task.schema_id else []
    for field in definitions:
        values=[a.values[field.key] for a in annotations if a.values.get(field.key) is not None]
        if field.field_type in {"boolean","single_select","multi_select"}:
            fields[field.key]={"kind":"categorical",**categorical([sorted(v) if isinstance(v,list) else v for v in values])}
        elif field.field_type in {"integer_rating","continuous_score"}:
            fields[field.key]={"kind":"numeric",**numeric(values)}
        else:
            fields[field.key]={"kind":"unscored","count":len(values),"note":"Text/structured values require human interpretation"}
    summary={"completed":len(annotations),"required":task.required_annotations,"labels":labels,"scores":scores,"fields":fields,"conflicting":labels['conflicting'] or any(v.get('conflicting',False) for v in fields.values()),"cohen_kappa":None,"fleiss_kappa":None,"kappa_note":"Chance-corrected kappa needs a cohort of multiple tasks; see project analytics.","interpretation":"Agreement is consistency, not evidence of correctness."}
    if store:
        db.add(ConsensusResult(task_id=task.id,round=task.annotation_round,annotation_ids=[a.id for a in annotations],metrics=summary))
        db.flush()
    return summary
