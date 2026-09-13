from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

_MONEY_RE = re.compile(
    r"(?P<currency>AUD|USD|NZD|EUR|GBP|CAD|SGD|\$|A\$|US\$)?\s*"
    r"(?P<sign>-)?"
    r"(?P<amount>\d{1,3}(?:,\d{3})*(?:\.\d{1,4})|\d+(?:\.\d{1,4})?)",
    re.I,
)

_CURRENCY_MAP = {
    "$": "AUD",
    "A$": "AUD",
    "US$": "USD",
    "AUD": "AUD",
    "USD": "USD",
    "NZD": "NZD",
    "EUR": "EUR",
    "GBP": "GBP",
    "CAD": "CAD",
    "SGD": "SGD",
}

TWOPLACE = Decimal("0.01")
FOURPLACE = Decimal("0.0001")


def parse_money(text: str | None, default_currency: str = "AUD") -> tuple[Decimal | None, str]:
    if not text:
        return None, default_currency
    match = _MONEY_RE.search(str(text).replace(" ", ""))
    if not match:
        cleaned = str(text).replace(",", "").replace("$", "").strip()
        try:
            return Decimal(cleaned).quantize(FOURPLACE), default_currency
        except (InvalidOperation, ValueError):
            return None, default_currency
    raw = match.group("amount").replace(",", "")
    sign = -1 if match.group("sign") else 1
    try:
        amount = (Decimal(raw) * sign).quantize(FOURPLACE)
    except InvalidOperation:
        return None, default_currency
    symbol = (match.group("currency") or default_currency).upper()
    currency = _CURRENCY_MAP.get(symbol, _CURRENCY_MAP.get(symbol.replace("$", ""), default_currency))
    if symbol in {"$", "A$"}:
        currency = default_currency
    return amount, currency


def quantize_money(value: Decimal | None) -> Decimal | None:
    if value is None:
        return None
    return value.quantize(FOURPLACE, rounding=ROUND_HALF_UP)


def almost_equal(left: Decimal | None, right: Decimal | None, tolerance: Decimal = Decimal("0.02")) -> bool:
    if left is None or right is None:
        return False
    return abs(left - right) <= tolerance
