from __future__ import annotations

import logging
import re
import sys
from typing import Any

import structlog

_REDACT_KEYS = {
    "authorization",
    "cookie",
    "set-cookie",
    "refresh_token",
    "access_token",
    "password",
    "master_key",
    "csrf",
    "token",
    "secret",
    "email_body",
    "body_html",
    "document_content",
    "otp",
    "totp",
    "recovery_code",
}

_BEARER = re.compile(r"Bearer\s+[A-Za-z0-9._\-+=/]+", re.I)


def _redact_value(key: str, value: Any) -> Any:
    lowered = str(key).lower()
    if any(part in lowered for part in _REDACT_KEYS):
        return "[redacted]"
    if isinstance(value, str):
        return _BEARER.sub("Bearer [redacted]", value)
    return value


def redact_mapping(data: dict[str, Any]) -> dict[str, Any]:
    return {key: _redact_value(key, value) for key, value in data.items()}


def configure_logging(level: str = "INFO") -> None:
    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            timestamper,
            _RedactProcessor(),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, level.upper(), logging.INFO)),
        cache_logger_on_first_use=True,
    )


class _RedactProcessor:
    def __call__(self, logger, method_name, event_dict):  # noqa: ANN001
        return redact_mapping(event_dict)


def get_logger(name: str | None = None):
    return structlog.get_logger(name)
