from fastapi import APIRouter, Depends
from sqlalchemy import select
from app.db.session import get_db
from app.auth.security import current_user, roles
from app.models.entities import Project, Role
from app.schemas.requests import ProjectCreate, ProjectPatch
from app.repositories.platform import project, counts, serialize
from app.services.workflow import audit

router = APIRouter(prefix="/projects", tags=["Projects"])


def detail(db, obj):
    return {**serialize(obj), "counts": counts(db, [obj.id])}


@router.get("")
def list_projects(user=Depends(current_user), db=Depends(get_db)):
    return [
        detail(db, p)
        for p in db.scalars(
            select(Project).where(Project.organization_id == user.organization_id).order_by(Project.created_at.desc())
        )
    ]


@router.post("", status_code=201)
def create(data: ProjectCreate, user=Depends(roles(Role.ADMIN)), db=Depends(get_db)):
    obj = Project(**data.model_dump(), organization_id=user.organization_id)
    db.add(obj)
    db.flush()
    audit(db, user, "PROJECT_CREATED", project_id=obj.id)
    return detail(db, obj)


@router.get("/{project_id}")
def get(project_id: str, user=Depends(current_user), db=Depends(get_db)):
    return detail(db, project(db, user, project_id))


@router.patch("/{project_id}")
def update(project_id: str, data: ProjectPatch, user=Depends(roles(Role.ADMIN)), db=Depends(get_db)):
    obj = project(db, user, project_id, lock=True)
    for key, value in data.model_dump(exclude_none=True).items():
        setattr(obj, key, value)
    audit(db, user, "PROJECT_UPDATED", project_id=obj.id, payload=data.model_dump(exclude_none=True))
    db.flush()
    return detail(db, obj)


@router.delete("/{project_id}", status_code=204)
def delete(project_id: str, user=Depends(roles(Role.ADMIN)), db=Depends(get_db)):
    obj = project(db, user, project_id, lock=True)
    audit(db, user, "PROJECT_DELETED", payload={"project_id": obj.id, "name": obj.name})
    db.delete(obj)
