import pytest
from doc_intake_service.extract import amounts_in, extract, norm_date
from doc_intake_service.rules import duplicate_key, normalize_record, validate
from conftest import SAMPLES


def good():
    return normalize_record(extract((SAMPLES / "valid-invoice.txt").read_text()).as_dict())

def test_extracts_fields_and_never_reads_percent_as_money():
    row = good()
    assert (row["vendor"], row["number"], row["date"]) == ("Northwind Supplies", "NW-2026-0481", "2026-08-12")
    assert (row["subtotal"], row["tax"], row["total"], row["line_total"]) == ("624.00", "53.04", "677.04", "624.00")
    assert amounts_in("Tax 8.5% 53.04") == [53.04]
    assert amounts_in("Discount 10.00% applied") == []
    assert amounts_in("Overprecision 10.001; decimal comma 1.234,56; bad grouping 1,2,3.45") == []
    assert amounts_in("USD 1,234.56; INR 1,23,456.78") == [1234.56, 123456.78]
    assert all(c["ok"] for c in validate(row, "invoice", .9))

def test_duplicate_identity_has_currency_and_normalized_amount():
    row = good()
    assert duplicate_key(row) == duplicate_key(dict(row, vendor=" NORTHWIND   Supplies ", total=677.04))
    assert duplicate_key(row) != duplicate_key(dict(row, currency="INR"))
    assert duplicate_key(dict(row, number=None)) is None

@pytest.mark.parametrize("doc_type", ["contract", "statement", "receipt", "credit_note", "other"])
def test_noninvoice_types_are_explicitly_manual(doc_type):
    row = good()
    row.update(subtotal=None, tax=None, total=None, line_total=None)
    checks = validate(row, doc_type, .99)
    assert any(not c["ok"] and c["rule"] == "Manual review required" for c in checks)
    assert not any("Subtotal" in c["rule"] for c in checks)
    assert all(c["ok"] for c in validate(row, doc_type, .2, type_confirmed=True, manual_note="Read all pages and checked the metadata"))

@pytest.mark.parametrize("value", ["03/04/2026", "2026-02-30", None, "yesterday"])
def test_invalid_or_ambiguous_dates_block_approval(value):
    assert not next(c for c in validate(dict(good(), date=value), "invoice", .99) if c["rule"] == "Date is unambiguous")["ok"]

def test_no_currency_guess_and_mixed_currency_blocks():
    assert extract("Acme\nTotal 20.00").currency == "UNKNOWN"
    assert extract("Acme USD EUR\nTotal 20.00").currency == "UNKNOWN"
    assert extract("Acme INR\nTotal 20.00").currency == "INR"
    assert norm_date("Aug 12, 2026") == "2026-08-12"
    assert not all(c["ok"] for c in validate(dict(good(), currency="UNKNOWN"), "invoice", .99))

def test_low_confidence_and_negative_or_mismatched_amounts_block():
    assert not all(c["ok"] for c in validate(good(), "invoice", .3))
    assert all(c["ok"] for c in validate(good(), "invoice", .3, type_confirmed=True))
    assert not all(c["ok"] for c in validate(dict(good(), tax="-1.00"), "invoice", .99))
    assert not all(c["ok"] for c in validate(dict(good(), total="677.05"), "invoice", .99))
