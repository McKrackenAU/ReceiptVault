from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import JobAttempt, ProcessingJob


def create_job(db: Session, kind: str, payload: dict, idempotency_key: str | None = None) -> ProcessingJob:
    if idempotency_key:
        existing = db.query(ProcessingJob).filter(ProcessingJob.idempotency_key == idempotency_key).one_or_none()
        if existing:
            return existing
    job = ProcessingJob(kind=kind, payload=payload, idempotency_key=idempotency_key, status="queued")
    db.add(job)
    db.flush()
    return job


def start_attempt(db: Session, job: ProcessingJob) -> JobAttempt:
    job.status = "running"
    job.started_at = job.started_at or datetime.now(timezone.utc)
    attempt = JobAttempt(job_id=job.id)
    db.add(attempt)
    db.flush()
    return attempt


def finish_attempt(db: Session, attempt: JobAttempt, success: bool, error: str | None = None) -> None:
    attempt.success = success
    attempt.error = error
    attempt.finished_at = datetime.now(timezone.utc)
