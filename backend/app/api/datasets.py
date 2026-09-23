from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from app.auth.security import roles
from app.db.session import get_db
from app.models.entities import Role, AgentRun, TrajectoryStep, Annotation
from app.models.quality import PreferencePair, QualityGateResult
from app.models.datasets import Dataset, DatasetVersion, DatasetExample, TrainingExample, ExportJob
from app.schemas.datasets import DatasetInput, VersionInput, ExampleFilters, ExportInput, PreferenceInput
from app.repositories.platform import task, serialize
from app.services import datasets as service
from app.services.export_jobs import request_export, artifact_directory
from app.services.export_formats import final_response
from app.services.workflow import audit

router = APIRouter(tags=["Datasets and exports"])
admin = roles(Role.ADMIN)
reader = roles(Role.ADMIN, Role.REVIEWER)


@router.post("/tasks/{task_id}/preference", status_code=201)
def preference(task_id: str, data: PreferenceInput, user=Depends(reader), db=Depends(get_db)):
    t = task(db, user, task_id, lock=True)
    if db.scalar(select(Annotation.id).where(Annotation.task_id == t.id, Annotation.annotator_id == user.id)):
        raise HTTPException(403, "Preference pairs require an independent reviewer")
    if data.chosen_run_id == data.rejected_run_id:
        raise HTTPException(422, "Choose two distinct agent runs")
    if db.scalar(
        select(PreferencePair.id).where(PreferencePair.task_id == t.id, PreferencePair.round == t.annotation_round)
    ):
        raise HTTPException(409, "A preference pair already exists for this round")
    responses = []
    for run_id in [data.chosen_run_id, data.rejected_run_id]:
        run = db.scalar(select(AgentRun).where(AgentRun.id == run_id, AgentRun.task_id == t.id))
        if not run:
            raise HTTPException(422, "Both runs must belong to this task")
        steps = [
            serialize(s)
            for s in db.scalars(
                select(TrajectoryStep)
                .where(TrajectoryStep.agent_run_id == run_id)
                .order_by(TrajectoryStep.sequence_number)
            )
        ]
        try:
            responses.append(final_response({"steps": steps}))
        except ValueError as exc:
            raise HTTPException(422, str(exc))
    if responses[0] == responses[1]:
        raise HTTPException(422, "Preference responses must differ")
    row = PreferencePair(task_id=t.id, round=t.annotation_round, reviewer_id=user.id, **data.model_dump())
    db.add(row)
    db.flush()
    audit(
        db,
        user,
        "PREFERENCE_PAIR_CREATED",
        t,
        payload={"pair_id": row.id, "chosen_run_id": row.chosen_run_id, "rejected_run_id": row.rejected_run_id},
    )
    return serialize(row)


@router.post("/tasks/{task_id}/training-examples", status_code=201)
def example(task_id: str, user=Depends(admin), db=Depends(get_db)):
    return serialize(service.create_example(db, user, task(db, user, task_id, lock=True)))


@router.post("/training-examples/preview")
def preview(data: ExampleFilters, user=Depends(admin), db=Depends(get_db)):
    items = service.preview(db, user, data)
    return {"items": items, "eligible_count": len(items)}


@router.get("/training-examples/{example_id}/lineage")
def lineage(example_id: str, user=Depends(reader), db=Depends(get_db)):
    e = db.scalar(
        select(TrainingExample).where(
            TrainingExample.id == example_id, TrainingExample.organization_id == user.organization_id
        )
    )
    if not e:
        raise HTTPException(404, "Training example not found")
    versions = [
        {
            "version": serialize(v),
            "finalization_gate": serialize(db.get(QualityGateResult, m.gate_result_id)) if m.gate_result_id else None,
        }
        for m, v in db.execute(
            select(DatasetExample, DatasetVersion).join(DatasetVersion).where(DatasetExample.example_id == e.id)
        )
    ]
    return {"example": serialize(e), "versions": versions}


@router.get("/datasets")
def datasets(user=Depends(reader), db=Depends(get_db)):
    result = []
    for d in db.scalars(
        select(Dataset).where(Dataset.organization_id == user.organization_id).order_by(Dataset.created_at.desc())
    ):
        versions = db.scalars(
            select(DatasetVersion).where(DatasetVersion.dataset_id == d.id).order_by(DatasetVersion.version.desc())
        ).all()
        result.append({**serialize(d), "versions": [serialize(v) for v in versions]})
    return result


@router.post("/datasets", status_code=201)
def create(data: DatasetInput, user=Depends(admin), db=Depends(get_db)):
    d = Dataset(organization_id=user.organization_id, created_by=user.id, **data.model_dump())
    db.add(d)
    db.flush()
    audit(db, user, "DATASET_CREATED", payload={"dataset_id": d.id, "name": d.name})
    return serialize(d)


