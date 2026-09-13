from __future__ import annotations

import csv
import io
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditEvent


def record_audit(
    db: Session,
    *,
    event_type: str,
    success: bool,
    user_id: uuid.UUID | None = None,
    username: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    ip: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditEvent:
    event = AuditEvent(
        user_id=user_id,
        username=username,
        event_type=event_type,
        target_type=target_type,
        target_id=str(target_id) if target_id else None,
        success=success,
        ip=ip,
        metadata_json=metadata or {},
    )
    db.add(event)
    db.flush()
    return event


def export_audit_csv(events: list[AuditEvent]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["timestamp_utc", "username", "event_type", "target_type", "target_id", "success", "ip", "metadata"])
    for event in events:
        writer.writerow(
            [
                event.created_at.isoformat(),
                event.username or "",
                event.event_type,
                event.target_type or "",
                event.target_id or "",
                "true" if event.success else "false",
                event.ip or "",
                str(event.metadata_json),
            ]
        )
    return buffer.getvalue().encode("utf-8")
