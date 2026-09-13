from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.config import Settings
from app.models import (
    ExtractedDocument,
    ExtractedField,
    ExtractedPage,
    LineItem,
    Supplier,
)
from app.services.classify import classify_line_item, never_fabricate_purpose
from app.services.duplicates import link_duplicates
from app.services.evidence import add_to_folder, ensure_virtual_folder, store_original
from app.services.fy import assign_financial_year
from app.services.html_sanitize import html_to_text, sanitize_email_html
from app.services.ocr import extract_and_parse


def persist_extraction(db: Session, settings: Settings, evidence, parsed: dict, profile=None) -> ExtractedDocument:
    merchant = parsed.get("merchant")
    supplier = None
    if merchant:
        norm = merchant.strip().lower()
        supplier = db.query(Supplier).filter(Supplier.normalized_name == norm).one_or_none()
        if not supplier:
            supplier = Supplier(name=merchant, normalized_name=norm, abn=parsed.get("abn"))
            db.add(supplier)
            db.flush()
    fy, fy_source = assign_financial_year(parsed.get("document_date"), None)
    evidence.financial_year = fy
    evidence.fy_source = fy_source
    doc = ExtractedDocument(
        evidence_id=evidence.id,
        supplier_id=supplier.id if supplier else None,
        doc_type=parsed.get("doc_type"),
        document_number=parsed.get("document_number"),
        document_date=parsed.get("document_date"),
        currency=parsed.get("currency") or "AUD",
        subtotal=parsed.get("subtotal"),
        tax=parsed.get("tax"),
        total=parsed.get("total"),
        payment_method=parsed.get("payment_method"),
        payment_masked=parsed.get("payment_masked"),
        raw_text=parsed.get("raw_text"),
        normalized_text=parsed.get("normalized_text"),
        ocr_confidence=parsed.get("ocr_confidence"),
        engine_version=parsed.get("engine_version"),
        validation_flags=parsed.get("validation_flags") or [],
        fields_json={"merchant": merchant, "abn": parsed.get("abn")},
    )
    db.add(doc)
    db.flush()
    page = ExtractedPage(document_id=doc.id, page_number=1, text=parsed.get("raw_text"), confidence=parsed.get("ocr_confidence"))
    db.add(page)
    for name in ("merchant", "abn", "document_number", "total", "document_date"):
        value = parsed.get(name)
        db.add(
            ExtractedField(
                document_id=doc.id,
                name=name,
                raw_value=str(value) if value is not None else None,
                current_value=str(value) if value is not None else None,
                confidence=parsed.get("ocr_confidence"),
                page_number=1,
                history=[],
            )
        )
    duties = ""
    equipment = []
    if profile:
        duties = " ".join(p.duties or "" for p in getattr(profile, "periods", []) or [])
        equipment = getattr(profile, "common_equipment", []) or []
    for idx, item in enumerate(parsed.get("line_items") or []):
        suggestion = classify_line_item(
            item.get("raw_description") or "",
            merchant or "",
            item.get("line_total"),
            duties,
            equipment,
        )
        db.add(
            LineItem(
                document_id=doc.id,
                position=idx,
                raw_description=item.get("raw_description") or "Item",
                normalized_description=item.get("normalized_description") or item.get("raw_description") or "Item",
                quantity=item.get("quantity"),
                unit_price=item.get("unit_price"),
                line_total=item.get("line_total"),
                suggested_status=suggestion["status"],
                suggested_category=suggestion["category"],
                suggestion_confidence=Decimal(suggestion["confidence"]),
                explanation=suggestion["explanation"],
                work_purpose=never_fabricate_purpose(None),
            )
        )
    if not parsed.get("line_items") and parsed.get("total") is not None:
        suggestion = classify_line_item(merchant or "Receipt", merchant or "", parsed.get("total"), duties, equipment)
        db.add(
            LineItem(
                document_id=doc.id,
                position=0,
                raw_description=merchant or "Receipt",
                normalized_description=merchant or "Receipt",
                line_total=parsed.get("total"),
                suggested_status=suggestion["status"],
                suggested_category=suggestion["category"],
                suggestion_confidence=Decimal(suggestion["confidence"]),
                explanation=suggestion["explanation"],
            )
        )
    _place_in_folders(db, evidence, suggestion_status_for(doc, parsed))
    link_duplicates(db, evidence, doc)
    evidence.processing_history = list(evidence.processing_history or []) + [
        {"event": "extracted", "engine": parsed.get("engine_version"), "at": datetime.now(timezone.utc).isoformat()}
    ]
    return doc


