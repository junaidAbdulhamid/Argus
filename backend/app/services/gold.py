from sqlalchemy import select
from app.models.quality import GoldReference, GoldAttempt
from app.services.workflow import audit


def grade(db,user,task,annotation):
    reference=db.scalar(select(GoldReference).where(GoldReference.task_id==task.id))
    if not reference:
        return None
    supplied={"label":annotation.label,"score":annotation.score,"values":annotation.values}
    comparisons={}
    for key,expected in reference.expected.items():
        actual=supplied.get(key)
        if key=='values':
            for field,value in expected.items():
                comparisons[f'values.{field}']=matches(actual.get(field),value,reference.tolerance)
        else:
            comparisons[key]=matches(actual,expected,reference.tolerance)
    attempt=GoldAttempt(reference_id=reference.id,annotator_id=user.id,annotation_id=annotation.id,accuracy=sum(comparisons.values())/len(comparisons),comparison=comparisons)
    db.add(attempt)
    audit(db,user,'GOLD_TASK_GRADED',task,payload={"annotation_id":annotation.id})
    db.flush()
    return attempt


def matches(actual,expected,tolerance):
    if type(actual) in (int,float) and type(expected) in (int,float):
        return abs(actual-expected)<=tolerance
    if isinstance(actual,list) and isinstance(expected,list):
        return sorted(str(x) for x in actual)==sorted(str(x) for x in expected)
    return type(actual) is type(expected) and actual==expected
