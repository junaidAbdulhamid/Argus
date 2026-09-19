from datetime import timedelta
import jwt
from pwdlib import PasswordHash
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from app.core.config import settings
from app.db.session import get_db
from app.models.entities import User, now

passwords = PasswordHash.recommended()
bearer = HTTPBearer(auto_error=False)
DUMMY_HASH = passwords.hash("constant-non-user-password")


def token(user):
    return jwt.encode(
        {
            "sub": user.id,
            "iat": now(),
            "exp": now() + timedelta(minutes=settings().token_minutes),
            "iss": "argus",
            "aud": "argus-api",
        },
        settings().jwt_secret,
        algorithm="HS256",
    )


def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer), db=Depends(get_db)):
    try:
        if not credentials:
            raise ValueError()
        claims = jwt.decode(
            credentials.credentials,
            settings().jwt_secret,
            algorithms=["HS256"],
            issuer="argus",
            audience="argus-api",
            options={"require": ["sub", "exp", "iat"]},
        )
        user = db.scalar(select(User).where(User.id == claims["sub"]))
        if not user:
            raise ValueError()
        return user
    except (jwt.PyJWTError, ValueError):
        raise HTTPException(401, "Valid authentication is required", headers={"WWW-Authenticate": "Bearer"})


def roles(*allowed):
    def dependency(user=Depends(current_user)):
        if user.role not in allowed:
            raise HTTPException(403, "Your role cannot perform this action")
        return user

    return dependency
