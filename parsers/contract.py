"""The row contract every statement parser must emit.

This mirrors the backend's ``parse_phonepe_pdf_text`` output so a parser written
and proven here can be migrated into
``backend/app/modules/transactions/statement_upload/parsers/`` with only one
change: swap the local ``DEBIT`` / ``CREDIT`` string constants for the backend's
``app.constants.DebitCredit`` enum.

A parsed row::

    {
        "date": "2026-01-05T14:30:00Z",   # ISO 8601, midnight if no time found
        "amount": 1200.0,                  # positive float
        "debit_credit": "DEBIT",           # DEBIT | CREDIT
        "beneficiary": "Amazon India",     # short counterparty name
        "notes": "...",                    # raw-ish reconstructed line(s)
        "source": "statement",
    }
"""

from __future__ import annotations

# Backend equivalent: app.constants.DebitCredit.DEBIT / .CREDIT
DEBIT = "DEBIT"
CREDIT = "CREDIT"

ROW_KEYS = ("date", "amount", "debit_credit", "beneficiary", "notes", "source")


def clean_number(num_str: str) -> float:
    return float(num_str.replace(",", "").replace("₹", "").strip())
