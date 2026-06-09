"""Unit tests for the Paytm parser on fully synthetic, hand-built layout text.

No real statement data is used here. The text is assembled with a column
placement helper that mimics ``pdftotext -layout`` output, so the parser's
trickier behaviours (year-from-period, Rs. integer/decimal amounts, unsigned
credits, wrapped-name stitching, and no-leak from adjacent columns) are covered
without depending on a real PDF.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from parsers.paytm_parser import parse_paytm_pdf_text  # noqa: E402

# Column layout (character columns) mimicking pdftotext -layout of Paytm.
_DATE, _DETAILS, _NOTES, _ACCOUNT, _AMOUNT = 2, 18, 49, 66, 82


def _line(*cells: tuple[int, str]) -> str:
    """Place each (column, text) cell at its column, like a layout-extracted row."""
    s = ""
    for col, text in cells:
        s = (s.ljust(col) if len(s) < col else s + "  ") + text
    return s


def _build(*transactions: list[str]) -> str:
    header = [
        "                 PII-FREE SYNTHETIC HEADER",
        "Paytm Statement for",
        _line((_DETAILS, "5 JAN'26 - 1 FEB'26"), (_AMOUNT - 10, "- Rs.1,500.00"), (_AMOUNT + 8, "+ Rs.0")),
        _line((_DETAILS, "3 Payments made"), (_AMOUNT + 8, "0 Payment received")),
        "",
        "Passbook Payments History",
        _line((_DATE, "Date &"), (_DETAILS, "Transaction Details"),
              (_NOTES, "Notes & Tags"), (_ACCOUNT, "Your Account"), (_AMOUNT, "Amount")),
        _line((_DATE, "Time")),
        "",
    ]
    body: list[str] = []
    for block in transactions:
        body.extend(block)
        body.append("")
    return "\n".join(header + body) + "\n"


def test_year_from_period_and_basic_fields():
    txn = [
        _line((_DATE, "05 Jan"), (_DETAILS, "Paid to Acme Store"),
              (_NOTES, "Tag:"), (_ACCOUNT, "UPI Lite"), (_AMOUNT, "- Rs.250.00")),
        _line((_DATE, "1:30 PM")),
        _line((_DETAILS, "UPI ID: acme.store@ybl"), (_NOTES, "# Shopping")),
        _line((_DETAILS, "UPI Ref No: 100000000001")),
    ]
    rows = parse_paytm_pdf_text(_build(txn))
    assert len(rows) == 1
    r = rows[0]
    assert r["date"].startswith("2026-01-05T13:30:00")  # year from period, 12h->24h
    assert r["amount"] == 250.0
    assert r["debit_credit"] == "DEBIT"
    assert r["beneficiary"] == "Acme Store"


def test_integer_and_grouped_amounts():
    txn = [
        _line((_DATE, "06 Jan"), (_DETAILS, "Paid to Big Mart"),
              (_NOTES, "Tag:"), (_ACCOUNT, "UPI Lite"), (_AMOUNT, "- Rs.1,700")),
        _line((_DATE, "9:00 AM")),
        _line((_DETAILS, "UPI Ref No: 100000000002")),
    ]
    rows = parse_paytm_pdf_text(_build(txn))
    assert rows[0]["amount"] == 1700.0


def test_unsigned_amount_is_credit():
    txn = [
        _line((_DATE, "07 Jan"), (_DETAILS, "Automatic Add Money for UPI Lite"),
              (_NOTES, "Note: Topup"), (_ACCOUNT, "State Bank"), (_AMOUNT, "Rs.2,000")),
        _line((_DATE, "10:10 AM")),
        _line((_DETAILS, "UPI Ref No: 100000000003")),
    ]
    rows = parse_paytm_pdf_text(_build(txn))
    assert rows[0]["debit_credit"] == "CREDIT"
    assert rows[0]["amount"] == 2000.0
    assert rows[0]["beneficiary"] == "Automatic Add Money for UPI Lite"


def test_wrapped_name_is_stitched_across_lines():
    # The counterparty name wraps onto the time line in the details column.
    txn = [
        _line((_DATE, "08 Jan"), (_DETAILS, "Paid to Very Long Merchant"),
              (_NOTES, "Tag:"), (_ACCOUNT, "UPI Lite"), (_AMOUNT, "- Rs.99.00")),
        _line((_DATE, "2:45 PM"), (_DETAILS, "Name Continued")),
        _line((_DETAILS, "UPI ID: longmerchant@okaxis"), (_NOTES, "# Food")),
        _line((_DETAILS, "UPI Ref No: 100000000004")),
    ]
    rows = parse_paytm_pdf_text(_build(txn))
    assert rows[0]["beneficiary"] == "Very Long Merchant Name Continued"


def test_adjacent_note_column_does_not_leak_into_name():
    # A continuation in the Notes column (far from the details column) must NOT
    # be appended to the counterparty name.
    txn = [
        _line((_DATE, "09 Jan"), (_DETAILS, "Paid to Corner Shop"),
              (_NOTES, "Note: Pay to"), (_ACCOUNT, "UPI Lite"), (_AMOUNT, "- Rs.40.00")),
        _line((_DATE, "8:00 PM"), (_NOTES, "Local Vendor")),
        _line((_DETAILS, "UPI Ref No: 100000000005")),
    ]
    rows = parse_paytm_pdf_text(_build(txn))
    assert rows[0]["beneficiary"] == "Corner Shop"


def test_period_year_boundary_resolution():
    # Period spanning a year boundary: Dec rows -> start year, Jan rows -> end year.
    header_period = _line(
        (_DETAILS, "28 DEC'25 - 5 JAN'26"), (_AMOUNT - 10, "- Rs.90.00"), (_AMOUNT + 8, "+ Rs.0")
    )
    dec = [
        _line((_DATE, "30 Dec"), (_DETAILS, "Paid to Shop A"),
              (_ACCOUNT, "UPI Lite"), (_AMOUNT, "- Rs.40.00")),
        _line((_DATE, "1:00 PM")),
        _line((_DETAILS, "UPI Ref No: 100000000006")),
    ]
    jan = [
        _line((_DATE, "02 Jan"), (_DETAILS, "Paid to Shop B"),
              (_ACCOUNT, "UPI Lite"), (_AMOUNT, "- Rs.50.00")),
        _line((_DATE, "2:00 PM")),
        _line((_DETAILS, "UPI Ref No: 100000000007")),
    ]
    text = "\n".join(["Paytm Statement for", header_period, "", "Passbook Payments History",
                      "", *dec, "", *jan, ""]) + "\n"
    rows = parse_paytm_pdf_text(text)
    by_name = {r["beneficiary"]: r["date"] for r in rows}
    assert by_name["Shop A"].startswith("2025-12-30")
    assert by_name["Shop B"].startswith("2026-01-02")
