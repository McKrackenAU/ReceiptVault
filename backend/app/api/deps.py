from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.crypto import hash_token
from app.db import get_db
from app.errors import AppError
from app.models import Session as UserSession
from app.models import User


def settings_dep() -> Settings:
    return get_settings()


def client_ip(request: Request, settings: Settings) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded and settings.trusted_proxy_list:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


def current_session(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(settings_dep),
) -> UserSession:
    raw = request.cookies.get(settings.cookie_name)
    if not raw:
        raise AppError(401, "Unauthorized", "Authentication required")
    session = db.query(UserSession).filter(UserSession.token_hash == hash_token(raw)).one_or_none()
    if not session or session.revoked_at or session.expires_at <= datetime.now(timezone.utc):
        raise AppError(401, "Unauthorized", "Session expired")
    session.last_seen_at = datetime.now(timezone.utc)
    return session


def current_user(session: UserSession = Depends(current_session), db: Session = Depends(get_db)) -> User:
    user = db.get(User, session.user_id)
    if not user:
        raise AppError(401, "Unauthorized", "User missing")
    return user


def require_csrf(
    request: Request,
    session: UserSession = Depends(current_session),
    settings: Settings = Depends(settings_dep),
) -> None:
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    header = request.headers.get(settings.csrf_header)
    cookie = request.cookies.get("rv_csrf")
    if header == session.csrf_token or cookie == session.csrf_token:
        return
    raise AppError(403, "CSRF failed", "Missing or invalid CSRF token")
