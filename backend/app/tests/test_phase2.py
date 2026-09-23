import hashlib
import json
from unittest.mock import patch
import pytest
from app.tests.conftest import create_role, queued_task
from app.services.consensus import categorical, numeric, cohen_kappa, fleiss_kappa
from app.services.export_jobs import process_next

FIELDS = [
    {"key": "grounded", "label": "Grounded in evidence", "field_type": "boolean", "required": True},
    {"key": "reason", "label": "Rationale", "field_type": "text", "required": True, "constraints": {"min_length": 3}},
    {
        "key": "confidence",
        "label": "Confidence",
        "field_type": "continuous_score",
        "constraints": {"minimum": 0, "maximum": 1},
    },
    {"key": "issues", "label": "Issues", "field_type": "multi_select", "options": ["citation", "tool", "safety"]},
    {"key": "rating", "label": "Rating", "field_type": "integer_rating", "constraints": {"minimum": 1, "maximum": 7}},
    {"key": "category", "label": "Category", "field_type": "single_select", "options": ["good", "bad"]},
    {"key": "evidence", "label": "Evidence", "field_type": "json"},
]
VALUES = {
    "grounded": True,
    "reason": "Supported by evidence",
    "confidence": 0.9,
    "issues": [],
    "rating": 6,
    "category": "good",
    "evidence": {"source": 1},
}


def schema(client, admin, project):
    r = client.post(
        f"/projects/{project['id']}/annotation-schemas",
        headers=admin,
        json={"name": "Evidence quality", "fields": FIELDS},
    )
    assert r.status_code == 201, r.text
    return r.json()


def annotate(client, headers, values=None, label="SUCCESS", score=5):
    r = client.post("/annotation/next", headers=headers)
    assert r.status_code == 200, r.text
    assignment = r.json()
    assert client.post(f"/assignments/{assignment['id']}/start", headers=headers).status_code == 200
    data = {"label": label, "score": score, "feedback": "Human checked", "values": values or {}}
    r = client.post(f"/assignments/{assignment['id']}/annotations", headers=headers, json=data)
    assert r.status_code == 201, r.text
    annotation = r.json()
    r = client.post(f"/assignments/{assignment['id']}/complete", headers=headers)
    assert r.status_code == 200, r.text
    return assignment, annotation


def approved_example(client, admin, project):
    t = queued_task(client, admin, project)
    a = create_role(client, admin, "ANNOTATOR")
    reviewer = create_role(client, admin, "REVIEWER")
    annotate(client, a)
    r = client.post(
        f"/tasks/{t['id']}/reviews",
        headers=reviewer,
        json={"decision": "APPROVED", "comments": "Independently verified"},
    )
    assert r.status_code == 201, r.text
    e = client.post(f"/tasks/{t['id']}/training-examples", headers=admin)
    assert e.status_code == 201, e.text
    return t, e.json(), reviewer


def test_dynamic_schema_types_versioning_and_blind_independence(client, admin, project):
    s = schema(client, admin, project)
    assert (
        client.put(
            f"/projects/{project['id']}/quality-rules", headers=admin, json={"required_annotations": 2}
        ).status_code
        == 200
    )
    t = queued_task(client, admin, project)
    a = create_role(client, admin, "ANNOTATOR", "a")
    b = create_role(client, admin, "ANNOTATOR", "b")
    assignment = client.post("/annotation/next", headers=a).json()
    client.post(f"/assignments/{assignment['id']}/start", headers=a)
    for values in [
        {},
        {**VALUES, "grounded": "true"},
        {**VALUES, "confidence": 2},
        {**VALUES, "rating": 1.2},
        {**VALUES, "issues": ["bad"]},
        {**VALUES, "category": "unknown"},
        {**VALUES, "evidence": "string"},
    ]:
        assert (
            client.post(
                f"/assignments/{assignment['id']}/annotations",
                headers=a,
                json={"label": "SUCCESS", "score": 5, "values": values},
            ).status_code
            == 422
        )
    assert (
        client.post(
            f"/assignments/{assignment['id']}/annotations",
            headers=a,
            json={"label": "SUCCESS", "score": 5, "values": VALUES},
        ).status_code
        == 201
    )
    client.post(f"/assignments/{assignment['id']}/complete", headers=a)
    assert client.get(f"/tasks/{t['id']}", headers=admin).json()["status"] == "ASSIGNED"
    assert client.post("/annotation/next", headers=a).status_code == 404
    assigned = client.post("/annotation/next", headers=b).json()
    hidden = client.get(f"/tasks/{t['id']}", headers=b).json()
    assert hidden["annotations"] == [] and len(hidden["assignments"]) == 1
    changed = schema(client, admin, project)
    assert changed["version"] == 2
    assert client.get(f"/annotation/assignments/{assigned['id']}", headers=b).json()["schema"]["id"] == s["id"]
    annotate(client, b, VALUES)
    assert client.get(f"/tasks/{t['id']}", headers=admin).json()["status"] == "PENDING_REVIEW"


