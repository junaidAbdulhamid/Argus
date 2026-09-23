"""Deterministic, additive Phase 2 showcase. Existing Phase 1 data is preserved."""

import os
from datetime import timedelta
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models.entities import (
    User,
    Role,
    Project,
    TaskStatus,
    AnnotationAssignment,
    AssignmentStatus,
    Annotation,
    now,
)
from app.models.quality import AnnotationSchema, GoldReference, PreferencePair
from app.models.datasets import Dataset
from app.schemas.requests import TaskCreate, RunCreate
from app.schemas.quality import SchemaInput, QualityRules
from app.schemas.datasets import VersionInput, ExportInput
from app.services.annotation_schema import create_schema
from app.services.ingestion import ingest, ingest_run
from app.services.workflow import transition, complete, audit
from app.services.review import submit_review
from app.services.datasets import create_example, create_version, finalize
from app.services.export_jobs import request_export
from app.auth.security import passwords
from app.seed import SCENARIOS


FIELDS = [
    {
        "key": "grounded",
        "label": "Grounded in evidence",
        "field_type": "boolean",
        "required": True,
        "description": "Does the final answer stay within the available evidence?",
    },
    {
        "key": "tool_correctness",
        "label": "Tool use quality",
        "field_type": "integer_rating",
        "required": True,
        "constraints": {"minimum": 1, "maximum": 5},
    },
    {
        "key": "confidence",
        "label": "Confidence",
        "field_type": "continuous_score",
        "required": True,
        "constraints": {"minimum": 0, "maximum": 1},
    },
    {
        "key": "failure_modes",
        "label": "Failure modes",
        "field_type": "multi_select",
        "options": ["unsupported_claim", "tool_error", "unsafe_action", "missing_citation"],
    },
    {
        "key": "recommendation",
        "label": "Training recommendation",
        "field_type": "single_select",
        "required": True,
        "options": ["include", "revise", "exclude"],
    },
    {
        "key": "rationale",
        "label": "Evidence rationale",
        "field_type": "text",
        "required": True,
        "constraints": {"min_length": 10, "max_length": 2000},
    },
    {
        "key": "evidence",
        "label": "Structured evidence",
        "field_type": "json",
        "description": "Step references or other structured context",
    },
]


def values(good=True):
    return {
        "grounded": good,
        "tool_correctness": 5 if good else 2,
        "confidence": 0.95 if good else 0.45,
        "failure_modes": [] if good else ["missing_citation"],
        "recommendation": "include" if good else "revise",
        "rationale": "The final answer follows the tool evidence and preserves relevant limitations."
        if good
        else "The response omits a source needed to verify its conclusion.",
        "evidence": {"reviewed_steps": [2, 3, 5], "source_verified": good},
    }


