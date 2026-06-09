"""Paytm UPI statement parser.

Calibrated against a real Paytm UPI Statement (Passbook Payments History), as
extracted by ``pdftotext -layout``. The relevant shape (synthetic example — no
real account data is embedded here):

    Paytm Statement for
    5 JAN'26 - 1 FEB'26                       - Rs.1,234.00 ...      <- period (year source)
    ...
      Date &
                    Transaction Details      Notes & Tags   Your Account   Amount
      Time

      05 Jan        Paid to Acme Store       Tag:           UPI Lite       - Rs.50
      1:30 PM
                    UPI ID: acme.store@ybl on             # Shopping
                    UPI Ref No: 100000000001

Key facts this parser handles:
  * Amounts are ``Rs.`` (not ``₹``) and may be integer (``Rs.50``) or decimal
    (``Rs.370.90``); thousands grouped (``Rs.1,700``).
  * A leading ``-`` marks a debit; **no sign** marks a credit / add-money
    (e.g. a Paytm "Automatic Add Money for UPI Lite" self-transfer top-up).
  * Transaction rows carry only ``DD Mon`` (no year). The year is taken from the
    statement-period header ``D MON'YY - D MON'YY`` and mapped per month so a
    statement spanning a year boundary resolves correctly.
  * pdftotext merges the 5 columns onto the date line; the leftmost cell is the
    description. Continuation lines (wrapped names) are matched by column.

Emits the shared row contract (see ``parsers/contract.py``).
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from .contract import CREDIT, DEBIT, clean_number

_MONTHS = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}
_MON_ALT = "Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec"

# A transaction row: leading "DD Mon" then anything, ending in an amount.
_ROW_RE = re.compile(rf"^(\s*)(\d{{1,2}})\s+({_MON_ALT})\s+(\S.*)$", re.IGNORECASE)
# Amount at end of the date line: optional "-" sign, "Rs." and a number.
_AMOUNT_RE = re.compile(r"(-)?\s*Rs\.?\s*([0-9,]+(?:\.\d+)?)\s*$", re.IGNORECASE)
_TIME_RE = re.compile(r"(\d{1,2}):(\d{2})\s*(AM|PM)", re.IGNORECASE)
# Statement period header, e.g. "5 JAN'26 - 1 FEB'26"
_PERIOD_RE = re.compile(
    rf"(\d{{1,2}})\s+({_MON_ALT})'(\d{{2}})\s*-\s*(\d{{1,2}})\s+({_MON_ALT})'(\d{{2}})",
    re.IGNORECASE,
)

_VERBS = ("Paid to ", "Received from ", "Money sent to ", "Sent to ")
# A details-column line that is NOT part of the counterparty name.
_NAME_STOP = ("UPI ID", "UPI Ref No", "Tag:", "Note:", "#")


def _segments(line: str) -> List[Tuple[int, str]]:
    """Split a layout line into (start_column, text) cells on runs of 2+ spaces."""
    return [(m.start(), m.group().strip()) for m in re.finditer(r"\S.*?(?=\s{2,}|$)", line)]


def _strip_verb(text: str) -> str:
    text = " ".join(text.split()).strip()
    for verb in _VERBS:
        if text.lower().startswith(verb.lower()):
            return text[len(verb):].strip()
    return text


def _year_resolver(pdf_text: str, default_year: Optional[int]):
    m = _PERIOD_RE.search(pdf_text)
    if not m:
        fixed = default_year
        return lambda _month: fixed
    s_mon, s_yy = _MONTHS[m.group(2).title()], 2000 + int(m.group(3))
    e_mon, e_yy = _MONTHS[m.group(5).title()], 2000 + int(m.group(6))

    def resolve(month: int) -> Optional[int]:
        if s_yy == e_yy:
            return s_yy
        if month >= s_mon:   # tail of the start year
            return s_yy
        if month <= e_mon:   # head of the end year
            return e_yy
        return s_yy

    return resolve


def parse_paytm_pdf_text(pdf_text: str, *, default_year: Optional[int] = None) -> List[Dict]:
    year_of = _year_resolver(pdf_text, default_year)
    raw_lines = [ln.rstrip() for ln in pdf_text.splitlines()]

    out: List[Dict] = []
    i = 0
    n = len(raw_lines)
    while i < n:
        row = _ROW_RE.match(raw_lines[i])
        amt = _AMOUNT_RE.search(raw_lines[i]) if row else None
        if not row or not amt:
            i += 1
            continue

        day = int(row.group(2))
        month = _MONTHS[row.group(3).title()]
        year = year_of(month)
        date_iso = f"{year:04d}-{month:02d}-{day:02d}" if year else f"0000-{month:02d}-{day:02d}"

        # Description = leftmost cell between the date and the amount column.
        desc_region = raw_lines[i][row.start(4):amt.start()]
        desc_segs = _segments(raw_lines[i][: amt.start()])
        # the first cell after the date prefix is the description
        desc_col, desc_text = (desc_segs[1] if len(desc_segs) > 1 else (row.start(4), desc_region.strip()))
        beneficiary = desc_text

        sign = amt.group(1)
        amount = clean_number(amt.group(2))
        debit_credit = DEBIT if sign == "-" else CREDIT

        # Walk the block: pull the time, extend a column-aligned wrapped name
        # (stopping at the first UPI ID / Ref / Tag line), and collect notes.
        notes_parts = [raw_lines[i].strip()]
        time_iso = None
        name_open = True
        j = i + 1
        while j < n and not (_ROW_RE.match(raw_lines[j]) and _AMOUNT_RE.search(raw_lines[j])):
            text = raw_lines[j].strip()
            if not text:
                j += 1
                continue
            if text.startswith(("Page ", "Passbook Payments History",
                                "All payments done by you", "For any queries", "Contact Us",
                                "Date &", "Transaction Details", "Note: This payment")):
                j += 1
                continue
            notes_parts.append(text)

            tm = _TIME_RE.match(text)
            if tm and time_iso is None:
                hour, minute, ap = int(tm.group(1)), int(tm.group(2)), tm.group(3).upper()
                if ap == "PM" and hour != 12:
                    hour += 12
                elif ap == "AM" and hour == 12:
                    hour = 0
                time_iso = f"{hour:02d}:{minute:02d}:00"

            # column-aligned wrapped-name continuation
            if name_open:
                for col, seg in _segments(raw_lines[j]):
                    if seg.startswith(_NAME_STOP):
                        name_open = False
                        break
                    if _TIME_RE.match(seg):
                        continue
                    if abs(col - desc_col) <= 4 and seg:
                        beneficiary = f"{beneficiary} {seg}".strip()
            j += 1

        date_full = f"{date_iso}T{time_iso}Z" if time_iso else f"{date_iso}T00:00:00Z"
        out.append({
            "date": date_full,
            "amount": amount,
            "debit_credit": debit_credit,
            "beneficiary": _strip_verb(beneficiary),
            "notes": " ".join(" ".join(notes_parts).split()).strip(),
            "source": "statement",
        })
        i = j

    return out
