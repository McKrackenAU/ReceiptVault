from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import client_ip, current_user, require_csrf, settings_dep
from app.config import Settings
from app.crypto import encrypt_secret, hash_token
from app.db import get_db
from app.errors import AppError
from app.models import MailboxAccount, OauthState, ProcessingJob, User
from app.services.audit import record_audit
from app.services.graph import GraphClient, GraphError, exchange_code, mask_address, poll_device_code, start_device_code
from app.services.graph_mock import MOCK_IDENTITIES
from app.services.jobs import create_job
from app.services.oauth import MS_SCOPES, authorize_url, new_state, pkce_pair
from app.services.scan import dry_run_estimate, ensure_access, run_scan

router = APIRouter(tags=["accounts"])


class ConnectBody(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    mock_identity: str | None = None
    login_hint: str | None = None


class DevicePollBody(BaseModel):
    state: str


class ScanBody(BaseModel):
    account_id: str
    folders: list[str] = ["inbox"]
    include_archive: bool = False
    include_sent: bool = False
    date_from: str | None = None
    date_to: str | None = None
    dry_run: bool = False
    idempotency_key: str | None = None


@router.get("/mail/accounts")
def list_accounts(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.query(MailboxAccount).filter(MailboxAccount.disconnected_at.is_(None)).all()
    return {"items": [_account_payload(a) for a in rows]}


@router.post("/mail/connect")
def connect_start(
    body: ConnectBody,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(settings_dep),
    _: None = Depends(require_csrf),
):
    verifier, challenge = pkce_pair()
    state = new_state()
    db.add(
        OauthState(
            state=state,
            code_verifier=verifier,
            label=body.label,
            mock_identity=body.mock_identity,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
        )
    )
    db.commit()
    # Mock inboxes are only for GRAPH_MOCK. Never treat a UI leftover field as
    # a real Microsoft sign-in — that skipped Hotmail login entirely.
    if settings.graph_mock:
        identity = body.mock_identity or "hotmail-one"
        if identity not in MOCK_IDENTITIES:
            raise AppError(400, "Unknown mock identity", "Use hotmail-one, hotmail-two, or outlook-work")
        url = f"/api/v1/mail/oauth/callback?code=mock-code-{identity}&state={state}"
        return {"authorize_url": url, "mock": True}
    if not settings.ms_client_id:
        raise AppError(400, "Missing Entra app", "Set RECEIPTVAULT_MS_CLIENT_ID or enable GRAPH_MOCK")
    url = authorize_url(
        tenant=settings.ms_tenant,
        client_id=settings.ms_client_id,
        redirect_uri=settings.oauth_redirect_uri,
        state=state,
        challenge=challenge,
        scopes=MS_SCOPES,
        login_hint=body.login_hint,
    )
    return {"authorize_url": url, "mock": False}


@router.post("/mail/connect/device")
def connect_device(
    body: ConnectBody,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(settings_dep),
    _: None = Depends(require_csrf),
):
    """Device-code Hotmail login. Works on http://192.168.x.x (Microsoft often rejects HTTP redirects)."""
    if settings.graph_mock:
        started = start_device_code(settings)
    elif not settings.ms_client_id:
        raise AppError(400, "Missing Entra app", "Save the Application (client) ID in Settings first")
    else:
        try:
            started = start_device_code(settings)
        except GraphError as exc:
            raise AppError(exc.status, "Microsoft device login failed", exc.detail) from exc
    state = new_state()
    expires = datetime.now(timezone.utc) + timedelta(seconds=int(started.get("expires_in") or 900))
    db.add(
        OauthState(
            state=state,
            code_verifier="",
            label=body.label,
            mock_identity=body.mock_identity if settings.graph_mock else None,
            device_code=started.get("device_code"),
            expires_at=expires,
        )
    )
    db.commit()
    return {
        "state": state,
        "user_code": started.get("user_code"),
        "verification_uri": started.get("verification_uri") or "https://www.microsoft.com/link",
        "verification_uri_complete": started.get("verification_uri_complete"),
        "interval": int(started.get("interval") or 5),
        "expires_in": int(started.get("expires_in") or 900),
        "message": started.get("message")
        or "Open the Microsoft link, enter this code, then sign in to Hotmail.",
        "mock": settings.graph_mock,
    }


@router.post("/mail/connect/device/poll")
def connect_device_poll(
    body: DevicePollBody,
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(settings_dep),
    _: None = Depends(require_csrf),
):
    row = db.query(OauthState).filter(OauthState.state == body.state).one_or_none()
    if not row or row.expires_at <= datetime.now(timezone.utc):
        raise AppError(400, "Login expired", "Start Sign in with Microsoft again")
    try:
        tokens = poll_device_code(settings, row.device_code or "mock-device")
    except GraphError as exc:
        detail = exc.detail.lower()
        if "authorization_pending" in detail or "authorization_pending" in exc.detail:
            return {"status": "pending"}
        if "slow_down" in detail:
            return {"status": "pending", "slow_down": True}
        if "expired" in detail:
            raise AppError(400, "Login expired", "The Microsoft code timed out. Start again.") from exc
        if "declined" in detail or "access_denied" in detail:
            raise AppError(400, "Sign-in cancelled", "Microsoft said the sign-in was declined.") from exc
        raise AppError(exc.status if exc.status < 500 else 400, "Microsoft sign-in failed", exc.detail) from exc
    account = _store_connected_account(db, settings, request, row, tokens)
    return {"status": "connected", "account": _account_payload(account)}


@router.get("/mail/oauth/callback")
def oauth_callback(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(settings_dep),
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
):
    if error:
        return RedirectResponse(url=f"/accounts?ms_error={error}", status_code=302)
    if not code or not state:
        raise AppError(400, "Invalid callback", "Microsoft did not return a code. Use device sign-in instead.")
    row = db.query(OauthState).filter(OauthState.state == state).one_or_none()
    if not row or row.expires_at <= datetime.now(timezone.utc):
        raise AppError(400, "Invalid state", "OAuth state is missing or expired")
    try:
        tokens = exchange_code(settings, code, row.code_verifier)
    except GraphError as exc:
        raise AppError(400, "Microsoft token exchange failed", exc.detail) from exc
    _store_connected_account(db, settings, request, row, tokens)
    return RedirectResponse(url="/accounts?connected=1", status_code=302)


@router.post("/mail/accounts/{account_id}/test")
def test_connection(account_id: str, user: User = Depends(current_user), db: Session = Depends(get_db), settings: Settings = Depends(settings_dep), _: None = Depends(require_csrf)):
    account = _get_account(db, account_id)
    client = ensure_access(db, settings, account)
    profile = client.profile()
    db.commit()
    return {"ok": True, "displayName": profile.get("displayName"), "mail": mask_address(profile.get("mail") or "")}


@router.post("/mail/accounts/{account_id}/disconnect")
def disconnect(account_id: str, request: Request, delete_evidence: bool = False, user: User = Depends(current_user), db: Session = Depends(get_db), settings: Settings = Depends(settings_dep), _: None = Depends(require_csrf)):
    account = _get_account(db, account_id)
    account.disconnected_at = datetime.now(timezone.utc)
    account.refresh_token_encrypted = None
    account.access_token_encrypted = None
    account.scan_status = "disconnected"
    record_audit(db, event_type="account_disconnected", success=True, target_id=account_id, ip=client_ip(request, settings), metadata={"delete_evidence": delete_evidence})
    db.commit()
    return {"ok": True, "evidence_retained": not delete_evidence}


@router.post("/mail/scans")
def start_scan(body: ScanBody, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db), settings: Settings = Depends(settings_dep), _: None = Depends(require_csrf)):
    account = _get_account(db, body.account_id)
    if body.dry_run:
        client = ensure_access(db, settings, account)
        estimate = dry_run_estimate(client, body.folders)
        db.commit()
        return {"dry_run": True, **estimate}
    job = create_job(
        db,
        "scan",
        {
            "account_id": str(account.id),
            "folders": body.folders,
            "include_archive": body.include_archive,
            "include_sent": body.include_sent,
            "date_from": body.date_from,
            "date_to": body.date_to,
        },
        idempotency_key=body.idempotency_key,
    )
    record_audit(db, event_type="scan_start", success=True, target_id=str(account.id), ip=client_ip(request, settings))
    db.commit()
    # Run inline for local/dev and tests; worker also consumes queued jobs.
    job = db.get(ProcessingJob, job.id)
    run_scan(db, settings, job)
    return {"job_id": str(job.id), "status": job.status, "progress": job.progress}


@router.post("/mail/scans/{job_id}/cancel")
def cancel_scan(job_id: str, user: User = Depends(current_user), db: Session = Depends(get_db), _: None = Depends(require_csrf)):
    job = db.get(ProcessingJob, job_id)
    if not job:
        raise AppError(404, "Not found", "Scan job missing")
    job.cancel_requested = True
    db.commit()
    return {"ok": True}


@router.get("/mail/jobs")
def list_jobs(user: User = Depends(current_user), db: Session = Depends(get_db)):
    jobs = db.query(ProcessingJob).order_by(ProcessingJob.created_at.desc()).limit(100).all()
    return {
        "items": [
            {
                "id": str(j.id),
                "kind": j.kind,
                "status": j.status,
                "progress": j.progress,
                "message": j.message,
                "created_at": j.created_at,
                "finished_at": j.finished_at,
            }
            for j in jobs
        ]
    }


@router.get("/mail/oauth/instructions")
def oauth_instructions(settings: Settings = Depends(settings_dep), user: User = Depends(current_user)):
    return {
        "redirect_uri": settings.oauth_redirect_uri,
        "authority": f"https://login.microsoftonline.com/{settings.ms_tenant}",
        "scopes": MS_SCOPES,
        "graph_mock": settings.graph_mock,
        "mock_identities": list(MOCK_IDENTITIES),
    }


def _store_connected_account(db: Session, settings: Settings, request: Request, row: OauthState, tokens: dict) -> MailboxAccount:
    identity = tokens.get("mock_identity") or row.mock_identity
    client = GraphClient(settings, tokens.get("access_token", "mock"), identity)
    profile = client.profile()
    address = profile.get("mail") or profile.get("userPrincipalName") or profile.get("displayName") or "unknown"
    account = MailboxAccount(
        label=row.label,
        masked_address=mask_address(address),
        address_hash=hash_token(address.lower()),
        provider_type=profile.get("account_type") or "personal",
        ms_user_id=profile.get("id"),
        refresh_token_encrypted=encrypt_secret(tokens.get("refresh_token") or "none"),
        access_token_encrypted=encrypt_secret(tokens.get("access_token") or "none"),
        access_token_expires_at=datetime.now(timezone.utc) + timedelta(seconds=int(tokens.get("expires_in") or 3600)),
        last_token_refresh_at=datetime.now(timezone.utc),
        mock_identity=identity,
    )
    db.add(account)
    record_audit(
        db,
        event_type="account_connected",
        success=True,
        ip=client_ip(request, settings),
        metadata={"label": row.label},
    )
    db.delete(row)
    db.commit()
    db.refresh(account)
    return account


def _get_account(db: Session, account_id: str) -> MailboxAccount:
    account = db.get(MailboxAccount, account_id)
    if not account or account.disconnected_at:
        raise AppError(404, "Not found", "Mailbox account missing")
    return account


def _account_payload(account: MailboxAccount) -> dict:
    return {
        "id": str(account.id),
        "label": account.label,
        "masked_address": account.masked_address,
        "provider_type": account.provider_type,
        "connected_at": account.connected_at,
        "last_token_refresh_at": account.last_token_refresh_at,
        "last_scan_at": account.last_scan_at,
        "scan_status": account.scan_status,
        "emails_examined": account.emails_examined,
        "candidates_found": account.candidates_found,
        "documents_imported": account.documents_imported,
        "duplicates_skipped": account.duplicates_skipped,
        "failures": account.failures,
        "mock_identity": account.mock_identity,
    }
