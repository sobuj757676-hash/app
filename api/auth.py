"""Authentication: bcrypt password hashing, JWT sessions, role-based access.

AUTH_SECRET must be set in the environment (same fail-fast pattern as
MONGO_URL in index.py). Tokens are HS256 JWTs valid for 7 days.
"""
import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

AUTH_SECRET = os.environ.get("AUTH_SECRET", "")
if not AUTH_SECRET:
    raise RuntimeError("AUTH_SECRET environment variable is not set")

ALGORITHM = "HS256"
TOKEN_DAYS = 7
ROLES = ("admin", "manager", "engineer", "supervisor", "worker", "viewer")

# Operational writes (units, inspections request, tests, points, workforce, materials)
OPS_ROLES = ("admin", "manager", "engineer", "supervisor")
# RTO approve/rework decisions (supervisor excluded)
DECIDE_ROLES = ("admin", "manager", "engineer")
# Financial + project structure writes
MONEY_ROLES = ("admin", "manager")

_bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except Exception:
        return False


def create_token(user: dict) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user["id"],
        "role": user.get("role"),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=TOKEN_DAYS)).timestamp()),
    }
    return jwt.encode(payload, AUTH_SECRET, algorithm=ALGORITHM)


def _decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, AUTH_SECRET, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Session expired. Please sign in again.")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid session. Please sign in again.")


def database():
    from server import db
    return db


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> dict:
    if credentials is None or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        raise HTTPException(401, "Sign in required")
    payload = _decode_token(credentials.credentials)
    user = await database().users.find_one({"id": payload.get("sub")}, {"_id": 0, "password_hash": 0})
    if not user or not user.get("active", True):
        raise HTTPException(401, "Account is no longer active")
    return user


def require_roles(*roles):
    async def checker(user: dict = Depends(get_current_user)) -> dict:
        if user.get("role") not in roles:
            raise HTTPException(403, "You do not have permission for this action")
        return user
    return checker


def public_user(user: dict) -> dict:
    return {
        key: user.get(key)
        for key in ("id", "name", "email", "phone", "role", "worker_id",
                    "active", "must_change_password", "created_at", "last_login_at")
    }
