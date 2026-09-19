import os
import uuid

os.environ.setdefault("JWT_SECRET", "test-only-secret-with-at-least-32-characters")
os.environ.setdefault("DATABASE_URL", "sqlite://")
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.models.entities import Base
from app.db.session import get_db
from app.main import app


@pytest.fixture
def client():
    postgres_url = os.environ.get("TEST_API_POSTGRES_URL")
    admin_engine = None
    schema = None
    if postgres_url:
        schema = "argus_api_test_" + uuid.uuid4().hex
        admin_engine = create_engine(postgres_url)
        with admin_engine.begin() as conn:
            conn.execute(text(f"CREATE SCHEMA {schema}"))
        engine = create_engine(postgres_url, connect_args={"options": f"-csearch_path={schema}"})
    else:
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

        @event.listens_for(engine, "connect")
        def foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)

    def override():
        with factory() as db:
            try:
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise

    app.dependency_overrides[get_db] = override
    with (
        patch("app.api.tasks.sync_task"),
        patch("app.services.workflow.sync_task"),
        patch("app.services.workflow.pop_priority_hint", return_value=None),
        patch("app.api.operations.health", return_value="healthy"),
    ):
        with TestClient(app) as c:
            c.factory = factory
            yield c
    app.dependency_overrides.clear()
    engine.dispose()
    if admin_engine:
        with admin_engine.begin() as conn:
            conn.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        admin_engine.dispose()


@pytest.fixture
def admin(client):
    r = client.post(
        "/auth/register",
        json={
            "email": "admin@example.com",
            "password": "secure-password-123",
            "full_name": "Admin",
            "organization_name": "Test Org",
        },
    )
    assert r.status_code == 201
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def project(client, admin):
    return client.post("/projects", headers=admin, json={"name": "Research agents", "description": "Evaluation"}).json()


def create_role(client, admin, role, suffix=""):
    email = f"{role.lower()}{suffix}@example.com"
    r = client.post(
        "/users",
        headers=admin,
        json={"email": email, "password": "secure-password-123", "full_name": role, "role": role},
    )
    assert r.status_code == 201, r.text
    login = client.post("/auth/login", json={"email": email, "password": "secure-password-123"})
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def queued_task(client, admin, project, external_id="task-1", priority=50):
    t = client.post(
        f"/projects/{project['id']}/tasks",
        headers=admin,
        json={
            "external_id": external_id,
            "task_type": "research",
            "priority": priority,
            "input_payload": {"question": "Find evidence"},
        },
    ).json()
    assert (
        client.post(
            f"/tasks/{t['id']}/runs",
            headers=admin,
            json={
                "model_name": "agent-v1",
                "steps": [
                    {"sequence_number": 0, "step_type": "user_message", "content": "Find evidence"},
                    {
                        "sequence_number": 1,
                        "step_type": "tool_call",
                        "tool_name": "search",
                        "tool_input": {"q": "evidence"},
                    },
                    {"sequence_number": 2, "step_type": "final_answer", "content": "Verified answer"},
                ],
            },
        ).status_code
        == 201
    )
    assert client.post(f"/tasks/{t['id']}/queue", headers=admin).status_code == 200
    return t
