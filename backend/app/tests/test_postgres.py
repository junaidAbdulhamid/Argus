"""Opt-in real PostgreSQL tests. Uses an isolated schema, never drops application tables."""

import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch
import pytest
from sqlalchemy import create_engine, text, select
from sqlalchemy.orm import sessionmaker
from app.models.entities import Base, Organization, User, Role, Project, Task, TaskStatus, AnnotationAssignment
from app.services.workflow import claim


@pytest.fixture
def pg_factory():
    url = os.environ.get("TEST_POSTGRES_URL")
    if not url:
        pytest.skip("Set TEST_POSTGRES_URL to run real PostgreSQL concurrency checks")
    schema = "argus_test_" + uuid.uuid4().hex
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text(f"CREATE SCHEMA {schema}"))
    scoped = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    try:
        Base.metadata.create_all(scoped)
        yield sessionmaker(scoped, expire_on_commit=False)
    finally:
        scoped.dispose()
        with engine.begin() as conn:
            conn.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        engine.dispose()


def setup_queue(factory, n=8):
    with factory() as db:
        org = Organization(name="Concurrency test")
        db.add(org)
        db.flush()
        users = [
            User(
                email=f"{i}@example.com",
                full_name=f"Annotator {i}",
                password_hash="not-used-in-service-test",
                role=Role.ANNOTATOR,
                organization_id=org.id,
            )
            for i in range(n)
        ]
        db.add_all(users)
        p = Project(name="Concurrent claims", organization_id=org.id)
        db.add(p)
        db.flush()
        tasks = [Task(project_id=p.id, task_type="research", status=TaskStatus.QUEUED, priority=i) for i in range(n)]
        db.add_all(tasks)
        db.commit()
        return [u.id for u in users]


def test_simultaneous_claims_have_distinct_tasks(pg_factory):
    users = setup_queue(pg_factory)
    barrier = Barrier(len(users))

    def worker(uid):
        with pg_factory() as db:
            user = db.get(User, uid)
            barrier.wait(timeout=10)
            return claim(db, user).task_id

    with (
        patch("app.services.workflow.sync_task"),
        patch("app.services.workflow.pop_priority_hint", return_value=None),
        ThreadPoolExecutor(max_workers=len(users)) as pool,
    ):
        task_ids = list(pool.map(worker, users))
    assert len(set(task_ids)) == len(users)
    with pg_factory() as db:
        assert len(db.scalars(select(AnnotationAssignment)).all()) == len(users)
        assert all(t.status == TaskStatus.ASSIGNED for t in db.scalars(select(Task)))


def test_simultaneous_requests_by_same_annotator_resume(pg_factory):
    uid = setup_queue(pg_factory, 4)[0]
    barrier = Barrier(4)

    def worker(_):
        with pg_factory() as db:
            user = db.get(User, uid)
            barrier.wait(timeout=10)
            assignment = claim(db, user)
            db.commit()
            return assignment.id

    with (
        patch("app.services.workflow.sync_task"),
        patch("app.services.workflow.pop_priority_hint", return_value=999),
        ThreadPoolExecutor(max_workers=4) as pool,
    ):
        ids = list(pool.map(worker, range(4)))
    assert len(set(ids)) == 1
    with pg_factory() as db:
        assert len(db.scalars(select(AnnotationAssignment)).all()) == 1
