"""Conservative review policy. A passing check never implies approval."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from .extract import DocumentRecord

TYPES = {"invoice", "receipt", "statement", "contract", "credit_note", "other"}
CURRENCIES = {"USD", "EUR", "GBP", "INR"}
MONEY_FIELDS = {"subtotal", "tax", "total", "line_total"}

@dataclass
class RuleResult:
    ok: bool
    rule: str
    detail: str
    def as_dict(self):
        return vars(self)

def money(value):
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError("Amounts must be decimal values")
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or abs(amount) > Decimal("9999999999.99"):
            raise ValueError("Amount is non-finite or exceeds the supported range")
        if amount != amount.quantize(Decimal("0.01")):
            raise ValueError("Amounts support at most two decimal places")
        return amount
    except InvalidOperation as exc:
        raise ValueError("Invalid decimal amount") from exc

def normalize_record(record):
    allowed = set(DocumentRecord.__dataclass_fields__)
    if set(record) - allowed:
        raise ValueError("Unknown record fields")
    out = DocumentRecord().as_dict()
    out.update(record)
    for field in MONEY_FIELDS:
        value = money(out[field])
        out[field] = format(value, ".2f") if value is not None else None
    for field in ("vendor", "number", "date", "due_date", "currency"):
        value = out[field]
        if value is not None and (not isinstance(value, str) or len(value) > 300):
            raise ValueError(f"{field} must be a string of at most 300 characters")
        out[field] = value.strip() if isinstance(value, str) else value
    if type(out["line_items"]) is not int or not 0 <= out["line_items"] <= 10000:
        raise ValueError("line_items must be an integer between 0 and 10000")
    if not isinstance(out["warnings"], list) or any(not isinstance(v, str) for v in out["warnings"]):
        raise ValueError("warnings must be a list of strings")
    return out

def duplicate_key(rec):
    rec = rec.as_dict() if isinstance(rec, DocumentRecord) else rec
    if not rec.get("vendor") or not rec.get("number") or rec.get("total") is None:
        return None
    parts = [re.sub(r"\s+", " ", str(rec[k]).strip()).casefold() for k in ("vendor", "number", "currency")]
    parts.append(format(money(rec["total"]), ".2f"))
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False).encode()).hexdigest()

def validate(record, doc_type, confidence, *, type_confirmed=False, manual_note="", duplicate=False):
    out = []
    def add(ok, rule, detail):
        out.append(RuleResult(bool(ok), rule, str(detail)).as_dict())
    add(bool(record.get("vendor")), "Vendor identified", record.get("vendor") or "Enter the vendor or counterparty")
    try:
        value = record.get("date") or ""
        valid_date = date.fromisoformat(value).isoformat() == value
    except (ValueError, TypeError):
        valid_date = False
    add(valid_date, "Date is unambiguous", "Use a valid YYYY-MM-DD date; numeric ambiguous dates require correction")
    add(record.get("currency") in CURRENCIES, "Currency supported", "Explicit USD, EUR, GBP or INR required; no exchange conversion")
    add(not duplicate, "Not a duplicate", "Original-byte hash or vendor/number/currency/total matches an earlier document" if duplicate else "No earlier matching document")
    add(type_confirmed or confidence >= .7, "Document type confirmed", "Confirm the type when classifier confidence is below 0.70")
    if doc_type != "invoice":
        add(type_confirmed and len(manual_note.strip()) >= 10, "Manual review required", "Only invoices have accounting automation. Confirm type and record a review note of at least 10 characters.")
        return out
    add(bool(record.get("number")), "Document number found", "Invoice number is required")
    values = {k: money(record.get(k)) for k in MONEY_FIELDS}
    complete = all(values[k] is not None for k in ("subtotal", "tax", "total"))
    add(complete, "Totals complete", "Subtotal, tax and total must be present (use explicit zero tax)")
    add(complete and values["subtotal"] + values["tax"] == values["total"], "Subtotal plus tax equals the total", f"{record.get('subtotal')} + {record.get('tax')} vs {record.get('total')}")
    add(values["line_total"] is not None and values["line_total"] == values["subtotal"], "Line items add up to the subtotal", f"Lines {record.get('line_total')} vs subtotal {record.get('subtotal')}; correct against the original")
    add(all(v is None or v >= 0 for v in values.values()), "Invoice amounts are nonnegative", "Use manual credit-note review for credits")
    return out

class SessionDuplicateStore:
    """Legacy standalone helper. The application uses transactional SQLite."""
    def __init__(self):
        self.seen = set()
    def seen_before(self, key):
        prior = key in self.seen
        self.seen.add(key)
        return prior

def check(rec, doc_type, type_confidence, dupes, min_type_confidence=.7):
    key = duplicate_key(rec)
    results = validate(normalize_record(rec.as_dict()), doc_type, type_confidence,
                       duplicate=bool(key and dupes.seen_before(key)))
    return [RuleResult(**r) for r in results]
