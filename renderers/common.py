"""Shared helpers for turning canonical statement records into the presentation
tokens each UPI app's statement uses.

A canonical record (from ``statement_generator``) looks like::

    {
        "date": "2026-01-05",
        "time": "14:30:00",
        "Transaction Detail": [
            "Paid to Amazon India",
            "Transaction ID: TXN20260105101...",
            "UTR No.: UTR20260105101...",
            "Paid by HDFC Bank A/C XX1234",
        ],
        "type": "debit",
        "amount": 1200.0,
    }

These helpers are app-agnostic; each renderer composes them into its own layout.
"""

from __future__ import annotations

import re
from datetime import datetime


_MONTHS = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]


def parse_date(iso: str) -> datetime:
    return datetime.strptime(iso, "%Y-%m-%d")


# ---- date / time presentation ------------------------------------------- #
def phonepe_date(iso: str) -> str:
    """``2026-01-05`` -> ``Jan 05, 2026`` (PhonePe statement header style)."""
    d = parse_date(iso)
    return f"{_MONTHS[d.month - 1]} {d.day:02d}, {d.year}"


def paytm_daymon(iso: str) -> str:
    """``2026-01-05`` -> ``05 Jan`` (Paytm passbook row — year lives in the
    period header, not the row)."""
    d = parse_date(iso)
    return f"{d.day:02d} {_MONTHS[d.month - 1]}"


def paytm_period(records: list[dict]) -> str:
    """Statement-period header, e.g. ``5 JAN'26 - 1 FEB'26`` (the year source)."""
    dates = sorted(r["date"] for r in records)
    a, b = parse_date(dates[0]), parse_date(dates[-1])
    return (f"{a.day} {_MONTHS[a.month - 1].upper()}'{a.year % 100:02d}"
            f" - {b.day} {_MONTHS[b.month - 1].upper()}'{b.year % 100:02d}")


def gpay_date(iso: str) -> str:
    """``2026-01-05`` -> ``5 Jan 2026`` (Google Pay activity style)."""
    d = parse_date(iso)
    return f"{d.day} {_MONTHS[d.month - 1]} {d.year}"


def clock_12h(hhmmss: str) -> str:
    """``14:30:00`` -> ``2:30 PM``."""
    t = datetime.strptime(hhmmss, "%H:%M:%S")
    hour = t.hour % 12 or 12
    suffix = "AM" if t.hour < 12 else "PM"
    return f"{hour}:{t.minute:02d} {suffix}"


# ---- amount presentation ------------------------------------------------- #
def amount_str(value: float) -> str:
    """``1200.0`` -> ``1,200.00`` (Indian-ish grouping is overkill for fixtures;
    plain thousands grouping is what the parsers tolerate)."""
    return f"{value:,.2f}"


def _symbol() -> str:
    # Drop the ₹ when the chosen font can't render it (would extract as a box
    # the amount regex can't read). A bare number stays parser-valid.
    from . import fonts

    return "₹" if fonts.rupee_supported() else ""


def rupee(value: float) -> str:
    return f"{_symbol()}{amount_str(value)}"


def signed_rupee(value: float, *, is_debit: bool) -> str:
    """``- ₹1,200.00`` / ``+ ₹1,200.00`` (Paytm-style signed amount)."""
    sign = "-" if is_debit else "+"
    sym = _symbol()
    joiner = " " if sym else ""
    return f"{sign} {sym}{joiner}{amount_str(value)}".replace("  ", " ")


# ---- field extraction from the canonical detail block -------------------- #
def is_debit(record: dict) -> bool:
    return str(record["type"]).lower() == "debit"


def counterparty(record: dict) -> str:
    """The other party, stripped of the ``Paid to`` / ``Received from`` verb."""
    first = str(record["Transaction Detail"][0])
    for verb in ("Paid to ", "Received from "):
        if first.startswith(verb):
            return first[len(verb):].strip()
    return first.strip()


def _detail_value(record: dict, label: str) -> str:
    for line in record["Transaction Detail"]:
        if str(line).startswith(label):
            return str(line)[len(label):].strip()
    return ""


def transaction_id(record: dict) -> str:
    return _detail_value(record, "Transaction ID:")


def utr_no(record: dict) -> str:
    return _detail_value(record, "UTR No.:")


def account_header(record: dict) -> str:
    """``HDFC Bank A/C XX1234`` — strip the ``Paid by`` / ``Credited to`` verb."""
    last = str(record["Transaction Detail"][3])
    for verb in ("Paid by ", "Credited to ", "Debited from "):
        if last.startswith(verb):
            return last[len(verb):].strip()
    return last.strip()


def bank_short(account: str) -> str:
    """``HDFC Bank A/C XX1234`` -> ``HDFC Bank XX1234`` (drop the ``A/C``)."""
    return account.replace(" A/C ", " ").strip()


def upi_handle(name: str, psp: str) -> str:
    """Synthesize a deterministic UPI handle for a statement header, e.g.
    ``rohit.solanki@ybl``. Purely cosmetic — feeds the header so the account
    holder's own handle can be picked up by handle-aware parsers."""
    local = re.sub(r"[^a-z0-9]+", ".", name.lower()).strip(".") or "user"
    return f"{local}@{psp}"
