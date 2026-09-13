from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

MELBOURNE = ZoneInfo("Australia/Melbourne")


def financial_year_for(moment: datetime) -> str:
    """Australian FY: 1 July – 30 June. Label is start-end, e.g. 2024-25."""
    local = moment
    if local.tzinfo is None:
        local = local.replace(tzinfo=timezone.utc)
    local = local.astimezone(MELBOURNE)
    if local.month >= 7:
        start = local.year
    else:
        start = local.year - 1
    end = start + 1
    return f"{start}-{str(end)[2:]}"


def assign_financial_year(document_date: datetime | None, received_at: datetime | None) -> tuple[str | None, str | None]:
    if document_date:
        return financial_year_for(document_date), "document_date"
    if received_at:
        return financial_year_for(received_at), "received_at"
    return None, None


def fy_bounds(label: str) -> tuple[datetime, datetime]:
    start_year = int(label.split("-")[0])
    start = datetime(start_year, 7, 1, tzinfo=MELBOURNE)
    end = datetime(start_year + 1, 6, 30, 23, 59, 59, tzinfo=MELBOURNE)
    return start, end
