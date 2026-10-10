"""Authentication and permission dependencies. Frontend hiding is not the control."""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models import User
from app.services.present import permissions_for

_bearer = HTTPBearer(auto_error=False)
_buckets: dict[str, list[float]] = {}


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or not credentials.credentials:
        raise HTTPException(status_code=401, detail={"code": "unauthorized", "message": "Sign in is required."})
    try:
        payload = decode_access_token(credentials.credentials)
        user_id = uuid.UUID(str(payload["sub"]))
    except (jwt.PyJWTError, ValueError, KeyError) as exc:
        raise HTTPException(
            status_code=401, detail={"code": "unauthorized", "message": "The session is invalid or has expired."}
        ) from exc
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail={"code": "unauthorized", "message": "The account is not active."})
    return user


def require(permission: str) -> Callable:
    def checker(user: User = Depends(get_current_user)) -> User:
        granted = set(permissions_for(user))
        if "*" not in granted and permission not in granted:
            raise HTTPException(
                status_code=403,
                detail={"code": "forbidden", "message": "You do not have permission for this action."},
            )
        return user

    return checker


def client_ip(request: Request) -> str | None:
    if request.client is None:
        return None
    return request.client.host


def enforce_rate_limit(key: str, limit: int, window_seconds: int = 60) -> None:
    now = time.time()
    hits = [stamp for stamp in _buckets.get(key, []) if now - stamp < window_seconds]
    if len(hits) >= limit:
        raise HTTPException(
            status_code=429,
            detail={"code": "rate_limited", "message": "Too many requests. Try again shortly."},
        )
    hits.append(now)
    _buckets[key] = hits


def reset_rate_limits() -> None:
    _buckets.clear()
