from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.config import Settings
from app.crypto import decrypt_secret, encrypt_secret, sha256_bytes
from app.models import MailFolder, MailMessage, MailboxAccount, ProcessingJob, ScanCheckpoint
from app.services.candidates import detect_candidate
from app.services.graph import GraphClient, refresh_access
from app.services.html_sanitize import html_to_text
from app.services.ingest import ingest_bytes, snapshot_html_body
from app.services.evidence import store_original


def ensure_access(db: Session, settings: Settings, account: MailboxAccount) -> GraphClient:
    if account.mock_identity:
        return GraphClient(settings, "mock", account.mock_identity)
    token = decrypt_secret(account.access_token_encrypted) if account.access_token_encrypted else None
    expires = account.access_token_expires_at
    if not token or not expires or expires <= datetime.now(timezone.utc):
        refreshed = refresh_access(settings, decrypt_secret(account.refresh_token_encrypted))
        account.access_token_encrypted = encrypt_secret(refreshed["access_token"])
        if refreshed.get("refresh_token"):
            account.refresh_token_encrypted = encrypt_secret(refreshed["refresh_token"])
        account.last_token_refresh_at = datetime.now(timezone.utc)
        token = refreshed["access_token"]
    return GraphClient(settings, token, account.mock_identity)


def run_scan(db: Session, settings: Settings, job: ProcessingJob) -> None:
    account = db.get(MailboxAccount, job.payload["account_id"])
    if not account or account.disconnected_at:
        job.status = "failed"
        job.message = "account missing or disconnected"
        return
    folders = job.payload.get("folders") or ["inbox"]
    if job.payload.get("include_archive"):
        folders.append("archive")
    if job.payload.get("include_sent"):
        folders.append("sentitems")
    client = ensure_access(db, settings, account)
    account.scan_status = "running"
    job.status = "running"
    job.started_at = datetime.now(timezone.utc)
    for folder_name in folders:
        if job.cancel_requested:
            account.scan_status = "paused"
            job.status = "cancelled"
            db.commit()
            return
        _scan_folder(db, settings, job, account, client, folder_name)
    account.scan_status = "idle"
    account.last_scan_at = datetime.now(timezone.utc)
    job.status = "succeeded"
    job.progress = 100
    job.finished_at = datetime.now(timezone.utc)
    db.commit()


def _scan_folder(db, settings, job, account, client, folder_name: str) -> None:
    checkpoint = (
        db.query(ScanCheckpoint)
        .filter(ScanCheckpoint.account_id == account.id, ScanCheckpoint.job_id == job.id, ScanCheckpoint.folder_provider_id == folder_name)
        .one_or_none()
    )
    if not checkpoint:
        checkpoint = ScanCheckpoint(account_id=account.id, job_id=job.id, folder_provider_id=folder_name, cursor="0")
        db.add(checkpoint)
        db.flush()
    folder_row = (
        db.query(MailFolder).filter(MailFolder.account_id == account.id, MailFolder.provider_id == folder_name).one_or_none()
    )
    if not folder_row:
        folder_row = MailFolder(account_id=account.id, provider_id=folder_name, display_name=folder_name, well_known=folder_name)
        db.add(folder_row)
        db.flush()
    cursor = checkpoint.cursor
    for page, next_cursor in client.iter_messages(folder_name, cursor):
        if job.cancel_requested:
            return
        for message in page:
            _ingest_message(db, settings, account, folder_row, client, message)
            account.emails_examined += 1
            job.progress = min(99, account.emails_examined)
        checkpoint.cursor = next_cursor
        checkpoint.updated_at = datetime.now(timezone.utc)
        db.commit()
        if not next_cursor:
            break


def _ingest_message(db, settings, account, folder, client, message: dict) -> None:
    existing = (
        db.query(MailMessage)
        .filter(MailMessage.account_id == account.id, MailMessage.provider_id == message["id"])
        .one_or_none()
    )
    if existing:
        account.duplicates_skipped += 1
        return
    body = message.get("body", {}).get("content") or ""
    names = [att["name"] for att in message.get("attachments", [])]
    if not names:
        names = [att["name"] for att in client.attachments(message["id"])]
    att_text = ""
    result = detect_candidate(subject=message.get("subject") or "", sender=_sender(message), body_text=html_to_text(body), attachment_names=names, attachment_text=att_text)
    mime = client.message_mime(message["id"])
    rec = MailMessage(
        account_id=account.id,
        folder_id=folder.id,
        provider_id=message["id"],
        internet_message_id=message.get("internetMessageId"),
        subject=message.get("subject"),
        sender=_sender(message),
        recipients=message.get("toRecipients"),
        received_at=_parse_dt(message.get("receivedDateTime")),
        sent_at=_parse_dt(message.get("sentDateTime")),
        sha256=sha256_bytes(mime),
        is_candidate=result.is_candidate,
        candidate_score=result.score,
    )
    db.add(rec)
    db.flush()
    if not result.is_candidate:
        return
    account.candidates_found += 1
    eml = store_original(
        db,
        settings,
        data=mime,
        filename=f"{message['id']}.eml",
        kind="email",
        source_account_id=account.id,
        source_message_id=rec.id,
    )
    rec.evidence_id = eml.id
    attachments = client.attachments(message["id"])
    imported = False
    for att in attachments:
        data = att.get("contentBytes") or b""
        if not data:
            continue
        ingest_bytes(
            db,
            settings,
            data=data,
            filename=att.get("name") or "attachment.bin",
            kind="attachment",
            source_account_id=account.id,
            source_message_id=rec.id,
            parent_id=eml.id,
            received_at=rec.received_at,
        )
        imported = True
    if not attachments and body:
        snapshot_html_body(db, settings, body, eml)
        imported = True
    if imported:
        account.documents_imported += 1


def _sender(message: dict) -> str:
    from_ = message.get("from") or {}
    addr = from_.get("emailAddress") or {}
    return addr.get("address") or ""


def _parse_dt(value: str | None):
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def dry_run_estimate(client: GraphClient, folders: list[str]) -> dict:
    total = 0
    for folder in folders:
        for page, _ in client.iter_messages(folder, None, page_size=200):
            total += len(page)
            break
    return {"estimated_messages": total, "note": "Estimate from first page or mock corpus; Graph may have more."}
