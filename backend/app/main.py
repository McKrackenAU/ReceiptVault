from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api.v1 import router as api_router
from app.config import get_settings
from app.db import Base, engine
from app.errors import AppError, app_error_handler, problem, unhandled_error_handler
from app.logging import configure_logging, get_logger

settings = get_settings()
configure_logging(settings.log_level)
log = get_logger("receiptvault")

app = FastAPI(title="ReceiptVault", version=__version__, openapi_url="/api/v1/openapi.json", docs_url="/api/docs")
app.add_exception_handler(AppError, app_error_handler)
app.add_exception_handler(Exception, unhandled_error_handler)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.public_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router)

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if FRONTEND.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND / "assets"), name="assets")


SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
        "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'self'"
    ),
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


@app.middleware("http")
async def security_and_correlation(request: Request, call_next):
    correlation = request.headers.get("x-request-id") or str(uuid.uuid4())
    response = await call_next(request)
    response.headers["X-Request-ID"] = correlation
    for key, value in SECURITY_HEADERS.items():
        response.headers.setdefault(key, value)
    return response


@app.get("/health/live")
def live():
    return {"status": "ok", "version": settings.app_version}


@app.on_event("startup")
def startup():
    settings.ensure_dirs()
    Base.metadata.create_all(bind=engine)
    log.info("receiptvault_started", version=__version__, env=settings.env)


@app.get("/")
@app.get("/{full_path:path}")
def spa(full_path: str = ""):
    if full_path.startswith("api/") or full_path.startswith("health"):
        return JSONResponse(problem(404, "Not found", "No such API route"), status_code=404)
    index = FRONTEND / "index.html"
    if index.exists() and not full_path.startswith("assets/"):
        return FileResponse(index)
    html = (
        "<!doctype html><html><head><meta charset='utf-8'><title>ReceiptVault</title></head>"
        "<body style='font-family:system-ui;padding:2rem'>"
        "<h1>ReceiptVault</h1>"
        "<p>The API is running. The web UI build is missing on this server "
        "(<code>frontend/dist</code>). Open <a href='/api/docs'>/api/docs</a> "
        "or rebuild the UI with <code>npm run build</code> in /opt/receiptvault/frontend.</p>"
        "</body></html>"
    )
    return HTMLResponse(html)
