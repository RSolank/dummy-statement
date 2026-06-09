"""Google Pay activity-statement parser.

ASSUMED FORMAT (stacked list; recalibrate against a real GPay statement):

    5 Jan 2026, 2:30 PM
    Paid to Amazon India
    ₹1,200.00
    HDFC Bank XX1234
    Completed - UPI transaction ID: 412345678901

Rules:
  * Each transaction begins with a ``D Mon YYYY[, h:mm AM/PM]`` line.
  * Amounts are unsigned; direction comes from the ``Paid to`` /
    ``Received from`` / ``Money sent to`` verb on the description line.
  * The remaining lines (bank, status, UPI transaction ID) fold into notes.

Emits the shared row contract (see ``parsers/contract.py``).
"""

from __future__ import annotations

import re
from typing import Dict, List

from .contract import CREDIT, DEBIT, clean_number

_MONTHS = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}

_DATE_RE = re.compile(
    r"^(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{4})"
    r"(?:,\s*(\d{1,2}):(\d{2})\s*(AM|PM))?$",
    re.IGNORECASE,
)
_AMOUNT_RE = re.compile(r"^₹?\s*([0-9,]+\.\d{2})$")
_CREDIT_VERBS = ("received from", "refund from", "money received from")
_DEBIT_VERBS = ("paid to", "money sent to", "sent to")
_VERBS = _CREDIT_VERBS + _DEBIT_VERBS
_SKIP_PREFIXES = ("Google Pay", "Transaction history", "SYNTHETIC", "This is a system generated", "Page ")


def _direction_and_name(desc: str):
    low = desc.lower()
    for verb in _CREDIT_VERBS:
        if low.startswith(verb):
            return CREDIT, desc[len(verb):].strip()
    for verb in _DEBIT_VERBS:
        if low.startswith(verb):
            return DEBIT, desc[len(verb):].strip()
    return None, None


def parse_gpay_pdf_text(pdf_text: str) -> List[Dict]:
    lines = [ln.strip() for ln in pdf_text.splitlines()]
    lines = [ln for ln in lines if ln and not ln.startswith(_SKIP_PREFIXES)]

    out: List[Dict] = []
    i = 0
    while i < len(lines):
        dm = _DATE_RE.match(lines[i])
        if not dm:
            i += 1
            continue

        day, mon, year = int(dm.group(1)), _MONTHS[dm.group(2).title()], int(dm.group(3))
        date_iso = f"{year}-{mon:02d}-{day:02d}"
        if dm.group(4):
            hour, minute, ap = int(dm.group(4)), int(dm.group(5)), dm.group(6).upper()
            if ap == "PM" and hour != 12:
                hour += 12
            elif ap == "AM" and hour == 12:
                hour = 0
            date_iso += f"T{hour:02d}:{minute:02d}:00Z"
        else:
            date_iso += "T00:00:00Z"

        # walk the block to the next date line, pulling description + amount
        debit_credit = beneficiary = None
        amount = None
        notes_parts = [lines[i]]
        j = i + 1
        while j < len(lines) and not _DATE_RE.match(lines[j]):
            notes_parts.append(lines[j])
            dc, name = _direction_and_name(lines[j])
            if dc and beneficiary is None:
                debit_credit, beneficiary = dc, name
            am = _AMOUNT_RE.match(lines[j])
            if am and amount is None:
                amount = clean_number(am.group(1))
            j += 1

        if debit_credit and amount is not None:
            out.append({
                "date": date_iso, "amount": amount, "debit_credit": debit_credit,
                "beneficiary": beneficiary,
                "notes": " ".join(" ".join(notes_parts).split()).strip(),
                "source": "statement",
            })
        i = j

    return out
