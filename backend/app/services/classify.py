from __future__ import annotations

from decimal import Decimal

WORK_HINTS = (
    "software",
    "saas",
    "subscription",
    "laptop",
    "computer",
    "monitor",
    "keyboard",
    "office",
    "stationery",
    "printer",
    "domain",
    "hosting",
    "cloud",
    "aws",
    "azure",
    "training",
    "course",
    "conference",
    "membership",
    "professional",
    "accounting",
    "sim",
    "mobile",
    "internet",
    "broadband",
    "tools",
)

PRIVATE_HINTS = (
    "restaurant",
    "cafe",
    "coffee",
    "grocery",
    "supermarket",
    "woolworths",
    "coles",
    "liquor",
    "netflix",
    "spotify",
    "uber eats",
    "doordash",
    "cinema",
    "movie",
    "gift card",
    "jewellery",
    "clothing",
)

CATEGORY_MAP = {
    "software": "Software and subscriptions",
    "laptop": "Computers and equipment",
    "office": "Office supplies",
    "training": "Self-education and training",
    "membership": "Professional memberships",
    "mobile": "Phone and internet",
    "internet": "Phone and internet",
    "tools": "Tools and equipment",
}


def classify_line_item(
    description: str,
    merchant: str = "",
    total: Decimal | None = None,
    duties: str = "",
    equipment: list[str] | None = None,
) -> dict:
    text = f"{description} {merchant} {duties} {' '.join(equipment or [])}".lower()
    work_hits = [hint for hint in WORK_HINTS if hint in text]
    private_hits = [hint for hint in PRIVATE_HINTS if hint in text]
    missing = []
    if not description.strip():
        missing.append("line_description")
    status = "needs_review"
    confidence = Decimal("40.00")
    category = "Uncategorised"
    if work_hits and not private_hits:
        status = "potentially_claimable"
        confidence = Decimal("70.00")
        for hint in work_hits:
            if hint in CATEGORY_MAP:
                category = CATEGORY_MAP[hint]
                break
    elif private_hits and not work_hits:
        status = "likely_private"
        confidence = Decimal("65.00")
        category = "Likely private"
    elif work_hits and private_hits:
        status = "needs_review"
        confidence = Decimal("45.00")
        missing.append("work_versus_private_split")
    else:
        missing.append("work_purpose")
        missing.append("whether_reimbursed")

    return {
        "status": status,
        "category": category,
        "confidence": str(confidence),
        "explanation": {
            "why": "Rule-based review aid using merchant/line text and the taxpayer profile.",
            "facts_used": {"work_hints": work_hits, "private_hints": private_hits, "merchant": merchant},
            "rules_used": ["keyword_work", "keyword_private", "conservative_default"],
            "missing_facts": missing,
            "disclaimer": (
                "This is an organisational review aid, not tax or legal advice. "
                "You or your adviser must decide what to claim."
            ),
        },
    }


def never_fabricate_purpose(user_purpose: str | None) -> str | None:
    """Suggestions must not invent a work purpose."""
    if user_purpose and user_purpose.strip():
        return user_purpose.strip()
    return None
