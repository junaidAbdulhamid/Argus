from datetime import timedelta
import jwt
from sqlalchemy import select
from app.models.entities import AnnotationAssignment, Task, TaskStatus, now
from app.services.workflow import TRANSITIONS
from app.tests.conftest import create_role, queued_task


def test_authentication(client, admin):
    assert client.get("/auth/me").status_code == 401
    me = client.get("/auth/me", headers=admin).json()
    assert me["role"] == "ADMIN" and "password_hash" not in me
    assert client.post("/auth/login", json={"email": "admin@example.com", "password": "wrong"}).status_code == 401
    assert client.get("/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401
    expired = jwt.encode(
        {
            "sub": me["id"],
            "iat": now() - timedelta(hours=2),
            "exp": now() - timedelta(hours=1),
            "iss": "argus",
            "aud": "argus-api",
        },
        "test-only-secret-with-at-least-32-characters",
        algorithm="HS256",
    )
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {expired}"}).status_code == 401


def test_project_crud_rbac_and_tenant_isolation(client, admin, project):
    a = create_role(client, admin, "ANNOTATOR")
    assert client.post("/projects", headers=a, json={"name": "Forbidden"}).status_code == 403
    assert (
        client.patch(f"/projects/{project['id']}", headers=admin, json={"name": "Updated"}).json()["name"] == "Updated"
    )
    other = client.post(
        "/auth/register",
        json={
            "email": "other@example.com",
            "password": "secure-password-123",
            "full_name": "Other",
            "organization_name": "Other",
        },
    ).json()
    headers = {"Authorization": f"Bearer {other['access_token']}"}
    assert client.get(f"/projects/{project['id']}", headers=headers).status_code == 404
    assert client.get("/projects", headers=headers).json() == []
    assert client.delete(f"/projects/{project['id']}", headers=a).status_code == 403
    assert client.delete(f"/projects/{project['id']}", headers=admin).status_code == 204


def test_idempotency_batch_and_rollback(client, admin, project):
    url = f"/projects/{project['id']}/tasks"
    body = {"external_id": "unique", "task_type": "research", "metadata": {"source": "test"}}
    first = client.post(url, headers=admin, json=body).json()
    assert client.post(url, headers=admin, json=body).json()["id"] == first["id"]
    assert client.post(url, headers=admin, json={**body, "priority": 99}).status_code == 409
    assert (
        client.post(
            url + "/batch", headers=admin, json={"tasks": [{**body, "external_id": "new"}, {**body, "priority": 20}]}
        ).status_code
        == 409
    )
    assert client.get("/tasks", headers=admin).json()["total"] == 1
    assert (
        client.post(
            url + "/batch",
            headers=admin,
            json={"tasks": [{**body, "external_id": "two"}, {**body, "external_id": "three"}]},
        ).status_code
        == 201
    )
    assert client.get(f"/projects/{project['id']}", headers=admin).json()["counts"]["total"] == 3
    assert client.get("/tasks?search=two&page_size=1", headers=admin).json()["total"] == 1


def test_trajectory_validation_and_immutability(client, admin, project):
    t = client.post(f"/projects/{project['id']}/tasks", headers=admin, json={"task_type": "research"}).json()
    assert client.post(f"/tasks/{t['id']}/queue", headers=admin).status_code == 409
    payload = {
        "model_name": "test",
        "steps": [
            {"sequence_number": 1, "step_type": "tool_call"},
            {"sequence_number": 0, "step_type": "final_answer"},
        ],
    }
    assert client.post(f"/tasks/{t['id']}/runs", headers=admin, json=payload).status_code == 422
    payload["steps"][0]["sequence_number"] = 0
    assert client.post(f"/tasks/{t['id']}/runs", headers=admin, json=payload).status_code == 422
    t = queued_task(client, admin, project)
    trace = client.get(f"/tasks/{t['id']}/trajectory", headers=admin).json()
    assert [s["sequence_number"] for s in trace[0]["steps"]] == [0, 1, 2]
    assert trace[0]["steps"][1]["tool_input"] == {"q": "evidence"}
    assert (
        client.post(
            f"/tasks/{t['id']}/runs",
            headers=admin,
            json={"model_name": "test", "steps": [{"sequence_number": 0, "step_type": "final_answer"}]},
        ).status_code
        == 409
    )
    assert client.post(f"/tasks/{t['id']}/queue", headers=admin).status_code == 409


def test_claim_priority_ownership_and_no_duplicates(client, admin, project):
    low = queued_task(client, admin, project, "low", 1)
    high = queued_task(client, admin, project, "high", 99)
    a = create_role(client, admin, "ANNOTATOR", "a")
    b = create_role(client, admin, "ANNOTATOR", "b")
    assert client.get(f"/tasks/{high['id']}", headers=a).status_code == 404
    assert client.get("/tasks", headers=a).json()["total"] == 0
    first = client.post("/annotation/next", headers=a).json()
    assert first["task_id"] == high["id"]
    assert client.post("/annotation/next", headers=a).json()["id"] == first["id"]
    second = client.post("/annotation/next", headers=b).json()
    assert second["task_id"] == low["id"]
    assert client.post(f"/assignments/{first['id']}/start", headers=b).status_code == 404
    assert client.get(f"/annotation/assignments/{first['id']}", headers=b).status_code == 404
    assert client.post("/annotation/next", headers=admin).status_code == 404


def test_annotation_review_and_audit(client, admin, project):
    t = queued_task(client, admin, project)
    a = create_role(client, admin, "ANNOTATOR")
    r = create_role(client, admin, "REVIEWER")
    assert client.post("/annotation/next", headers=r).status_code == 403
    aid = client.post("/annotation/next", headers=a).json()["id"]
    assert client.post(f"/assignments/{aid}/complete", headers=a).status_code == 409
    body = {"label": "SUCCESS", "score": 4, "feedback": "Accurate citations", "structured_payload": {"grounded": True}}
    assert client.post(f"/assignments/{aid}/annotations", headers=a, json=body).status_code == 409
    assert client.post(f"/assignments/{aid}/start", headers=a).status_code == 200
    ann = client.post(f"/assignments/{aid}/annotations", headers=a, json=body).json()
    assert client.post(f"/assignments/{aid}/annotations", headers=a, json=body).status_code == 409
    assert client.patch(f"/annotations/{ann['id']}", headers=a, json={**body, "score": 5}).json()["score"] == 5
    assert client.post(f"/assignments/{aid}/complete", headers=a).status_code == 200
    assert client.get(f"/tasks/{t['id']}", headers=admin).json()["status"] == "PENDING_REVIEW"
    assert client.patch(f"/annotations/{ann['id']}", headers=a, json=body).status_code == 409
    assert (
        client.post(f"/tasks/{t['id']}/review", headers=a, json={"decision": "APPROVED", "reason": "good"}).status_code
        == 403
    )
    assert (
        client.post(
            f"/tasks/{t['id']}/review", headers=r, json={"decision": "APPROVED", "reason": "Verified correctness"}
        ).status_code
        == 200
    )
    events = client.get(f"/tasks/{t['id']}/audit", headers=admin).json()
    assert {
        "TASK_CREATED",
        "TASK_QUEUED",
        "TASK_ASSIGNED",
        "ANNOTATION_STARTED",
        "ANNOTATION_SUBMITTED",
        "TASK_REVIEWED",
    }.issubset({e["event_type"] for e in events})
    stats = client.get("/overview", headers=admin).json()
    assert stats["counts"]["APPROVED"] == 1 and stats["completed_this_week"] == 1


def test_expired_assignment_recovery(client, admin, project):
    t = queued_task(client, admin, project)
    a = create_role(client, admin, "ANNOTATOR", "a")
    b = create_role(client, admin, "ANNOTATOR", "b")
    old = client.post("/annotation/next", headers=a).json()
    with client.factory() as db:
        db.get(AnnotationAssignment, old["id"]).assigned_at = now() - timedelta(hours=2)
        db.commit()
    assert client.post(f"/assignments/{old['id']}/start", headers=a).status_code == 409
    new = client.post("/annotation/next", headers=b).json()
    assert new["task_id"] == t["id"] and new["id"] != old["id"]
    assert client.get(f"/annotation/assignments/{old['id']}", headers=a).json()["status"] == "EXPIRED"
    with client.factory() as db:
        assert (
            len(
                db.scalars(
                    select(AnnotationAssignment).where(
                        AnnotationAssignment.task_id == t["id"], AnnotationAssignment.status == "ASSIGNED"
                    )
                ).all()
            )
            == 1
        )


def test_no_self_review_and_cascade(client, admin, project):
    t = queued_task(client, admin, project)
    a = client.post("/annotation/next", headers=admin).json()
    client.post(f"/assignments/{a['id']}/start", headers=admin)
    client.post(f"/assignments/{a['id']}/annotations", headers=admin, json={"label": "SUCCESS", "score": 5})
    client.post(f"/assignments/{a['id']}/complete", headers=admin)
    assert (
        client.post(
            f"/tasks/{t['id']}/review", headers=admin, json={"decision": "APPROVED", "reason": "self"}
        ).status_code
        == 403
    )
    assert client.delete(f"/projects/{project['id']}", headers=admin).status_code == 204
    with client.factory() as db:
        assert db.get(Task, t["id"]) is None


def test_state_machine_has_no_approval_shortcut():
    for state, targets in TRANSITIONS.items():
        if state != TaskStatus.PENDING_REVIEW:
            assert TaskStatus.APPROVED not in targets
    assert TRANSITIONS[TaskStatus.APPROVED] == set()