def test_agreement_math_and_undefined_cases():
    assert categorical(["A", "A", "B"])["raw_agreement"] == pytest.approx(1 / 3)
    assert categorical(["A"])["raw_agreement"] is None
    assert numeric([1, 3, 5])["median"] == 3
    assert numeric([1, 3, 5])["variance"] == pytest.approx(8 / 3)
    assert cohen_kappa([("A", "A"), ("B", "B")]) == 1
    assert cohen_kappa([("A", "A"), ("A", "A")]) is None
    assert cohen_kappa([("A", "B"), ("B", "A")]) == -1
    assert fleiss_kappa([["A", "A", "A"], ["B", "B", "B"]]) == 1
    assert fleiss_kappa([["A", "B"]]) is None


def test_invariant_no_example_without_review_and_gate_audits(client, admin, project):
    t = queued_task(client, admin, project)
    a = create_role(client, admin, "ANNOTATOR")
    annotate(client, a)
    r = client.post(f"/tasks/{t['id']}/training-examples", headers=admin)
    assert r.status_code == 409
    assert "requires_reviewer_approval" in r.json()["error"]["message"]["reasons"]
    events = client.get(f"/tasks/{t['id']}/audit", headers=admin).json()
    assert any(e["event_type"] == "QUALITY_GATE_EVALUATED" for e in events)
    assert client.post("/datasets", headers=a, json={"name": "Forbidden"}).status_code == 403


def test_disagreement_escalation_resolution_and_revision_round(client, admin, project):
    client.put(
        f"/projects/{project['id']}/quality-rules",
        headers=admin,
        json={"required_annotations": 2, "minimum_agreement": 0.8},
    )
    t = queued_task(client, admin, project)
    a = create_role(client, admin, "ANNOTATOR", "a")
    b = create_role(client, admin, "ANNOTATOR", "b")
    reviewer = create_role(client, admin, "REVIEWER")
    annotate(client, a)
    annotate(client, b, label="FAILURE", score=1)
    assert client.get(f"/tasks/{t['id']}", headers=admin).json()["status"] == "ESCALATED"
    escalation = client.get("/escalations", headers=reviewer).json()[0]
    assert (
        client.post(
            f"/tasks/{t['id']}/reviews", headers=reviewer, json={"decision": "APPROVED", "comments": "Cannot bypass"}
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"/escalations/{escalation['id']}/resolve",
            headers=reviewer,
            json={"status": "RESOLVED", "resolution": "Needs reannotation"},
        ).status_code
        == 200
    )
    gate = client.post(f"/tasks/{t['id']}/quality-gate", headers=reviewer).json()
    assert "agreement_below_threshold" in gate["reasons"]
    client.post(
        f"/tasks/{t['id']}/reviews",
        headers=reviewer,
        json={"decision": "REQUEST_CHANGES", "comments": "Reassess evidence"},
    )
    assert client.get(f"/tasks/{t['id']}", headers=admin).json()["status"] == "CHANGES_REQUESTED"
    assert client.post(f"/tasks/{t['id']}/queue", headers=admin).json()["annotation_round"] == 2
    annotate(client, a)
    annotate(client, b)
    assert (
        client.post(
            f"/tasks/{t['id']}/reviews",
            headers=reviewer,
            json={"decision": "APPROVED", "comments": "Revisions checked"},
        ).status_code
        == 201
    )
    assert client.post(f"/tasks/{t['id']}/training-examples", headers=admin).status_code == 201


def test_gold_hidden_grading_and_threshold(client, admin, project):
    t = client.post(f"/projects/{project['id']}/tasks", headers=admin, json={"task_type": "research"}).json()
    client.post(
        f"/tasks/{t['id']}/runs",
        headers=admin,
        json={
            "model_name": "agent",
            "steps": [{"sequence_number": 0, "step_type": "final_answer", "content": "Answer"}],
        },
    )
    assert (
        client.post(
            f"/tasks/{t['id']}/gold", headers=admin, json={"expected": {"label": "SUCCESS", "score": 5}, "tolerance": 0}
        ).status_code
        == 201
    )
    client.post(f"/tasks/{t['id']}/queue", headers=admin)
    a = create_role(client, admin, "ANNOTATOR")
    b = create_role(client, admin, "ANNOTATOR", "b")
    annotate(client, a)
    annotate(client, b, label="FAILURE", score=1)
    assert client.get("/gold-tasks", headers=a).status_code == 403
    assert not any(e["event_type"].startswith("GOLD") for e in client.get(f"/tasks/{t['id']}/audit", headers=a).json())
    profiles = client.get("/quality/dashboard", headers=admin).json()["annotators"]
    assert sorted(p["gold_accuracy"] for p in profiles if p["gold_attempted"]) == [0, 1]
    assert (
        "gold_reference_excluded_from_training"
        in client.post(f"/tasks/{t['id']}/quality-gate", headers=admin).json()["reasons"]
    )


