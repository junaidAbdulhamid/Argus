from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from app.db.session import get_db
from app.models.entities import User, Organization, Role
from app.schemas.requests import Register, Login, UserCreate
from app.auth.security import passwords, token, current_user, roles, DUMMY_HASH
from app.repositories.platform import serialize
from app.services.workflow import audit

router = APIRouter(tags=["Authentication"])


@router.post("/auth/register", status_code=201)
def register(data: Register, db=Depends(get_db)):
    email = str(data.email).lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "Email already registered")
    organization = Organization(name=data.organization_name)
    db.add(organization)
    db.flush()
    user = User(
        email=email,
        password_hash=passwords.hash(data.password),
        full_name=data.full_name,
        role=Role.ADMIN,
        organization_id=organization.id,
    )
    db.add(user)
    db.flush()
    audit(db, user, "ORGANIZATION_CREATED")
    return {"access_token": token(user), "token_type": "bearer", "user": serialize(user)}


@router.post("/auth/login")
def login(data: Login, db=Depends(get_db)):
    user = db.scalar(select(User).where(User.email == str(data.email).lower()))
    valid = passwords.verify(data.password, user.password_hash if user else DUMMY_HASH)
    if not user or not valid:
        raise HTTPException(401, "Incorrect email or password")
    return {"access_token": token(user), "token_type": "bearer", "user": serialize(user)}


@router.get("/auth/me")
def me(user=Depends(current_user)):
    return serialize(user)


@router.get("/users")
def users(user=Depends(current_user), db=Depends(get_db)):
    return [
        serialize(u)
        for u in db.scalars(select(User).where(User.organization_id == user.organization_id).order_by(User.full_name))
    ]


@router.post("/users", status_code=201)
def create_user(data: UserCreate, user=Depends(roles(Role.ADMIN)), db=Depends(get_db)):
    if db.scalar(select(User).where(User.email == str(data.email).lower())):
        raise HTTPException(409, "Email already registered")
    created = User(
        email=str(data.email).lower(),
        full_name=data.full_name,
        password_hash=passwords.hash(data.password),
        role=data.role,
        organization_id=user.organization_id,
    )
    db.add(created)
    db.flush()
    audit(db, user, "USER_CREATED", payload={"user_id": created.id, "role": created.role})
    return serialize(created)