def seed_phase2():
    with SessionLocal() as db:
        admin = db.scalar(select(User).where(User.email == "admin@argus.dev"))
        if not admin:
            print("Phase 2 demo requires the Phase 1 demo workspace")
            return
        if db.scalar(
            select(Project).where(
                Project.organization_id == admin.organization_id, Project.name == "Agent quality · multi-review"
            )
        ):
            print("Phase 2 demo already exists; seed skipped")
            return
        password = os.environ.get("SEED_PASSWORD")
        if not password or len(password) < 12:
            raise RuntimeError("Set SEED_PASSWORD to seed demo accounts")
        reviewer = db.scalar(select(User).where(User.email == "reviewer@argus.dev"))
        workers = [
            db.scalar(select(User).where(User.email == email))
            for email in ["annotator@argus.dev", "annotator2@argus.dev"]
        ]
        third = db.scalar(select(User).where(User.email == "annotator3@argus.dev"))
        if not third:
            third = User(
                organization_id=admin.organization_id,
                email="annotator3@argus.dev",
                full_name="Riley Patel",
                role=Role.ANNOTATOR,
                password_hash=passwords.hash(password),
            )
            db.add(third)
            db.flush()
        workers.append(third)
        project = Project(
            organization_id=admin.organization_id,
            name="Agent quality · multi-review",
            description="Three independent perspectives, calibrated reference work, explicit adjudication, and reproducible datasets.",
            quality_rules=QualityRules(
                required_annotations=3,
                minimum_agreement=0.65,
                minimum_score=3,
                maximum_variance=1.5,
                minimum_gold_accuracy=0.6,
                minimum_gold_attempts=2,
                gold_every=4,
            ).model_dump(),
        )
        db.add(project)
        db.flush()
        audit(db, admin, "PROJECT_CREATED", project_id=project.id)
        created_schema = create_schema(db, admin, project, SchemaInput(name="Agent reliability rubric", fields=FIELDS))
        schema = db.get(AnnotationSchema, created_schema["id"])
        examples = []
        for i in range(18):
            _, kind, prompt, tool, args, result, answer = SCENARIOS[i % len(SCENARIOS)]
            t = ingest(
                db,
                admin,
                project,
                TaskCreate(
                    external_id=f"EVAL-{2101 + i}",
                    task_type=kind,
                    priority=90 if i < 3 else 70,
                    input_payload={"prompt": prompt},
                    metadata={
                        "source": "phase2-demo",
                        "evaluation_set": "reliability-v2",
                        "difficulty": ["standard", "complex"][i % 2],
                    },
                ),
            )
            run = ingest_run(
                db,
                admin,
                t,
                RunCreate(
                    model_name="argus-research-agent",
                    model_version="v2.0",
                    steps=[
                        {"sequence_number": 0, "step_type": "user_message", "content": prompt},
                        {
                            "sequence_number": 1,
                            "step_type": "assistant_message",
                            "content": "I will inspect the evidence and keep the response bounded to what the tools support.",
                        },
                        {"sequence_number": 2, "step_type": "tool_call", "tool_name": tool, "tool_input": args},
                        {
                            "sequence_number": 3,
                            "step_type": "tool_result",
                            "tool_name": tool,
                            "tool_output": result,
                            "metadata": {"latency_ms": 182},
                        },
                        {
                            "sequence_number": 4,
                            "step_type": "observation",
                            "content": "The evidence supports a limited conclusion; uncertainties should remain explicit.",
                        },
                        {"sequence_number": 5, "step_type": "final_answer", "content": answer},
                    ],
                ),
            )
            alternate = None
            if i in [3, 4]:
                alternate = ingest_run(
                    db,
                    admin,
                    t,
                    RunCreate(
                        model_name="argus-baseline-agent",
                        model_version="v1.0",
                        steps=[
                            {"sequence_number": 0, "step_type": "user_message", "content": prompt},
                            {
                                "sequence_number": 1,
                                "step_type": "final_answer",
                                "content": "The task is completed successfully. No additional evidence is necessary.",
                            },
                        ],
                    ),
                )
            t.schema_id = schema.id
            t.required_annotations = 3
            if i < 3:
                db.add(
                    GoldReference(
                        task_id=t.id,
                        expected={"label": "SUCCESS", "score": 5, "values": values()},
                        tolerance=0.1,
                        created_by=admin.id,
                    )
                )
                db.flush()
            if i == 17:
                continue
            transition(db, admin, t, TaskStatus.QUEUED)
            audit(db, admin, "TASK_QUEUED", t)
            if i >= 14:
                continue
            for n, worker in enumerate(workers):
                if t.status == TaskStatus.QUEUED:
                    transition(db, worker, t, TaskStatus.ASSIGNED)
                assignment = AnnotationAssignment(
                    task_id=t.id,
                    annotator_id=worker.id,
                    round=1,
                    status=AssignmentStatus.STARTED,
                    started_at=now() - timedelta(minutes=8 + n),
                )
                db.add(assignment)
                db.flush()
                good = not ((i == 2 and n == 2) or (i in [8, 9] and n == 2))
                annotation = Annotation(
                    task_id=t.id,
                    annotator_id=worker.id,
                    assignment_id=assignment.id,
                    label="SUCCESS" if good else "PARTIAL",
                    score=5 if good else 3,
                    feedback="Evidence and tool behavior independently checked."
                    if good
                    else "Please add the missing citation before training.",
                    values=values(good),
                    structured_payload={"calibration": "rubric-v1"},
                )
                db.add(annotation)
                db.flush()
                audit(db, worker, "ANNOTATION_SAVED", t, payload={"annotation_id": annotation.id})
                complete(db, worker, assignment.id)
                historical = now() - timedelta(days=(i + n) % 7, hours=n)
                assignment.assigned_at = historical - timedelta(minutes=12 + n)
                assignment.started_at = historical - timedelta(minutes=8 + n)
                assignment.completed_at = historical
            if i < 3:
                continue
            if alternate:
                db.add(
                    PreferencePair(
                        task_id=t.id,
                        round=1,
                        chosen_run_id=run.id,
                        rejected_run_id=alternate.id,
                        reviewer_id=reviewer.id,
                        rationale="The chosen response is grounded in tool evidence; the baseline asserts success without support.",
                    )
                )
                db.flush()
            if i in [8, 9]:
                continue
            if i == 10:
                submit_review(
                    db,
                    reviewer,
                    t,
                    "REQUEST_CHANGES",
                    "Expand the explanation of uncertainty before accepting this example.",
                )
                continue
            if i == 11:
                submit_review(
                    db,
                    reviewer,
                    t,
                    "REJECTED",
                    "The trace is not representative of the intended training distribution.",
                )
                continue
            if i in [12, 13]:
                continue
            submit_review(
                db,
                reviewer,
                t,
                "APPROVED",
                "All three independent annotations and the source trace were checked. The configured gates are satisfied.",
            )
            examples.append(create_example(db, admin, t))
        dataset = Dataset(
            organization_id=admin.organization_id,
            name="argus-agent-reliability",
            description="A reviewed reliability cohort with three independent annotations per task, reference calibration, and complete evidence lineage.",
            created_by=admin.id,
        )
        db.add(dataset)
        db.flush()
        audit(db, admin, "DATASET_CREATED", payload={"dataset_id": dataset.id, "name": dataset.name})
        version = create_version(
            db,
            admin,
            dataset,
            VersionInput(
                example_ids=[e.id for e in examples],
                metadata={"purpose": "reliability fine-tuning", "curation": "three independent annotators"},
            ),
        )
        finalize(db, admin, version)
        pair_version = create_version(
            db,
            admin,
            dataset,
            VersionInput(
                example_ids=[e.id for e in examples if e.snapshot["preference_pair"]],
                metadata={"purpose": "human preference learning"},
            ),
        )
        finalize(db, admin, pair_version)
        db.commit()
        request_export(db, admin, version, ExportInput(format="trajectory"))
        request_export(db, admin, pair_version, ExportInput(format="dpo"))
        print(
            "Seeded Phase 2: 18 tasks, 3 annotators, schemas, gold history, reviews, escalations, 2 dataset versions, and export jobs"
        )


if __name__ == "__main__":
    seed_phase2()