def test_dataset_finalization_lineage_and_stale_approval(client, admin, project):
    t, e, reviewer = approved_example(client, admin, project)
    d = client.post("/datasets", headers=admin, json={"name": "quality-v1"}).json()
    v = client.post(f"/datasets/{d['id']}/versions", headers=admin, json={"example_ids": [e["id"]]}).json()
    assert (
        client.post(
            f"/tasks/{t['id']}/reviews",
            headers=reviewer,
            json={"decision": "REJECTED", "comments": "New issue discovered"},
        ).status_code
        == 201
    )
    assert client.post(f"/dataset-versions/{v['id']}/finalize", headers=admin).status_code == 409
    assert client.get(f"/dataset-versions/{v['id']}", headers=admin).json()["status"] == "DRAFT"
    assert client.post("/training-examples/preview", headers=admin, json={}).json()["eligible_count"] == 0
    lineage = client.get(f"/training-examples/{e['id']}/lineage", headers=reviewer).json()
    assert lineage["example"]["snapshot"]["reviews"][0]["decision"] == "APPROVED"
    assert lineage["example"]["snapshot"]["runs"][0]["steps"]


@pytest.mark.parametrize("format", ["sft", "reward", "trajectory"])
@pytest.mark.parametrize("container", ["json", "jsonl"])
def test_export_formats_checksums_and_immutable_versions(client, admin, project, tmp_path, format, container):
    _, e, _ = approved_example(client, admin, project)
    d = client.post("/datasets", headers=admin, json={"name": "Export fixture"}).json()
    v = client.post(f"/datasets/{d['id']}/versions", headers=admin, json={"example_ids": [e["id"]]}).json()
    r = client.post(f"/dataset-versions/{v['id']}/finalize", headers=admin)
    assert r.status_code == 200, r.text
    assert len(r.json()["checksum"]) == 64
    assert client.post(f"/dataset-versions/{v['id']}/finalize", headers=admin).status_code == 409
    with patch("app.services.export_jobs.client"):
        r = client.post(
            f"/dataset-versions/{v['id']}/exports", headers=admin, json={"format": format, "container": container}
        )
    assert r.status_code == 202, r.text
    with patch("app.services.export_jobs.settings") as settings:
        settings.return_value.export_directory = str(tmp_path)
        assert process_next(client.factory)
        file = client.get(f"/exports/{r.json()['id']}/files/dataset", headers=admin)
        manifest = client.get(f"/exports/{r.json()['id']}/files/manifest", headers=admin).json()
        assert hashlib.sha256(file.content).hexdigest() == manifest["files"]["dataset"]["sha256"]
        value = json.loads(file.text) if container == "json" else [json.loads(line) for line in file.text.splitlines()]
        assert len(value) == 1
        assert {"sft": "messages", "reward": "score", "trajectory": "trajectory"}[format] in value[0]


def test_dpo_requires_real_preference_pair(client, admin, project, tmp_path):
    t, e, _ = approved_example(client, admin, project)
    d = client.post("/datasets", headers=admin, json={"name": "No fabricated pairs"}).json()
    v = client.post(f"/datasets/{d['id']}/versions", headers=admin, json={"example_ids": [e["id"]]}).json()
    client.post(f"/dataset-versions/{v['id']}/finalize", headers=admin)
    with patch("app.services.export_jobs.client"):
        response = client.post(f"/dataset-versions/{v['id']}/exports", headers=admin, json={"format": "dpo"})
    assert response.status_code == 202
    with patch("app.services.export_jobs.settings") as settings:
        settings.return_value.export_directory = str(tmp_path)
        assert process_next(client.factory)
        jobs = client.get("/exports", headers=admin).json()
        job = next(j for j in jobs if j["id"] == response.json()["id"])
        assert job["status"] == "FAILED"
        assert "preference pair" in job["error"].lower()
        assert client.get(f"/exports/{job['id']}/files/dataset", headers=admin).status_code == 409
    from app.services.export_formats import export_record

    snapshot = e["snapshot"]
    chosen = snapshot["runs"][0]
    rejected = {
        **chosen,
        "id": "alternative",
        "steps": [{"step_type": "final_answer", "content": "Unsupported answer"}],
    }
    snapshot["runs"].append(rejected)
    snapshot["preference_pair"] = {"chosen_run_id": chosen["id"], "rejected_run_id": "alternative"}
    output = export_record(snapshot, "dpo")
    assert output["chosen"] == "Verified answer" and output["rejected"] == "Unsupported answer"


