"""The rule layer. Extraction and the classifier propose; these decide.

Any failing rule routes the document to a person instead of into the
books - the correct outcome for messy input, not an error state.
"""

from __future__ import annotations

from dataclasses import dataclass

from .extract import DocumentRecord


@dataclass
class RuleResult:
    ok: bool
    rule: str
    detail: str

    def as_dict(self) -> dict:
        return {"ok": self.ok, "rule": self.rule, "detail": self.detail}


class SessionDuplicateStore:
    """Duplicates within one server run. Swap for something durable in production."""

    def __init__(self) -> None:
        self._seen: set[str] = set()

    def seen_before(self, key: str) -> bool:
        if key in self._seen:
            return True
        self._seen.add(key)
        return False


def duplicate_key(rec: DocumentRecord) -> str:
    return "|".join(str(v) for v in (rec.vendor, rec.number, rec.total)).lower()


def _near(a: float | None, b: float | None, tol: float = 0.02) -> bool:
    return a is not None and b is not None and abs(a - b) <= tol


def check(
    rec: DocumentRecord,
    doc_type: str,
    type_confidence: float,
    dupes: SessionDuplicateStore,
    min_type_confidence: float = 0.7,
) -> list[RuleResult]:
    out: list[RuleResult] = []

    out.append(
        RuleResult(True, "Vendor identified", rec.vendor)
        if rec.vendor
        else RuleResult(False, "Vendor not identified", "Nothing usable at the top of the document")
    )
    out.append(
        RuleResult(True, "Document number found", rec.number)
        if rec.number
        else RuleResult(False, "No document number", "Cannot be de-duplicated safely without one")
    )
    out.append(
        RuleResult(True, "Date read", rec.date)
        if rec.date
        else RuleResult(False, "Date not read", "A posting date must never be guessed")
    )

    if rec.subtotal is not None and rec.tax is not None and rec.total is not None:
        s = round(rec.subtotal + rec.tax, 2)
        out.append(
            RuleResult(
                _near(s, rec.total),
                "Subtotal plus tax equals the total",
                f"{rec.subtotal} + {rec.tax} = {s} vs stated {rec.total}",
            )
        )
    else:
        out.append(RuleResult(False, "Totals incomplete", "One of subtotal, tax or total was not read"))

    if rec.line_total is not None and rec.subtotal is not None:
        out.append(
            RuleResult(
                _near(rec.line_total, rec.subtotal, 0.05),
                "Line items add up to the subtotal",
                f"lines {rec.line_total} vs subtotal {rec.subtotal}",
            )
        )
    else:
        out.append(RuleResult(False, "Line items not summed", "Not enough line amounts were read to check"))

    if rec.number is not None and dupes.seen_before(duplicate_key(rec)):
        out.append(RuleResult(False, "Duplicate of a document already seen", "Same vendor, number and amount"))
    else:
        out.append(RuleResult(True, "Not a duplicate", "No match against documents already processed"))

    if type_confidence < min_type_confidence:
        out.append(
            RuleResult(
                False,
                "Document type uncertain",
                f"classifier confidence {type_confidence:.2f} for '{doc_type}' "
                f"is below {min_type_confidence}; a person should confirm",
            )
        )
    elif doc_type == "credit_note":
        out.append(
            RuleResult(True, "Recorded as a credit note", "Reduces the payable; never posted as a negative invoice")
        )
    else:
        out.append(
            RuleResult(True, f"Recorded as {doc_type.replace('_', ' ')}", f"classifier confidence {type_confidence:.2f}")
        )

    return out
