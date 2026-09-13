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
from app.services.graph import GraphClient, exchange_code, mask_address
from app.services.graph_mock import MOCK_IDENTITIES
from app.services.jobs import create_job
from app.services.oauth import MS_SCOPES, authorize_url, new_state, pkce_pair
from app.services.scan import dry_run_estimate, ensure_access, run_scan

router = APIRouter(tags=["accounts"])


class ConnectBody(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    mock_identity: str | None = None


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
    if settings.graph_mock or body.mock_identity:
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
    )
    return {"authorize_url": url, "mock": False}


@router.get("/mail/oauth/callback")
def oauth_callback(code: str, state: str, request: Request, db: Session = Depends(get_db), settings: Settings = Depends(settings_dep)):
    row = db.query(OauthState).filter(OauthState.state == state).one_or_none()
    if not row or row.expires_at <= datetime.now(timezone.utc):
        raise AppError(400, "Invalid state", "OAuth state is missing or expired")
    tokens = exchange_code(settings, code, row.code_verifier)
    identity = tokens.get("mock_identity") or row.mock_identity
    client = GraphClient(settings, tokens.get("access_token", "mock"), identity)
    profile = client.profile()
    address = profile.get("mail") or profile.get("userPrincipalName") or profile.get("displayName")
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
