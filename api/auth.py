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
ROLES = ("admin", "manager", "engineer", "supervisor", "worker", "viewer",
         "super_admin", "company_admin", "pm", "qs", "storekeeper", "hr")

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


# Field roles (worker/supervisor) get a longer session: their app queues
# writes offline all shift, and a 7-day expiry dying mid-week strands that
# queue behind a re-login. Accounts can still be revoked instantly via the
# active flag, which get_current_user checks on every request.
FIELD_TOKEN_DAYS = 30
FIELD_ROLES = ('worker', 'supervisor')


def create_token(user: dict) -> str:
    now = datetime.now(timezone.utc)
    days = FIELD_TOKEN_DAYS if user.get('role') in FIELD_ROLES else TOKEN_DAYS
    payload = {
        "sub": user["id"],
        "role": user.get("role"),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=days)).timestamp()),
    }
    if user.get("company_id"):
        payload["company_id"] = user["company_id"]
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
    out = {
        key: user.get(key)
        for key in ("id", "name", "email", "phone", "role", "worker_id",
                    "active", "must_change_password", "created_at", "last_login_at")
    }
    for key in ("company_id", "preferred_lang"):
        if user.get(key) is not None:
            out[key] = user[key]
    return out


async def get_current_tenant(user: dict = Depends(get_current_user)) -> dict:
    """Resolve the caller's tenant (company) for v2 endpoints.

    super_admin is platform-level and has no tenant (company=None). Every
    other user resolves to their company doc; legacy users without a
    company_id fall back to the seeded "company-default" tenant. A missing
    company doc is treated as the default tenant (never a hard failure);
    a SUSPENDED company is a hard 403.
    """
    if user.get("role") == "super_admin":
        return {"user": user, "company": None}
    db = database()
    company_id = user.get("company_id") or "company-default"
    company = await db.companies.find_one({"id": company_id}, {"_id": 0})
    if company is None and company_id != "company-default":
        company = await db.companies.find_one({"id": "company-default"}, {"_id": 0})
    if company is not None and company.get("status") == "SUSPENDED":
        raise HTTPException(403, {
            "error_code": "TENANT_SUSPENDED",
            "message": "This company account is suspended. Please contact the platform administrator.",
        })
    return {"user": user, "company": company}