@router.get("/datasets/{dataset_id}")
def detail(dataset_id: str, user=Depends(reader), db=Depends(get_db)):
    d = service.get_dataset(db, user, dataset_id)
    versions = db.scalars(
        select(DatasetVersion).where(DatasetVersion.dataset_id == d.id).order_by(DatasetVersion.version.desc())
    ).all()
    examples = (
        db.scalars(
            select(TrainingExample).join(DatasetExample).join(DatasetVersion).where(DatasetVersion.dataset_id == d.id)
        )
        .unique()
        .all()
    )
    distribution = {str(n): 0 for n in range(1, 6)}
    for e in examples:
        for a in e.snapshot["annotations"]:
            distribution[str(a["score"])] += 1
    return {
        **serialize(d),
        "versions": [serialize(v) for v in versions],
        "quality_distribution": distribution,
        "source_projects": list({e.snapshot["project"]["name"] for e in examples}),
    }


@router.post("/datasets/{dataset_id}/versions", status_code=201)
def version_create(dataset_id: str, data: VersionInput, user=Depends(admin), db=Depends(get_db)):
    return serialize(service.create_version(db, user, service.get_dataset(db, user, dataset_id, lock=True), data))


@router.get("/dataset-versions/{version_id}")
def version_detail(version_id: str, user=Depends(reader), db=Depends(get_db)):
    version = service.get_version(db, user, version_id)
    examples = [
        {
            "membership_id": m.id,
            "id": e.id,
            "task_id": e.task_id,
            "external_id": e.snapshot["task"]["external_id"],
            "task_type": e.snapshot["task"]["task_type"],
            "checksum": e.checksum,
            "gate_result_id": m.gate_result_id,
        }
        for m, e in service.finalized_content(db, version)
    ]
    return {**serialize(version), "examples": examples}


@router.post("/dataset-versions/{version_id}/finalize")
def finalize(version_id: str, user=Depends(admin), db=Depends(get_db)):
    return serialize(service.finalize(db, user, service.get_version(db, user, version_id, lock=True)))


@router.post("/dataset-versions/{version_id}/exports", status_code=202)
def export(version_id: str, data: ExportInput, user=Depends(admin), db=Depends(get_db)):
    return serialize(request_export(db, user, service.get_version(db, user, version_id, lock=True), data))


@router.get("/exports")
def exports(version_id: str | None = None, user=Depends(reader), db=Depends(get_db)):
    q = select(ExportJob).join(DatasetVersion).join(Dataset).where(Dataset.organization_id == user.organization_id)
    if version_id:
        q = q.where(ExportJob.version_id == version_id)
    return [serialize(j) for j in db.scalars(q.order_by(ExportJob.created_at.desc()).limit(200))]


@router.get("/exports/{job_id}/files/{artifact}")
def download(job_id: str, artifact: str, user=Depends(reader), db=Depends(get_db)):
    job = db.scalar(
        select(ExportJob)
        .join(DatasetVersion)
        .join(Dataset)
        .where(ExportJob.id == job_id, Dataset.organization_id == user.organization_id)
    )
    if not job:
        raise HTTPException(404, "Export job not found")
    if job.status != "COMPLETED":
        raise HTTPException(409, "Export is not complete")
    filenames = {
        "dataset": f"dataset.{job.container}",
        "manifest": "manifest.json",
        "schema": "schema.json",
        "provenance": "provenance.json",
    }
    if artifact not in filenames:
        raise HTTPException(404, "Artifact not found")
    file = artifact_directory(job.id) / filenames[artifact]
    if not file.is_file():
        raise HTTPException(404, "Artifact file is unavailable")
    return FileResponse(
        file, filename=file.name, media_type="application/x-ndjson" if file.suffix == ".jsonl" else "application/json"
    )


@router.post("/training-examples/materialize")
def materialize(project_id: str | None = None, user=Depends(admin), db=Depends(get_db)):
    from app.models.entities import Project, TaskStatus, Task
    from app.services.quality_gate import evaluate

    q = (
        select(Task)
        .join(Project)
        .where(Project.organization_id == user.organization_id, Task.status == TaskStatus.APPROVED)
    )
    if project_id:
        q = q.where(Task.project_id == project_id)
    rows = db.scalars(q.order_by(Task.id).with_for_update(of=Task).limit(500)).all()
    created = []
    blocked = []
    for t in rows:
        result = evaluate(db, user, t)
        if result.eligible:
            created.append(service.create_example(db, user, t).id)
        else:
            blocked.append({"task_id": t.id, "reasons": result.reasons})
    return {"example_ids": created, "blocked": blocked, "scanned": len(rows)}
