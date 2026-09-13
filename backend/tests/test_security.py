from __future__ import annotations

from fastapi.testclient import TestClient

from app.services.html_sanitize import sanitize_email_html
from app.services.paths import UnsafePathError, safe_relpath
from app.logging import redact_mapping


def test_csrf_required(client: TestClient, owner):
    client.cookies.set("rv_csrf", "", domain="testserver")
    client.cookies.delete("rv_csrf")
    r = client.post("/api/v1/auth/logout")
    assert r.status_code == 403


def test_csrf_cookie_allows_post(client: TestClient, owner):
    client.get("/api/v1/auth/me")
    r = client.post("/api/v1/auth/logout")
    assert r.status_code in {200, 204}


def test_unauthorized_object_access(client: TestClient):
    client.cookies.clear()
    r = client.get("/api/v1/documents/00000000-0000-0000-0000-000000000001")
    assert r.status_code == 401


def test_html_sanitizer_strips_xss():
    html = '<p>Invoice</p><script>alert(1)</script><img src="https://evil.example/x"><a href="javascript:alert(1)">x</a>'
    cleaned = sanitize_email_html(html)
    assert "script" not in cleaned.lower()
    assert "<img" not in cleaned.lower()
    assert "javascript:" not in cleaned.lower()
    assert "Invoice" in cleaned


def test_zip_slip_rejected():
    try:
        safe_relpath("ok/../../evil")
        raised = False
    except UnsafePathError:
        raised = True
    assert raised


def test_malicious_filename_and_log_redaction():
    from app.services.paths import safe_filename

    assert ".." not in safe_filename("../../secret.exe")
    redacted = redact_mapping({"authorization": "Bearer abc", "password": "x", "note": "ok"})
    assert redacted["authorization"] == "[redacted]"
    assert redacted["password"] == "[redacted]"
    assert redacted["note"] == "ok"


def test_security_headers(client: TestClient):
    r = client.get("/health/live")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert "Content-Security-Policy" in r.headers
    assert r.headers["X-Frame-Options"] == "DENY"
