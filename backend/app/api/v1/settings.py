from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import client_ip, current_user, require_csrf, settings_dep
from app.config import Settings, reload_settings, upsert_env_key
from app.db import get_db
from app.models import AppSetting, User
from app.services.audit import record_audit
from app.services.backup import create_backup, restore_backup

router = APIRouter(tags=["settings"])


class SettingsBody(BaseModel):
    timezone: str | None = None
    selected_financial_year: str | None = None
    incremental_scan_minutes: int | None = None
    public_url: str | None = None
    ms_client_id: str | None = None
    ms_client_secret: str | None = None


class BackupBody(BaseModel):
    passphrase: str | None = None
    include_evidence: bool = True


class RestoreBody(BaseModel):
    path: str
    passphrase: str | None = None
    dry_run: bool = True
    confirm: bool = False


@router.get("/settings")
def get_settings_api(user: User = Depends(current_user), db: Session = Depends(get_db), settings: Settings = Depends(settings_dep)):
    stored = {row.key: row.value for row in db.query(AppSetting).all()}
    evidence_free = shutil.disk_usage(settings.evidence_root).free if settings.evidence_root.exists() else 0
    staging_used = _dir_size(settings.staging_root)
    return {
        "timezone": user.timezone,
        "public_url": settings.public_url,
        "graph_mock": settings.graph_mock,
        "oauth_redirect": settings.oauth_redirect_uri,
        "chunk_size_mib": settings.chunk_size_mib,
        "soft_delete_days": settings.soft_delete_days,
        "evidence_root": str(settings.evidence_root.resolve()),
        "evidence_free_bytes": evidence_free,
        "staging_bytes": staging_used,
        "selected_financial_year": (stored.get("ui") or {}).get("selected_financial_year"),
        "incremental_scan_minutes": settings.incremental_scan_minutes,
        "app_version": settings.app_version,
        "ms_client_configured": bool(settings.ms_client_id) or settings.graph_mock,
    }


@router.put("/settings")
def put_settings(body: SettingsBody, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db), settings: Settings = Depends(settings_dep), _: None = Depends(require_csrf)):
    if body.timezone:
        user.timezone = body.timezone
    row = db.get(AppSetting, "ui") or AppSetting(key="ui", value={})
    value = dict(row.value or {})
    if body.selected_financial_year:
        value["selected_financial_year"] = body.selected_financial_year
    row.value = value
    db.merge(row)
    if body.public_url:
        upsert_env_key("RECEIPTVAULT_PUBLIC_URL", body.public_url.rstrip("/"))
    if body.ms_client_id is not None:
        upsert_env_key("RECEIPTVAULT_MS_CLIENT_ID", body.ms_client_id.strip())
    if body.ms_client_secret:
        upsert_env_key("RECEIPTVAULT_MS_CLIENT_SECRET", body.ms_client_secret.strip())
    if body.public_url or body.ms_client_id is not None or body.ms_client_secret:
        settings = reload_settings()
    record_audit(
        db,
        event_type="settings_change",
        success=True,
        user_id=user.id,
        ip=client_ip(request, settings),
        metadata={"ms_client_updated": bool(body.ms_client_id or body.ms_client_secret)},
    )
    db.commit()
    return {
        "ok": True,
        "oauth_redirect": settings.oauth_redirect_uri,
        "ms_client_configured": bool(settings.ms_client_id) or settings.graph_mock,
    }


@router.post("/ops/backup")
def backup(body: BackupBody, request: Request, user: User = Depends(current_user), settings: Settings = Depends(settings_dep), db: Session = Depends(get_db), _: None = Depends(require_csrf)):
    result = create_backup(settings, body.passphrase, body.include_evidence)
    record_audit(db, event_type="backup", success=True, user_id=user.id, ip=client_ip(request, settings), metadata={"evidence_included": result["evidence_included"]})
    db.commit()
    return result


@router.post("/ops/restore")
def restore(body: RestoreBody, request: Request, user: User = Depends(current_user), settings: Settings = Depends(settings_dep), db: Session = Depends(get_db), _: None = Depends(require_csrf)):
    if not body.dry_run and not body.confirm:
        from app.errors import AppError

        raise AppError(400, "Confirmation required", "Set confirm=true to restore")
    result = restore_backup(settings, Path(body.path), body.passphrase, dry_run=body.dry_run)
    record_audit(db, event_type="restore", success=True, user_id=user.id, ip=client_ip(request, settings), metadata={"dry_run": body.dry_run})
    db.commit()
    return result


def _dir_size(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())
