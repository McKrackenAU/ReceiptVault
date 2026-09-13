from __future__ import annotations

from datetime import datetime, timedelta, timezone
from io import BytesIO

import pyotp
import qrcode
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.api.deps import client_ip, current_session, current_user, require_csrf, settings_dep
from app.config import Settings
from app.crypto import encrypt_secret, hash_password, hash_token, new_token, verify_password
from app.db import get_db
from app.errors import AppError
from app.models import RecoveryCode, Session as UserSession, TaxpayerProfile, User
from app.services.audit import record_audit

router = APIRouter(prefix="/auth", tags=["auth"])

_login_attempts: dict[str, list[float]] = {}


class SetupBody(BaseModel):
    username: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=12, max_length=256)
    timezone: str = "Australia/Melbourne"


class LoginBody(BaseModel):
    username: str
    password: str
    totp: str | None = None
    recovery_code: str | None = None


class PasswordBody(BaseModel):
    current_password: str
    new_password: str = Field(min_length=12)


class TotpVerifyBody(BaseModel):
    code: str


def _rate_limit(key: str, limit: int) -> None:
    now = datetime.now(timezone.utc).timestamp()
    window = [t for t in _login_attempts.get(key, []) if now - t < 60]
    if len(window) >= limit:
        raise AppError(429, "Too many attempts", "Try again in a minute")
    window.append(now)
    _login_attempts[key] = window


def _set_session_cookie(response: Response, settings: Settings, raw: str) -> None:
    response.set_cookie(
        settings.cookie_name,
        raw,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=settings.session_seconds,
        path="/",
    )


def _set_csrf_cookie(response: Response, settings: Settings, token: str) -> None:
    response.set_cookie(
        "rv_csrf",
        token,
        httponly=False,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=settings.session_seconds,
        path="/",
    )


def _new_session(db: Session, user: User, settings: Settings, request: Request) -> tuple[UserSession, str]:
    raw = new_token(32)
    session = UserSession(
        user_id=user.id,
        token_hash=hash_token(raw),
        csrf_token=new_token(24),
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=settings.session_seconds),
        ip=client_ip(request, settings),
        user_agent=request.headers.get("user-agent"),
    )
    db.add(session)
    db.flush()
    return session, raw


@router.get("/setup-required")
def setup_required(db: Session = Depends(get_db)) -> dict:
    return {"required": db.query(User).count() == 0}


@router.post("/setup")
def setup(body: SetupBody, request: Request, response: Response, db: Session = Depends(get_db), settings: Settings = Depends(settings_dep)):
    if db.query(User).count() > 0:
        raise AppError(403, "Setup disabled", "Owner already exists")
    user = User(
        username=body.username.strip(),
        email=str(body.email).lower(),
        password_hash=hash_password(body.password),
        timezone=body.timezone,
        setup_completed_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.flush()
    db.add(TaxpayerProfile(user_id=user.id, common_equipment=[], audit_years=[]))
    session, raw = _new_session(db, user, settings, request)
    record_audit(db, event_type="owner_setup", success=True, user_id=user.id, username=user.username, ip=client_ip(request, settings))
    db.commit()
    _set_session_cookie(response, settings, raw)
    _set_csrf_cookie(response, settings, session.csrf_token)
    return {"ok": True, "csrf": session.csrf_token, "username": user.username}


@router.post("/login")
def login(body: LoginBody, request: Request, response: Response, db: Session = Depends(get_db), settings: Settings = Depends(settings_dep)):
    ip = client_ip(request, settings)
    _rate_limit(f"{ip}:{body.username}", settings.login_rate_per_minute)
    user = db.query(User).filter(User.username == body.username).one_or_none()
    if not user or not verify_password(body.password, user.password_hash):
        record_audit(db, event_type="login_failed", success=False, username=body.username, ip=ip)
        db.commit()
        raise AppError(401, "Invalid credentials", "Username or password is incorrect")
    if user.totp_enabled:
        from app.crypto import decrypt_secret

        ok = False
        if body.totp:
            ok = pyotp.TOTP(decrypt_secret(user.totp_secret_encrypted)).verify(body.totp, valid_window=1)
        if not ok and body.recovery_code:
            hashed = hash_token(body.recovery_code.strip().replace(" ", "").upper())
            code = (
                db.query(RecoveryCode)
                .filter(RecoveryCode.user_id == user.id, RecoveryCode.code_hash == hashed, RecoveryCode.used_at.is_(None))
                .one_or_none()
            )
            if code:
                code.used_at = datetime.now(timezone.utc)
                ok = True
        if not ok:
            record_audit(db, event_type="login_failed", success=False, user_id=user.id, username=user.username, ip=ip, metadata={"reason": "totp"})
            db.commit()
            raise AppError(401, "Second factor required", "Enter an authenticator code or recovery code")
    session, raw = _new_session(db, user, settings, request)
    record_audit(db, event_type="login", success=True, user_id=user.id, username=user.username, ip=ip)
    db.commit()
    _set_session_cookie(response, settings, raw)
    _set_csrf_cookie(response, settings, session.csrf_token)
    return {"ok": True, "csrf": session.csrf_token, "username": user.username, "totp_enabled": user.totp_enabled}


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    session: UserSession = Depends(current_session),
    db: Session = Depends(get_db),
    settings: Settings = Depends(settings_dep),
    _: None = Depends(require_csrf),
):
    session.revoked_at = datetime.now(timezone.utc)
    record_audit(db, event_type="logout", success=True, user_id=session.user_id, ip=client_ip(request, settings))
    db.commit()
    response.delete_cookie(settings.cookie_name, path="/")
    return {"ok": True}


