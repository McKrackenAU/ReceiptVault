from __future__ import annotations

import dramatiq

from app.config import get_settings
from app.db import SessionLocal
from app.models import Package, ProcessingJob
from app.services.packages import build_folder_package
from app.services.scan import run_scan
from app.services.transfers import cleanup_expired
from app.workers.broker import broker  # noqa: F401


@dramatiq.actor(max_retries=3)
def run_job(job_id: str) -> None:
    settings = get_settings()
    db = SessionLocal()
    try:
        job = db.get(ProcessingJob, job_id)
        if not job:
            return
        if job.kind == "scan":
            run_scan(db, settings, job)
        elif job.kind == "package":
            package = db.get(Package, job.payload.get("package_id"))
            if package:
                build_folder_package(db, settings, package)
                job.status = "succeeded"
                db.commit()
        elif job.kind == "export":
            job.status = "succeeded"
            db.commit()
        elif job.kind == "cleanup":
            cleanup_expired(db, settings)
            job.status = "succeeded"
            db.commit()
    finally:
        db.close()


@dramatiq.actor
def scheduled_incremental_scans() -> None:
    from app.models import MailboxAccount
    from app.services.jobs import create_job

    settings = get_settings()
    db = SessionLocal()
    try:
        for account in db.query(MailboxAccount).filter(MailboxAccount.disconnected_at.is_(None)):
            job = create_job(db, "scan", {"account_id": str(account.id), "folders": ["inbox"]}, f"incr-{account.id}")
            db.commit()
            run_scan(db, settings, job)
    finally:
        db.close()
