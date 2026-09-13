from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

os.environ.setdefault("RECEIPTVAULT_MASTER_KEY", "test-master-key-please-change")
os.environ.setdefault("RECEIPTVAULT_GRAPH_MOCK", "true")
os.environ.setdefault("RECEIPTVAULT_COOKIE_SECURE", "false")

TEST_DB = "postgresql+psycopg://receiptvault:receiptvault_dev@127.0.0.1:5432/receiptvault_test"
os.environ["RECEIPTVAULT_DATABASE_URL"] = TEST_DB

ROOT = Path(__file__).resolve().parents[2]
VAR = ROOT / "var" / "test"
os.environ["RECEIPTVAULT_EVIDENCE_ROOT"] = str(VAR / "evidence")
os.environ["RECEIPTVAULT_DERIVED_ROOT"] = str(VAR / "derived")
os.environ["RECEIPTVAULT_STAGING_ROOT"] = str(VAR / "staging")
os.environ["RECEIPTVAULT_BACKUP_ROOT"] = str(VAR / "backups")


@pytest.fixture(scope="session")
def client():
    admin = create_engine("postgresql+psycopg://receiptvault:receiptvault_dev@127.0.0.1:5432/receiptvault")
    with admin.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(text("DROP DATABASE IF EXISTS receiptvault_test"))
        conn.execute(text("CREATE DATABASE receiptvault_test"))
    from app.config import get_settings

    get_settings.cache_clear()
    from app.db import Base, engine
    from app.main import app

    Base.metadata.create_all(bind=engine)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def owner(client: TestClient):
    me = client.get("/api/v1/auth/me")
    if me.status_code == 200:
        csrf = client.get("/api/v1/auth/csrf").json()["csrf"]
        return {"csrf": csrf}
    ready = client.get("/api/v1/auth/setup-required").json()
    if ready["required"]:
        r = client.post(
            "/api/v1/auth/setup",
            json={"username": "owner", "email": "owner@example.com", "password": "correct-horse-battery"},
        )
        assert r.status_code == 200
    else:
        r = client.post("/api/v1/auth/login", json={"username": "owner", "password": "correct-horse-battery"})
        assert r.status_code == 200
    csrf = r.json()["csrf"]
    return {"csrf": csrf}
