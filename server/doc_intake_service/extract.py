"""Line-based field extraction.

The same conservative parsing rules as the sibling TypeScript library
(github.com/mithundas79/doc-intake), ported to Python: money is only ever
read from two-decimal tokens so a percentage can never become an amount,
and ``Total`` is never matched inside ``Subtotal``.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

AMOUNT = re.compile(r"(-?\d[\d,]*\.\d{2})(?!\s*%)")
DOC_LABEL = re.compile(
    r"\b(tax\s+)?(invoice|receipt|bill|statement|credit\s*(note|memo)|purchase\s*order|remittance)\b",
    re.IGNORECASE,
)
NUMBER = re.compile(
    r"(?:invoice|receipt|statement|credit\s*note)\s*(?:no|number|#)?\s*[:.]?\s*([A-Z0-9][A-Z0-9\-/]{3,})",
    re.IGNORECASE,
)
DATE = re.compile(
    r"(\d{4}-\d{2}-\d{2}|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}|\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}|[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4})"
)
MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]


@dataclass
class DocumentRecord:
    vendor: str | None = None
    number: str | None = None
    date: str | None = None
    due_date: str | None = None
    currency: str = "UNKNOWN"
    subtotal: float | None = None
    tax: float | None = None
    total: float | None = None
    line_total: float | None = None
    line_items: int = 0
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


def amounts_in(line: str) -> list[float]:
    return [float(m.replace(",", "")) for m in AMOUNT.findall(line)]


def _last_amount(line: str) -> float | None:
    found = amounts_in(line)
    return found[-1] if found else None


def _month_num(name: str) -> str | None:
    try:
        return f"{MONTHS.index(name[:3].lower()) + 1:02d}"
    except ValueError:
        return None


def norm_date(value: str | None) -> str | None:
    """Normalise '12 Aug 2026' / 'Aug 12, 2026' to ISO; pass others through."""
    if not value:
        return None
    m = re.fullmatch(r"(\d{1,2})\s+([A-Za-z]{3,9})\s+(\d{4})", value)
    if m and (mm := _month_num(m.group(2))):
        return f"{m.group(3)}-{mm}-{int(m.group(1)):02d}"
    m = re.fullmatch(r"([A-Za-z]{3,9})\s+(\d{1,2}),?\s+(\d{4})", value)
    if m and (mm := _month_num(m.group(1))):
        return f"{m.group(3)}-{mm}-{int(m.group(2)):02d}"
    return value


def clean_vendor_line(text: str | None) -> str | None:
    v = re.sub(r"\s+", " ", str(text or "")).strip()
    m = DOC_LABEL.search(v)
    if m:
        v = v[: m.start()].strip()
    v = re.sub(r"[|,;:\-–—\s]+$", "", v).strip()
    if not re.search(r"[A-Za-z]{3}", v):
        return None
    if re.match(r"^\d", v):
        return None
    if re.match(r"^(description|qty|quantity|amount|date|due|page|total|subtotal)\b", v, re.IGNORECASE):
        return None
    return v


def pick_vendor(lines: list[str]) -> str | None:
    for line in lines[:6]:
        if v := clean_vendor_line(line):
            return v
    return None


def extract(text: str) -> DocumentRecord:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    rec = DocumentRecord(vendor=pick_vendor(lines))

    currencies = set()
    for code, marker in (("USD", "$"), ("EUR", "€"), ("GBP", "£"), ("INR", "₹")):
        if marker in text or re.search(r"\b" + code + r"\b", text):
            currencies.add(code)
    if len(currencies) == 1:
        rec.currency = currencies.pop()

    line_sum = 0.0
    for raw in lines:
        line = re.sub(r"\s+", " ", raw)
        low = line.lower()

        if rec.number is None:
            m = NUMBER.search(line)
            if m and "date" not in m.group(1).lower():
                rec.number = m.group(1).strip()
        if rec.date is None and re.search(r"invoice\s*date|^date\b", low):
            m = DATE.search(line)
            rec.date = norm_date(m.group(1) if m else None)
        if rec.due_date is None and "due date" in low:
            m = DATE.search(line)
            rec.due_date = norm_date(m.group(1) if m else None)

        amount = _last_amount(line)
        if amount is None:
            continue
        if "subtotal" in low or "sub total" in low:
            rec.subtotal = amount
        elif re.search(r"\b(tax|vat|gst)\b", low):
            rec.tax = amount
        elif re.search(r"\btotal\b|\bbalance due\b|\bamount due\b", low):
            rec.total = amount
        elif re.search(r"payment|terms|thank|page|invoice no|date", low):
            continue
        else:
            rec.line_items += 1
            line_sum += amount

    if rec.line_items:
        rec.line_total = round(line_sum, 2)
    for name in ("subtotal", "tax", "total"):
        v = getattr(rec, name)
        if v is not None:
            setattr(rec, name, round(v, 2))
    return rec
