"""Regression test against a REAL Paytm statement.

Privacy: this test embeds **no** values from the statement. Every expectation is
derived from the statement's own summary header at runtime (the "Total Money
Paid" figure and the "N Payments made" count), then checked against what the
parser extracted. The real PDF stays gitignored and is never read into source.

It is skipped when no real statement PDF is present, so CI without the fixture
stays green. This is the calibration anchor: if Paytm changes its layout, this
is the test that should fail first.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from parsers.paytm_parser import parse_paytm_pdf_text  # noqa: E402

_ROOT = Path(__file__).resolve().parent.parent
_REAL = next(iter(sorted(_ROOT.glob("Paytm*Statement*.pdf"))), None)

pytestmark = pytest.mark.skipif(
    _REAL is None or shutil.which("pdftotext") is None,
    reason="no real Paytm statement PDF present, or pdftotext not installed",
)

_PERIOD_RE = re.compile(r"(\d{1,2})\s+[A-Za-z]{3}'(\d{2})\s*-\s*(\d{1,2})\s+[A-Za-z]{3}'(\d{2})")
_PAYMENTS_MADE_RE = re.compile(r"(\d+)\s+Payments?\s+made")
# Totals line: "... - Rs.<paid> ... + Rs.<received>"
_TOTALS_RE = re.compile(r"-\s*Rs\.?\s*([0-9,]+(?:\.\d+)?).*?\+\s*Rs\.?\s*([0-9,]+(?:\.\d+)?)")


@pytest.fixture(scope="module")
def text() -> str:
    return subprocess.check_output(["pdftotext", "-layout", str(_REAL), "-"]).decode("utf-8")


@pytest.fixture(scope="module")
def rows(text) -> list[dict]:
    return parse_paytm_pdf_text(text)


def test_debit_count_matches_reported_payments(rows, text):
    m = _PAYMENTS_MADE_RE.search(text)
    assert m, "statement header should report 'N Payments made'"
    reported = int(m.group(1))
    debits = sum(1 for r in rows if r["debit_credit"] == "DEBIT")
    assert debits == reported


def test_debit_total_matches_reported_total(rows, text):
    m = _TOTALS_RE.search(text)
    assert m, "statement header should report a 'Total Money Paid' figure"
    reported_paid = float(m.group(1).replace(",", ""))
    debit_total = round(sum(r["amount"] for r in rows if r["debit_credit"] == "DEBIT"), 2)
    assert debit_total == round(reported_paid, 2)


def test_years_fall_within_reported_period(rows, text):
    m = _PERIOD_RE.search(text)
    assert m, "statement header should report a 'D MON'YY - D MON'YY' period"
    years = {2000 + int(m.group(2)), 2000 + int(m.group(4))}
    assert all(int(r["date"][:4]) in years for r in rows)


def test_contract_shape(rows):
    assert rows, "parser should extract at least one row"
    for r in rows:
        assert set(r) == {"date", "amount", "debit_credit", "beneficiary", "notes", "source"}
        assert r["source"] == "statement"
        assert r["debit_credit"] in {"DEBIT", "CREDIT"}
        assert r["amount"] > 0
        assert r["beneficiary"]


def test_no_column_bleed_in_any_beneficiary(rows):
    # The column-aware extraction must not let adjacent columns (Notes & Tags,
    # Your Account, Amount, UPI ID/Ref) leak into the counterparty name.
    forbidden = ("Tag:", "Note:", "UPI ID", "UPI Ref", "Rs.", "#", "  ")
    for r in rows:
        for token in forbidden:
            assert token not in r["beneficiary"], f"{token!r} leaked into {r['beneficiary']!r}"