@router.post("/logout-all")
def logout_all(
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(settings_dep),
    _: None = Depends(require_csrf),
):
    now = datetime.now(timezone.utc)
    for session in db.query(UserSession).filter(UserSession.user_id == user.id, UserSession.revoked_at.is_(None)):
        session.revoked_at = now
    record_audit(db, event_type="logout_all", success=True, user_id=user.id, username=user.username, ip=client_ip(request, settings))
    db.commit()
    return {"ok": True}


@router.get("/me")
def me(
    response: Response,
    user: User = Depends(current_user),
    session: UserSession = Depends(current_session),
    settings: Settings = Depends(settings_dep),
):
    _set_csrf_cookie(response, settings, session.csrf_token)
    return {
        "username": user.username,
        "email": user.email,
        "timezone": user.timezone,
        "totp_enabled": user.totp_enabled,
        "csrf": session.csrf_token,
    }


@router.get("/csrf")
def csrf(
    response: Response,
    session: UserSession = Depends(current_session),
    settings: Settings = Depends(settings_dep),
):
    _set_csrf_cookie(response, settings, session.csrf_token)
    return {"csrf": session.csrf_token}


@router.post("/totp/start")
def totp_start(user: User = Depends(current_user), db: Session = Depends(get_db), _: None = Depends(require_csrf)):
    secret = pyotp.random_base32()
    user.totp_secret_encrypted = encrypt_secret(secret)
    db.commit()
    uri = pyotp.TOTP(secret).provisioning_uri(name=user.username, issuer_name="ReceiptVault")
    image = qrcode.make(uri)
    buf = BytesIO()
    image.save(buf, format="PNG")
    import base64

    return {"otpauth": uri, "qr_png_base64": base64.b64encode(buf.getvalue()).decode()}


@router.post("/totp/enable")
def totp_enable(body: TotpVerifyBody, user: User = Depends(current_user), db: Session = Depends(get_db), _: None = Depends(require_csrf)):
    from app.crypto import decrypt_secret

    if not user.totp_secret_encrypted or not pyotp.TOTP(decrypt_secret(user.totp_secret_encrypted)).verify(body.code, valid_window=1):
        raise AppError(400, "Invalid code", "Authenticator code was not accepted")
    user.totp_enabled = True
    codes = []
    db.query(RecoveryCode).filter(RecoveryCode.user_id == user.id).delete()
    for _ in range(8):
        raw = new_token(8).upper().replace("-", "")[:10]
        codes.append(raw)
        db.add(RecoveryCode(user_id=user.id, code_hash=hash_token(raw)))
    db.commit()
    return {"ok": True, "recovery_codes": codes}


@router.post("/password")
def change_password(body: PasswordBody, user: User = Depends(current_user), db: Session = Depends(get_db), _: None = Depends(require_csrf)):
    if not verify_password(body.current_password, user.password_hash):
        raise AppError(400, "Invalid password", "Current password is incorrect")
    user.password_hash = hash_password(body.new_password)
    db.commit()
    return {"ok": True}
