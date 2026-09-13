from __future__ import annotations

import csv
import io
import json
import zipfile
from datetime import datetime, timezone

from openpyxl import Workbook
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from sqlalchemy.orm import Session

from app.config import Settings
from app.crypto import sha256_file
from app.models import AuditEvent, EvidenceObject, ExportRecord, ExtractedDocument, LineItem, Package
from app.services.evidence import evidence_path


def run_export(db: Session, settings: Settings, export: ExportRecord, package: Package) -> None:
    year = export.financial_year
    query = db.query(EvidenceObject).filter(EvidenceObject.deleted_at.is_(None), EvidenceObject.is_original.is_(True))
    if year:
        query = query.filter(EvidenceObject.financial_year == year)
    ids = export.selection.get("evidence_ids")
    if ids:
        query = query.filter(EvidenceObject.id.in_(ids))
    evidence = query.all()
    dest_dir = settings.staging_root / "exports"
    dest_dir.mkdir(parents=True, exist_ok=True)
    archive = dest_dir / f"{export.id}.zip"
    manifest = []
    csv_bytes = _expense_csv(db, evidence)
    xlsx_bytes = _expense_xlsx(db, evidence)
    json_bytes = _metadata_json(db, evidence)
    index_pdf = _index_pdf(evidence)
    audit_bytes = _audit_excerpt(db)
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        for obj in evidence:
            rel = f"originals/{obj.financial_year or 'unassigned'}/{obj.display_filename}"
            zf.write(evidence_path(settings, obj), rel)
            manifest.append({"path": rel, "sha256": obj.sha256, "bytes": obj.byte_count, "source_id": str(obj.id)})
        extras = {
            "expense-register.csv": csv_bytes,
            "expense-register.xlsx": xlsx_bytes,
            "extracted-metadata.json": json_bytes,
            "evidence-index.pdf": index_pdf,
            "audit-log-excerpt.csv": audit_bytes,
        }
        for name, payload in extras.items():
            zf.writestr(name, payload)
            from hashlib import sha256

            manifest.append({"path": name, "sha256": sha256(payload).hexdigest(), "bytes": len(payload), "source_id": "derived"})
        generated = datetime.now(timezone.utc).isoformat()
        zf.writestr("MANIFEST.json", json.dumps({"generated_at": generated, "entries": manifest}, indent=2))
    package.archive_relpath = f"exports/{export.id}.zip"
    package.byte_count = archive.stat().st_size
    package.sha256 = sha256_file(archive)
    package.manifest = {"entries": manifest, "generated_at": datetime.now(timezone.utc).isoformat()}
    package.status = "ready"
    package.progress = 100
    export.package_id = package.id


def _docs_for(db: Session, evidence: list[EvidenceObject]) -> dict:
    ids = [e.id for e in evidence]
    docs = db.query(ExtractedDocument).filter(ExtractedDocument.evidence_id.in_(ids)).all()
    return {d.evidence_id: d for d in docs}


def _expense_csv(db: Session, evidence: list[EvidenceObject]) -> bytes:
    docs = _docs_for(db, evidence)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "evidence_id",
            "filename",
            "financial_year",
            "merchant",
            "document_number",
            "date",
            "currency",
            "total",
            "line_description",
            "suggested_status",
            "decision",
            "work_purpose",
            "disclaimer",
        ]
    )
    disclaimer = "Review aid only — not tax advice or a final deduction."
    for obj in evidence:
        doc = docs.get(obj.id)
        lines = db.query(LineItem).filter(LineItem.document_id == doc.id).all() if doc else []
        if not lines:
            writer.writerow(
                [
                    obj.id,
                    obj.display_filename,
                    obj.financial_year,
                    (doc.fields_json or {}).get("merchant") if doc else "",
                    doc.document_number if doc else "",
                    doc.document_date if doc else "",
                    doc.currency if doc else "",
                    doc.total if doc else "",
                    "",
                    "",
                    "",
                    "",
                    disclaimer,
                ]
            )
            continue
        for line in lines:
            writer.writerow(
                [
                    obj.id,
                    obj.display_filename,
                    obj.financial_year,
                    (doc.fields_json or {}).get("merchant"),
                    doc.document_number,
                    doc.document_date,
                    doc.currency,
                    line.line_total,
                    line.raw_description,
                    line.suggested_status,
                    line.decision,
                    line.work_purpose or "",
                    disclaimer,
                ]
            )
    return buffer.getvalue().encode("utf-8")


def _expense_xlsx(db: Session, evidence: list[EvidenceObject]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Expense register"
    headers = [
        "Evidence ID",
        "File",
        "FY",
        "Merchant",
        "Number",
        "Date",
        "Currency",
        "Total",
        "Status",
        "Decision",
        "Source ID",
    ]
    ws.append(headers)
    docs = _docs_for(db, evidence)
    total = 0
    for obj in evidence:
        doc = docs.get(obj.id)
        amount = float(doc.total) if doc and doc.total is not None else 0
        total += amount
        ws.append(
            [
                str(obj.id),
                obj.display_filename,
                obj.financial_year,
                (doc.fields_json or {}).get("merchant") if doc else "",
                doc.document_number if doc else "",
                str(doc.document_date) if doc and doc.document_date else "",
                doc.currency if doc else "",
                amount,
                "",
                "",
                str(obj.id),
            ]
        )
    ws.auto_filter.ref = f"A1:K{max(len(evidence) + 1, 2)}"
    ws.append([])
    ws.append(["Grand total (not a final deduction)", "", "", "", "", "", "", total])
    ws.append(["This register is a review aid, not tax advice."])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _metadata_json(db: Session, evidence: list[EvidenceObject]) -> bytes:
    docs = _docs_for(db, evidence)
    payload = []
    for obj in evidence:
        doc = docs.get(obj.id)
        payload.append(
            {
                "evidence_id": str(obj.id),
                "sha256": obj.sha256,
                "bytes": obj.byte_count,
                "filename": obj.original_filename,
                "financial_year": obj.financial_year,
                "fy_source": obj.fy_source,
                "extracted": {
                    "merchant": (doc.fields_json or {}).get("merchant") if doc else None,
                    "number": doc.document_number if doc else None,
                    "total": str(doc.total) if doc and doc.total is not None else None,
                    "currency": doc.currency if doc else None,
                },
            }
        )
    return json.dumps(payload, indent=2).encode("utf-8")


def _index_pdf(evidence: list[EvidenceObject]) -> bytes:
    buf = io.BytesIO()
    pdf = canvas.Canvas(buf, pagesize=A4)
    pdf.setTitle("Evidence index")
    pdf.drawString(40, 800, "ReceiptVault evidence index — review aid, not tax advice")
    y = 770
    for obj in evidence:
        pdf.drawString(40, y, f"{obj.financial_year or '-'}  {obj.display_filename}  {obj.sha256[:12]}")
        y -= 16
        if y < 50:
            pdf.showPage()
            y = 800
    pdf.save()
    return buf.getvalue()


def _audit_excerpt(db: Session) -> bytes:
    events = db.query(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(1000).all()
    from app.services.audit import export_audit_csv

    return export_audit_csv(events)
