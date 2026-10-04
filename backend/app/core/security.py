"""JWT auth with role-based access (customer / analyst / admin)."""
from __future__ import annotations

import hmac
import time
from typing import Iterable

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings

ROLES = ("customer", "analyst", "admin")
_bearer = HTTPBearer(auto_error=False)


def demo_users() -> dict[str, str]:
    """username -> role. customer and analyst share DEMO_PASSWORD (synthetic demo only)."""
    return {"customer": "customer", "analyst": "analyst", "admin": "admin"}


def _expected_password(role: str) -> str | None:
    """Password for a role, or None when that login is disabled."""
    s = get_settings()
    if role != "admin":
        return s.demo_password
    if s.admin_password:
        return s.admin_password
    # DEMO_PASSWORD is public (it is built into the web app), so it may unlock admin only in development.
    return s.demo_password if s.environment == "development" else None


def authenticate(username: str, password: str) -> str | None:
    role = demo_users().get(username)
    expected = _expected_password(role) if role else None
    if expected and hmac.compare_digest(password.encode(), expected.encode()):
        return role
    return None


def create_token(username: str, role: str) -> str:
    s = get_settings()
    now = int(time.time())
    payload = {"sub": username, "role": role, "iat": now, "exp": now + s.jwt_expire_minutes * 60}
    return jwt.encode(payload, s.jwt_secret, algorithm="HS256")


class Principal(dict):
    @property
    def role(self) -> str:
        return self["role"]

    @property
    def username(self) -> str:
        return self["sub"]


def get_principal(creds: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> Principal:
    s = get_settings()
    if creds is None:
        if not s.auth_required:
            return Principal(sub="anonymous", role="admin")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    try:
        payload = jwt.decode(creds.credentials, s.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Invalid token: {exc}") from exc
    return Principal(payload)


def require_roles(*roles: Iterable[str]):
    allowed = set(roles) | {"admin"}

    def dep(principal: Principal = Depends(get_principal)) -> Principal:
        if principal.role not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Role '{principal.role}' not allowed")
        return principal

    return dep
