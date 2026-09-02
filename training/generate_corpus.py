"""Generate the synthetic training corpus.

Every document is fictional - invented vendors, invented amounts. The point
of committing the generator instead of a data dump is that the corpus is
reproducible, inspectable, and honestly labelled for what it is: synthetic.
A model trained on this demonstrates the pipeline, not production accuracy.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

random.seed(2026)

VENDORS = [
    "Northwind Supplies", "Ridgeway Trading", "Harbor Coffee Roasters", "Cascade Tools Ltd",
    "Bluefield Stationers", "Portside Logistics", "Granite Office Interiors", "Fairway Electrical",
    "Lakeview Catering Co", "Summit Print Works", "Copperline Plumbing", "Anchor Freight Services",
    "Meridian Cleaning Group", "Oakfield Timber Merchants", "Beacon IT Services",
]
ITEMS = [
    "Filter cartridges", "Sealing rings", "Pallet wrap 500m", "Strapping tape", "Copy paper A4",
    "Toner cartridge", "Site visit labour", "Delivery", "Monthly service fee", "Cable ties",
    "Safety gloves", "Server maintenance", "Coffee beans 1kg", "Cleaning supplies", "Timber batten",
]
BANKS = ["First Harbour Bank", "Meridian Savings", "Union Coastal Bank", "Granite Trust"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _money(lo: float, hi: float) -> float:
    return round(random.uniform(lo, hi), 2)


def _date() -> str:
    return f"{random.randint(1, 28):02d} {random.choice(MONTHS)} 2026"


def make_invoice() -> str:
    vendor = random.choice(VENDORS)
    n_lines = random.randint(1, 5)
    lines, subtotal = [], 0.0
    for _ in range(n_lines):
        qty = random.randint(1, 30)
        amt = _money(20, 900)
        subtotal = round(subtotal + amt, 2)
        lines.append(f"{random.choice(ITEMS)}    {qty}    {amt:.2f}")
    tax = round(subtotal * random.choice([0.05, 0.085, 0.1, 0.2]), 2)
    total = round(subtotal + tax, 2)
    header = random.choice(["INVOICE", "TAX INVOICE", "Invoice"])
    return "\n".join(
        [
            vendor,
            header,
            f"Invoice No: {random.choice('ABCDEFG')}{random.choice('WXYZ')}-{random.randint(1000, 9999)}",
            f"Invoice Date: {_date()}",
            f"Due Date: {_date()}",
            *lines,
            f"Subtotal {subtotal:.2f}",
            f"Tax {tax:.2f}",
            f"{random.choice(['Total Due', 'Amount Due', 'Balance Due'])} {total:.2f}",
            random.choice(["Payment terms: Net 30.", "Payment terms: Net 14.", "Please quote the invoice number."]),
        ]
    )


def make_receipt() -> str:
    vendor = random.choice(VENDORS)
    n = random.randint(1, 4)
    lines, total = [], 0.0
    for _ in range(n):
        amt = _money(2, 80)
        total = round(total + amt, 2)
        lines.append(f"{random.randint(1, 3)}x {random.choice(ITEMS)}   {amt:.2f}")
    card = random.choice(["VISA", "MASTERCARD", "AMEX"])
    return "\n".join(
        [
            vendor.upper(),
            random.choice(["RECEIPT", "PAYMENT RECEIPT", "Receipt"]),
            f"{_date()} {random.randint(8, 20)}:{random.randint(10, 59)}",
            *lines,
            f"Total {total:.2f}",
            f"{card} **** {random.randint(1000, 9999)} - APPROVED",
            random.choice(["Thank you for your visit", "Thank you for your custom", "Keep this receipt"]),
        ]
    )


def make_statement() -> str:
    bank = random.choice(BANKS)
    opening = _money(500, 40000)
    rows, balance = [], opening
    for _ in range(random.randint(3, 7)):
        amt = _money(10, 900) * random.choice([-1, 1])
        balance = round(balance + amt, 2)
        rows.append(f"{_date()}  {random.choice(ITEMS)}  {amt:.2f}  {balance:.2f}")
    return "\n".join(
        [
            bank,
            random.choice(["ACCOUNT STATEMENT", "Monthly Statement", "STATEMENT OF ACCOUNT"]),
            f"Statement period ending {_date()}",
            f"Opening balance {opening:.2f}",
            *rows,
            f"Closing balance {balance:.2f}",
            random.choice(["Please review your transactions.", "Contact us about discrepancies within 30 days."]),
        ]
    )


def make_contract() -> str:
    a, b = random.sample(VENDORS, 2)
    return "\n".join(
        [
            random.choice(["SERVICE AGREEMENT", "ENGAGEMENT LETTER", "MASTER SERVICES AGREEMENT"]),
            f"This agreement is made between {a} and {b}.",
            f"Effective date: {_date()}",
            f"Term: {random.choice(['12 months', '24 months', 'until terminated'])}",
            f"Monthly fee: {_money(200, 5000):.2f} payable in arrears.",
            random.choice(
                [
                    "Either party may terminate with 30 days written notice.",
                    "This agreement is governed by the laws of the state of Delaware.",
                    "The parties agree to the scope of work described in Schedule A.",
                ]
            ),
            "Signed by the authorised representatives of both parties.",
        ]
    )


GENERATORS = {
    "invoice": make_invoice,
    "receipt": make_receipt,
    "statement": make_statement,
    "contract": make_contract,
}

PER_CLASS = 300


def main() -> None:
    out = Path(__file__).parent / "corpus.jsonl"
    with out.open("w", encoding="utf-8") as f:
        for label, gen in GENERATORS.items():
            for _ in range(PER_CLASS):
                f.write(json.dumps({"label": label, "text": gen()}) + "\n")
    print(f"wrote {PER_CLASS * len(GENERATORS)} documents -> {out}")


if __name__ == "__main__":
    main()
