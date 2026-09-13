from __future__ import annotations

import re
from dataclasses import dataclass

_KEYWORDS = (
    r"receipt",
    r"invoice",
    r"tax[\s-]?invoice",
    r"\bpaid\b",
    r"payment",
    r"order confirmation",
    r"purchase",
    r"amount due",
    r"\bgst\b",
    r"\babn\b",
    r"total",
    r"subtotal",
    r"tax invoice",
    r"docket",
    r"statement",
)

_CURRENCY = re.compile(r"(?:AUD|USD|NZD|A\$|\$)\s*\d")
_INVOICE_NO = re.compile(r"(invoice|receipt|order)\s*(no\.?|number|#)\s*[:#]?\s*[A-Z0-9\-]+", re.I)
_ABN = re.compile(r"\bABN[:\s]*\d{2}\s*\d{3}\s*\d{3}\s*\d{3}\b", re.I)
_KEYWORD_RE = re.compile("|".join(_KEYWORDS), re.I)


@dataclass
class CandidateResult:
    is_candidate: bool
    score: int
    reasons: list[str]


def detect_candidate(
    *,
    subject: str = "",
    sender: str = "",
    body_text: str = "",
    attachment_names: list[str] | None = None,
    attachment_text: str = "",
) -> CandidateResult:
    attachment_names = attachment_names or []
    haystack = " ".join([subject, sender, body_text, " ".join(attachment_names), attachment_text])
    score = 0
    reasons: list[str] = []

    if _KEYWORD_RE.search(haystack):
        score += 30
        reasons.append("keyword")
    if _CURRENCY.search(haystack):
        score += 20
        reasons.append("currency_amount")
    if _INVOICE_NO.search(haystack):
        score += 20
        reasons.append("document_number")
    if _ABN.search(haystack):
        score += 15
        reasons.append("abn")
    if any(re.search(r"\.(pdf|jpe?g|png|webp|tiff?|heic|docx|xlsx)$", name, re.I) for name in attachment_names):
        score += 15
        reasons.append("attachment")
    if re.search(r"(table|qty|quantity|unit price|line total)", haystack, re.I):
        score += 10
        reasons.append("tabular_structure")

    # Conservative: low-confidence items still become candidates (false negatives are worse).
    is_candidate = score >= 15 or bool(_KEYWORD_RE.search(subject))
    if not is_candidate and attachment_names and _CURRENCY.search(haystack):
        is_candidate = True
        reasons.append("low_confidence_kept")
    return CandidateResult(is_candidate=is_candidate, score=score, reasons=reasons)