def test_policy_change_blocks_finalization_and_tenant_access(client, admin, project):
    _, e, _ = approved_example(client, admin, project)
    d = client.post("/datasets", headers=admin, json={"name": "Policy frozen at finalization"}).json()
    v = client.post(f"/datasets/{d['id']}/versions", headers=admin, json={"example_ids": [e["id"]]}).json()
    client.put(f"/projects/{project['id']}/quality-rules", headers=admin, json={"required_reviews": 2})
    assert client.post(f"/dataset-versions/{v['id']}/finalize", headers=admin).status_code == 409
    other = client.post(
        "/auth/register",
        json={
            "email": "isolated@example.com",
            "password": "secure-password-123",
            "full_name": "Other",
            "organization_name": "Other",
        },
    ).json()
    headers = {"Authorization": f"Bearer {other['access_token']}"}
    for path in [f"/datasets/{d['id']}", f"/dataset-versions/{v['id']}", f"/training-examples/{e['id']}/lineage"]:
        assert client.get(path, headers=headers).status_code == 404


def test_required_approvals_and_score_variance_are_independent_gates(client, admin, project):
    client.put(
        f"/projects/{project['id']}/quality-rules",
        headers=admin,
        json={
            "required_annotations": 2,
            "required_reviews": 2,
            "minimum_score": 4,
            "maximum_variance": 0.1,
            "auto_escalate_disagreement": False,
        },
    )
    t = queued_task(client, admin, project)
    a = create_role(client, admin, "ANNOTATOR", "a")
    b = create_role(client, admin, "ANNOTATOR", "b")
    r1 = create_role(client, admin, "REVIEWER", "a")
    r2 = create_role(client, admin, "REVIEWER", "b")
    annotate(client, a, score=5)
    annotate(client, b, score=3)
    client.post(f"/tasks/{t['id']}/reviews", headers=r1, json={"decision": "APPROVED", "comments": "First check"})
    gate = client.post(f"/tasks/{t['id']}/quality-gate", headers=admin).json()
    assert {
        "requires_reviewer_approval",
        "annotation_quality_below_threshold",
        "score_variance_above_threshold",
    }.issubset(gate["reasons"])
    client.post(f"/tasks/{t['id']}/reviews", headers=r2, json={"decision": "APPROVED", "comments": "Second check"})
    gate = client.post(f"/tasks/{t['id']}/quality-gate", headers=admin).json()
    assert "requires_reviewer_approval" not in gate["reasons"]
    assert not gate["eligible"]


def test_gold_history_gate_does_not_assume_unmeasured_workers_are_accurate(client, admin, project):
    t = queued_task(client, admin, project)
    annotate(client, create_role(client, admin, "ANNOTATOR"))
    reviewer = create_role(client, admin, "REVIEWER")
    client.post(f"/tasks/{t['id']}/reviews", headers=reviewer, json={"decision": "APPROVED", "comments": "Reviewed"})
    client.put(
        f"/projects/{project['id']}/quality-rules",
        headers=admin,
        json={"minimum_gold_accuracy": 0.8, "minimum_gold_attempts": 3},
    )
    gate = client.post(f"/tasks/{t['id']}/quality-gate", headers=admin).json()
    assert not gate["eligible"] and "insufficient_gold_history" in gate["reasons"]


def test_postgres_finalized_records_reject_direct_mutation(client, admin, project):
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    with client.factory() as db:
        if db.bind.dialect.name != "postgresql":
            pytest.skip("PostgreSQL migration triggers require PostgreSQL")
    _, example, _ = approved_example(client, admin, project)
    dataset = client.post("/datasets", headers=admin, json={"name": "Immutable evidence"}).json()
    version = client.post(
        f"/datasets/{dataset['id']}/versions", headers=admin, json={"example_ids": [example["id"]]}
    ).json()
    assert client.post(f"/dataset-versions/{version['id']}/finalize", headers=admin).status_code == 200
    statements = [
        ("UPDATE training_examples SET checksum = 'changed' WHERE id = :id", example["id"]),
        ("DELETE FROM training_examples WHERE id = :id", example["id"]),
        ("UPDATE dataset_versions SET status = 'DRAFT' WHERE id = :id", version["id"]),
        ("DELETE FROM dataset_versions WHERE id = :id", version["id"]),
        ("UPDATE dataset_examples SET position = 99 WHERE version_id = :id", version["id"]),
        ("DELETE FROM dataset_examples WHERE version_id = :id", version["id"]),
    ]
    for statement, identifier in statements:
        with client.factory() as db, pytest.raises(DBAPIError, match="immutable"):
            db.execute(text(statement), {"id": identifier})
            db.commit()
    assert client.delete(f"/projects/{project['id']}", headers=admin).status_code == 409
