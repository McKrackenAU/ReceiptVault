from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal

from app.services.money import almost_equal, parse_money, quantize_money

_ABN = re.compile(r"ABN[:\s]*([0-9]{2}\s*[0-9]{3}\s*[0-9]{3}\s*[0-9]{3})", re.I)
_DOCNO = re.compile(r"(?:invoice|receipt|tax invoice|order)\s*(?:no\.?|number|#)?\s*[:#]?\s*([A-Z0-9][A-Z0-9\-/]{2,})", re.I)
_DATE = re.compile(
    r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2}|\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{2,4})\b",
    re.I,
)
_TOTAL = re.compile(r"(?:grand\s+)?total(?:\s+aud)?\s*[: ]\s*([$\d,.\-]+)", re.I)
_SUBTOTAL = re.compile(r"sub[\s-]?total\s*[: ]\s*([$\d,.\-]+)", re.I)
_GST = re.compile(r"(?:gst|tax)\s*(?:amount)?\s*[: ]\s*([$\d,.\-]+)", re.I)
_MERCHANT = re.compile(r"^(?:from|merchant|supplier|sold by)[:\s]+(.+)$", re.I | re.M)
_LINE = re.compile(
    r"^(?P<desc>.+?)\s+(?P<qty>\d+(?:\.\d+)?)\s+[x@]\s*(?P<unit>[$\d,.]+)\s+(?P<total>[$\d,.]+)$",
    re.I | re.M,
)
_CARD = re.compile(r"(visa|mastercard|amex|eftpos|paypal|apple pay).*?(\d{4})", re.I)


def _parse_date(text: str) -> datetime | None:
    text = text.replace(",", " ")
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y", "%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def parse_receipt_text(text: str) -> dict:
    currency = "AUD"
    merchant = None
    merch_match = _MERCHANT.search(text)
    if merch_match:
        merchant = merch_match.group(1).strip()
    else:
        first = next((line.strip() for line in text.splitlines() if line.strip()), None)
        merchant = first

    abn = None
    abn_match = _ABN.search(text)
    if abn_match:
        abn = re.sub(r"\s+", "", abn_match.group(1))

    doc_no = None
    doc_match = _DOCNO.search(text)
    if doc_match:
        doc_no = doc_match.group(1)

    document_date = None
    date_match = _DATE.search(text)
    if date_match:
        document_date = _parse_date(date_match.group(1))

    total, currency = parse_money(_TOTAL.search(text).group(1) if _TOTAL.search(text) else None, currency)
    subtotal, _ = parse_money(_SUBTOTAL.search(text).group(1) if _SUBTOTAL.search(text) else None, currency)
    tax, _ = parse_money(_GST.search(text).group(1) if _GST.search(text) else None, currency)

    lines = []
    for match in _LINE.finditer(text):
        qty, _ = parse_money(match.group("qty"), currency)
        unit, _ = parse_money(match.group("unit"), currency)
        line_total, _ = parse_money(match.group("total"), currency)
        lines.append(
            {
                "raw_description": match.group("desc").strip(),
                "normalized_description": match.group("desc").strip(),
                "quantity": qty,
                "unit_price": unit,
                "line_total": line_total,
            }
        )

    payment = None
    masked = None
    card = _CARD.search(text)
    if card:
        payment = card.group(1)
        masked = f"•••• {card.group(2)}"

    flags = validate_arithmetic(lines, subtotal, tax, total)
    if document_date is None:
        flags.append("missing_date")
    if not merchant:
        flags.append("missing_supplier")
    if currency not in {"AUD", "USD", "NZD", "EUR", "GBP", "CAD", "SGD"}:
        flags.append("ambiguous_currency")

    return {
        "merchant": merchant,
        "abn": abn,
        "document_number": doc_no,
        "document_date": document_date,
        "currency": currency,
        "subtotal": quantize_money(subtotal),
        "tax": quantize_money(tax),
        "total": quantize_money(total),
        "payment_method": payment,
        "payment_masked": masked,
        "line_items": lines,
        "validation_flags": flags,
        "doc_type": guess_doc_type(text),
    }


def guess_doc_type(text: str) -> str:
    lowered = text.lower()
    if "tax invoice" in lowered:
        return "tax_invoice"
    if "invoice" in lowered:
        return "invoice"
    if "receipt" in lowered:
        return "receipt"
    return "unknown"


def validate_arithmetic(
    lines: list[dict],
    subtotal: Decimal | None,
    tax: Decimal | None,
    total: Decimal | None,
) -> list[str]:
    flags: list[str] = []
    line_sum = Decimal("0")
    have_lines = False
    for item in lines:
        if item.get("line_total") is not None:
            line_sum += item["line_total"]
            have_lines = True
    if have_lines and subtotal is not None and not almost_equal(line_sum, subtotal):
        flags.append("line_totals_mismatch_subtotal")
    if subtotal is not None and tax is not None and total is not None and not almost_equal(subtotal + tax, total, Decimal("0.05")):
        flags.append("subtotal_tax_mismatch_total")
    if total is None:
        flags.append("missing_total")
    return flags