def suggestion_status_for(doc: ExtractedDocument, parsed: dict) -> str:
    flags = parsed.get("validation_flags") or []
    if "low_ocr_confidence" in flags or "unreadable_pages" in flags:
        return "needs_review"
    return "needs_review"


def _place_in_folders(db: Session, evidence, status: str) -> None:
    year = evidence.financial_year or "unassigned"
    root = ensure_virtual_folder(db, "ATO Audit", "ATO Audit")
    fy = ensure_virtual_folder(db, f"ATO Audit/{year}", year, "ATO Audit")
    mapping = {
        "potentially_claimable": "Potentially Claimable",
        "needs_review": "Needs Review",
        "likely_private": "Likely Private",
    }
    status_label = mapping.get(status, "Needs Review")
    dest = ensure_virtual_folder(db, f"ATO Audit/{year}/{status_label}", status_label, fy.path)
    originals = ensure_virtual_folder(db, f"ATO Audit/{year}/Original Evidence", "Original Evidence", fy.path)
    add_to_folder(db, dest, evidence.id)
    if evidence.is_original:
        add_to_folder(db, originals, evidence.id)
    _ = root


def ingest_bytes(
    db: Session,
    settings: Settings,
    *,
    data: bytes,
    filename: str,
    kind: str = "upload",
    uploaded_by=None,
    source_account_id=None,
    source_message_id=None,
    parent_id=None,
    received_at=None,
) -> ExtractedDocument:
    evidence = store_original(
        db,
        settings,
        data=data,
        filename=filename,
        kind=kind,
        uploaded_by=uploaded_by,
        source_account_id=source_account_id,
        source_message_id=source_message_id,
        parent_id=parent_id,
    )
    parsed = extract_and_parse(data, filename)
    fy, src = assign_financial_year(parsed.get("document_date"), received_at)
    evidence.financial_year = fy
    evidence.fy_source = src
    existing = db.query(ExtractedDocument).filter(ExtractedDocument.evidence_id == evidence.id).one_or_none()
    if existing:
        return existing
    return persist_extraction(db, settings, evidence, parsed)


def snapshot_html_body(db: Session, settings: Settings, html: str, parent, filename: str = "email-body.pdf"):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    import io

    sanitized = sanitize_email_html(html)
    text = html_to_text(html)
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    pdf.setTitle("Email body snapshot")
    pdf.drawString(40, 800, "Derived PDF snapshot (not original evidence)")
    y = 770
    for line in text.split(". "):
        pdf.drawString(40, y, line[:110])
        y -= 16
        if y < 50:
            pdf.showPage()
            y = 800
    pdf.save()
    data = buffer.getvalue()
    derived = store_original(
        db,
        settings,
        data=data,
        filename=filename,
        kind="derived-pdf",
        parent_id=parent.id,
        derived_from_id=parent.id,
        is_original=False,
        source_account_id=parent.source_account_id,
        source_message_id=parent.source_message_id,
    )
    parsed = extract_and_parse(data, filename)
    parsed["raw_text"] = text
    persist_extraction(db, settings, derived, parsed)
    derived.processing_history = list(derived.processing_history or []) + [
        {"event": "derived_from_html", "parent": str(parent.id), "sanitized": True}
    ]
    return derived, sanitized
