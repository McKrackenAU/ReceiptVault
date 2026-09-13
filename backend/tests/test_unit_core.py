from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest

from app.crypto import encrypt_secret, decrypt_secret, hash_password, verify_password, sha256_bytes, hash_token
from app.services.candidates import detect_candidate
from app.services.classify import classify_line_item, never_fabricate_purpose
from app.services.fy import assign_financial_year, financial_year_for
from app.services.money import parse_money
from app.services.oauth import pkce_pair
from app.services.parse import validate_arithmetic
from app.services.paths import UnsafePathError, safe_relpath, resolve_under
from app.services.transfers import _expected_part_count


def test_financial_year_july_boundary():
    assert financial_year_for(datetime(2024, 7, 1)) == "2024-25"
    assert financial_year_for(datetime(2024, 6, 30)) == "2023-24"
    fy, src = assign_financial_year(None, datetime(2024, 8, 1))
    assert fy == "2024-25" and src == "received_at"


def test_money_parsing_not_float():
    amount, currency = parse_money("Total AUD $1,234.50")
    assert amount == Decimal("1234.5000")
    assert currency == "AUD"
    assert isinstance(amount, Decimal)


def test_hashing_and_encryption(monkeypatch):
    monkeypatch.setenv("RECEIPTVAULT_MASTER_KEY", "unit-test-master-key")
    from app.config import get_settings

    get_settings.cache_clear()
    digest = sha256_bytes(b"hello")
    assert len(digest) == 64
    token = encrypt_secret("refresh-token-value")
    assert "refresh-token-value" not in token
    assert decrypt_secret(token) == "refresh-token-value"
    hashed = hash_password("super-secret-pass")
    assert verify_password("super-secret-pass", hashed)
    assert hash_token("abc") != "abc"


def test_duplicate_rules_and_candidates():
    strong = detect_candidate(subject="Tax invoice INV-9", body_text="ABN 12 345 678 901 Total AUD $22.00", attachment_names=["inv.pdf"])
    assert strong.is_candidate
    weak = detect_candidate(subject="Hello", body_text="See you Saturday")
    assert not weak.is_candidate
    low = detect_candidate(subject="Order", body_text="Amount due $15.00", attachment_names=["scan.jpg"])
    assert low.is_candidate


def test_safe_paths(tmp_path: Path):
    assert safe_relpath("ATO Audit/2024-25/file.pdf") == "ATO Audit/2024-25/file.pdf"
    with pytest.raises(UnsafePathError):
        safe_relpath("../etc/passwd")
    with pytest.raises(UnsafePathError):
        resolve_under(tmp_path, "../../etc/passwd")


def test_pkce_and_classification():
    verifier, challenge = pkce_pair()
    assert verifier != challenge and len(verifier) > 20
    suggestion = classify_line_item("Adobe Creative Cloud subscription", "Adobe")
    assert suggestion["status"] == "potentially_claimable"
    private = classify_line_item("Dinner tasting menu", "Restaurant")
    assert private["status"] == "likely_private"
    assert never_fabricate_purpose(None) is None
    assert "not tax" in suggestion["explanation"]["disclaimer"].lower()


def test_chunk_manifest_math():
    assert _expected_part_count(0, 16 * 1024 * 1024) == 0
    assert _expected_part_count(1, 16 * 1024 * 1024) == 1
    assert _expected_part_count(16 * 1024 * 1024, 16 * 1024 * 1024) == 1
    assert _expected_part_count(16 * 1024 * 1024 + 1, 16 * 1024 * 1024) == 2


def test_arithmetic_flags():
    flags = validate_arithmetic(
        [{"line_total": Decimal("10.00")}],
        Decimal("12.00"),
        Decimal("2.00"),
        Decimal("20.00"),
    )
    assert "line_totals_mismatch_subtotal" in flags
    assert "subtotal_tax_mismatch_total" in flags
