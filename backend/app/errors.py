from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    def __init__(self, status: int, title: str, detail: str, extra: dict[str, Any] | None = None):
        self.status = status
        self.title = title
        self.detail = detail
        self.extra = extra or {}
        super().__init__(detail)


def problem(status: int, title: str, detail: str, instance: str | None = None, **extra: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "type": "about:blank",
        "title": title,
        "status": status,
        "detail": detail,
    }
    if instance:
        body["instance"] = instance
    body.update(extra)
    return body


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status,
        content=problem(exc.status, exc.title, exc.detail, instance=str(request.url.path), **exc.extra),
    )


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:  # noqa: ARG001
    return JSONResponse(
        status_code=500,
        content=problem(500, "Internal Server Error", "An unexpected error occurred.", instance=str(request.url.path)),
    )
