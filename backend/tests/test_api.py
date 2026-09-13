from __future__ import annotations

from hashlib import sha256

from fastapi.testclient import TestClient


def test_live_health(client: TestClient):
    r = client.get("/health/live")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.json().get("version")
    assert "database" not in r.json()


def test_setup_login_and_pages(client: TestClient, owner):
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    dash = client.get("/api/v1/dashboard")
    assert dash.status_code == 200
    assert "not" in dash.json()["disclaimer"].lower()


def test_device_code_connects_mock_inbox(client: TestClient, owner):
    headers = {"X-CSRF-Token": owner["csrf"]}
    start = client.post("/api/v1/mail/connect/device", json={"label": "Phone Hotmail"}, headers=headers)
    assert start.status_code == 200
    body = start.json()
    assert body["user_code"]
    assert body["state"]
    polled = client.post("/api/v1/mail/connect/device/poll", json={"state": body["state"]}, headers=headers)
    assert polled.status_code == 200
    assert polled.json()["status"] == "connected"
    accounts = client.get("/api/v1/mail/accounts").json()["items"]
    assert any(a["label"] == "Phone Hotmail" for a in accounts)


def test_three_mock_accounts_and_scan(client: TestClient, owner):
    csrf = owner["csrf"]
    headers = {"X-CSRF-Token": csrf}
    for label, identity in [("Hotmail 1", "hotmail-one"), ("Hotmail 2", "hotmail-two"), ("Outlook", "outlook-work")]:
        start = client.post("/api/v1/mail/connect", json={"label": label, "mock_identity": identity}, headers=headers)
        assert start.status_code == 200
        cb = client.get(start.json()["authorize_url"], follow_redirects=False)
        assert cb.status_code in {302, 200}
    accounts = client.get("/api/v1/mail/accounts").json()["items"]
    assert len(accounts) >= 3
    first = accounts[0]
    dry = client.post("/api/v1/mail/scans", json={"account_id": first["id"], "dry_run": True}, headers=headers)
    assert dry.status_code == 200
    scan = client.post(
        "/api/v1/mail/scans",
        json={"account_id": first["id"], "folders": ["inbox"], "idempotency_key": "scan-once"},
        headers=headers,
    )
    assert scan.status_code == 200
    again = client.post(
        "/api/v1/mail/scans",
        json={"account_id": first["id"], "folders": ["inbox"], "idempotency_key": "scan-once"},
        headers=headers,
    )
    assert again.json()["job_id"] == scan.json()["job_id"]
    docs = client.get("/api/v1/documents").json()["items"]
    assert docs
    target = next((d for d in docs if d.get("merchant") or d.get("total")), docs[0])
    detail = client.get(f"/api/v1/documents/{target['id']}")
    assert detail.status_code == 200
    extracted = detail.json()["extracted"]
    assert extracted is None or extracted.get("disclaimer")


def test_manual_upload_and_export(client: TestClient, owner):
    csrf = owner["csrf"]
    headers = {"X-CSRF-Token": csrf}
    pdf = b"%PDF-1.4\n1 0 obj<<>>endobj\nFrom: Office Supplies Co\nABN: 12 345 678 901\nTax Invoice INV-9\nDate: 12/07/2024\nNotebook 1 x $20.00 $20.00\nSubtotal $20.00\nGST $2.00\nTotal AUD $22.00\n"
    r = client.post("/api/v1/documents/upload", files={"file": ("receipt.pdf", pdf, "application/pdf")}, headers=headers)
    assert r.status_code == 200
    exp = client.post("/api/v1/exports", json={"financial_year": "2024-25", "idempotency_key": "exp1"}, headers=headers)
    assert exp.status_code == 200
    assert exp.json()["sha256"]


def test_chunked_upload_resume(client: TestClient, owner):
    csrf = owner["csrf"]
    headers = {"X-CSRF-Token": csrf}
    payload = b"A" * 80
    digest = sha256(payload).hexdigest()
    session = client.post(
        "/api/v1/transfers/uploads",
        json={"filename": "tiny.bin", "size": 80, "sha256": digest},
        headers=headers,
    ).json()
    status = client.get(f"/api/v1/transfers/uploads/{session['session_id']}").json()
    assert status["missing"] == [0]
    chunk_hash = sha256(payload).hexdigest()
    put = client.put(
        f"/api/v1/transfers/uploads/{session['session_id']}/chunks/0",
        headers={**headers, "X-Chunk-SHA256": chunk_hash},
        content=payload,
    )
    assert put.status_code == 200
    fin = client.post(f"/api/v1/transfers/uploads/{session['session_id']}/finalize", headers=headers)
    assert fin.status_code == 200
    ev = fin.json()["evidence_id"]
    content = client.get(f"/api/v1/documents/{ev}/content", headers={"Range": "bytes=0-9"})
    assert content.status_code == 206
    assert content.content == b"A" * 10


def test_email_viewer_preview(client: TestClient, owner):
    csrf = owner["csrf"]
    headers = {"X-CSRF-Token": csrf}
    eml = (
        b"From: Shop <shop@example.com>\r\nTo: you@hotmail.com\r\n"
        b"Subject: Tax invoice INV-9\r\nMIME-Version: 1.0\r\n"
        b"Content-Type: text/html; charset=utf-8\r\n\r\n"
        b"<p>Please see attached</p><script>alert(1)</script>"
    )
    up = client.post("/api/v1/documents/upload", files={"file": ("invoice.eml", eml, "message/rfc822")}, headers=headers)
    assert up.status_code == 200
    ev = up.json()["evidence_id"]
    detail = client.get(f"/api/v1/documents/{ev}")
    assert detail.status_code == 200
    assert "related" in detail.json()
    preview = client.get(f"/api/v1/documents/{ev}/preview")
    assert preview.status_code == 200
    body = preview.json()
    assert body["viewer"] == "email"
    assert body["email"]["subject"] == "Tax invoice INV-9"
    page = client.get(f"/api/v1/documents/{ev}/html")
    assert page.status_code == 200
    assert b"Please see attached" in page.content
    assert b"<script" not in page.content.lower()
