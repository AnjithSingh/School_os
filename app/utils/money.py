"""Money helpers. All stored values are integer paise."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def to_paise(value) -> int:
    """Accept '1250.50', 1250.5 or Decimal and return 125050 paise."""
    if value is None or value == "":
        return 0
    try:
        amount = Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        raise ValueError("Enter a valid amount.")
    if amount < 0:
        raise ValueError("Amount cannot be negative.")
    return int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def from_paise(paise: int | None) -> Decimal:
    return (Decimal(paise or 0) / Decimal(100)).quantize(Decimal("0.01"))


def _indian_group(value: str) -> str:
    """Group the integer part Indian style: 12,34,567."""
    if len(value) <= 3:
        return value
    head, tail = value[:-3], value[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ",".join(parts) + "," + tail


def format_money(paise: int | None, symbol: str = "₹", decimals: bool = True) -> str:
    amount = from_paise(paise)
    negative = amount < 0
    amount = abs(amount)
    whole, _, fraction = f"{amount:.2f}".partition(".")
    text = _indian_group(str(int(whole)))
    if decimals:
        text = f"{text}.{fraction}"
    return f"{'-' if negative else ''}{symbol}{text}"


def format_percent(value: float | None, digits: int = 1) -> str:
    if value is None:
        return "—"
    return f"{value:.{digits}f}%"
