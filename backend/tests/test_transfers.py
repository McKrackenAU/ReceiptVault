from __future__ import annotations

from hashlib import sha256

from fastapi.testclient import TestClient


def _open(client: TestClient, headers, name: str, data: bytes):
    digest = sha256(data).hexdigest()
    return client.post(
        "/api/v1/transfers/uploads",
        json={"filename": name, "size": len(data), "sha256": digest},
        headers=headers,
    ).json()


def test_zero_and_one_byte(client: TestClient, owner):
    headers = {"X-CSRF-Token": owner["csrf"]}
    session = _open(client, headers, "empty.bin", b"")
    fin = client.post(f"/api/v1/transfers/uploads/{session['session_id']}/finalize", headers=headers)
    assert fin.status_code == 200
    one = b"Z"
    session = _open(client, headers, "one.bin", one)
    client.put(
        f"/api/v1/transfers/uploads/{session['session_id']}/chunks/0",
        headers={**headers, "X-Chunk-SHA256": sha256(one).hexdigest()},
        content=one,
    )
    assert client.post(f"/api/v1/transfers/uploads/{session['session_id']}/finalize", headers=headers).status_code == 200


def test_corrupt_and_missing_chunks(client: TestClient, owner):
    headers = {"X-CSRF-Token": owner["csrf"]}
    data = b"hello-world-bytes"
    session = _open(client, headers, "bad.bin", data)
    bad = client.put(
        f"/api/v1/transfers/uploads/{session['session_id']}/chunks/0",
        headers={**headers, "X-Chunk-SHA256": "0" * 64},
        content=data,
    )
    assert bad.status_code == 400
    missing = client.post(f"/api/v1/transfers/uploads/{session['session_id']}/finalize", headers=headers)
    assert missing.status_code == 409


def test_folder_package_unicode(client: TestClient, owner):
    headers = {"X-CSRF-Token": owner["csrf"]}
    pdf = b"%PDF-1.4 total AUD $5.00 From: Cafe\n"
    up = client.post("/api/v1/documents/upload", files={"file": ("Cafe receipt (über).pdf", pdf, "application/pdf")}, headers=headers)
    assert up.status_code == 200
    pkg = client.post("/api/v1/transfers/packages", json={"folder_path": "ATO Audit"}, headers=headers)
    assert pkg.status_code == 200
    down = client.get(f"/api/v1/transfers/packages/{pkg.json()['package_id']}/download", headers={"Range": "bytes=0-20"})
    assert down.status_code in {200, 206}
