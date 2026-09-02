from doc_intake_service.extract import amounts_in, extract, norm_date
from doc_intake_service.rules import SessionDuplicateStore, check

GOOD = """Northwind Supplies
INVOICE
Invoice No: NW-2026-0481
Invoice Date: 12 Aug 2026
Due Date: 11 Sep 2026
Filter cartridges 10 in 24 408.00
Sealing rings box of 50 6 171.00
Delivery 1 45.00
Subtotal 624.00
Tax 8.5% 53.04
Total Due 677.04"""

# The deliberate bad sample: 304.00 + 25.84 = 329.84, not 349.84.
BAD_TOTALS = """Ridgeway Trading
INVOICE
Invoice No: RT-9912
Invoice Date: 03 Aug 2026
Pallet wrap 500m 12 216.00
Strapping tape 4 88.00
Subtotal 304.00
Tax 8.5% 25.84
Total Due 349.84"""


def test_extracts_every_field_from_a_clean_invoice():
    r = extract(GOOD)
    assert r.vendor == "Northwind Supplies"
    assert r.number == "NW-2026-0481"
    assert r.date == "2026-08-12"
    assert r.due_date == "2026-09-11"
    assert (r.subtotal, r.tax, r.total) == (624.00, 53.04, 677.04)
    assert r.line_total == 624.00


def test_percentages_are_never_money():
    assert amounts_in("Tax 8.5% 53.04") == [53.04]
    assert amounts_in("Discount 10.00% applied") == []


def test_norm_date_both_orders():
    assert norm_date("12 Aug 2026") == "2026-08-12"
    assert norm_date("Aug 12, 2026") == "2026-08-12"
    assert norm_date("03/04/2026") == "03/04/2026"  # ambiguous: passed through


def test_all_rules_pass_on_the_clean_invoice():
    r = extract(GOOD)
    results = check(r, "invoice", 0.98, SessionDuplicateStore())
    assert [c.rule for c in results if not c.ok] == []


def test_totals_that_do_not_foot_are_caught():
    r = extract(BAD_TOTALS)
    results = check(r, "invoice", 0.98, SessionDuplicateStore())
    bad = [c for c in results if c.rule == "Subtotal plus tax equals the total"][0]
    assert not bad.ok
    assert "329.84" in bad.detail


def test_duplicate_flagged_on_second_sighting_only():
    store = SessionDuplicateStore()
    r = extract(GOOD)
    first = check(r, "invoice", 0.98, store)
    second = check(extract(GOOD), "invoice", 0.98, store)
    assert all(c.ok for c in first)
    assert any(c.rule.startswith("Duplicate") and not c.ok for c in second)


def test_low_classifier_confidence_is_a_failing_rule():
    r = extract(GOOD)
    results = check(r, "invoice", 0.41, SessionDuplicateStore())
    uncertain = [c for c in results if c.rule == "Document type uncertain"][0]
    assert not uncertain.ok
    assert "0.41" in uncertain.detail
