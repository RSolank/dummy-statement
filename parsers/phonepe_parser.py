"""PhonePe statement parser — VENDORED from the backend for round-trip testing.

Source of truth:
``backend/app/modules/transactions/statement_upload/parsers/phonepe_statement_parser.py``

This copy is adapted only to the local row contract (``DEBIT`` / ``CREDIT``
string constants instead of ``app.constants.DebitCredit``). Keep it in sync with
the backend if that parser changes — it exists here purely so the PhonePe
renderer can be validated against the exact logic production uses, which in turn
gives confidence in the Paytm / GPay harness.
"""

from __future__ import annotations

import re
from typing import Dict, List

from .contract import CREDIT, DEBIT, clean_number

MONTHS = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}

DATE_RE = re.compile(r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s(\d{1,2}),\s(\d{4})$")
DATE_PREFIX_RE = re.compile(r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s(\d{1,2}),\s(\d{4})")

DETAIL_STOP_SUFFIXES = ("Transaction ID", "UTR No", "Paid by")
DETAIL_START_PREFIXES = ("to", "from", "by")


def _extract_short_beneficiary(details_text: str) -> str:
    beneficiary = " ".join(details_text.split()).strip()
    for suffix in DETAIL_STOP_SUFFIXES:
        m = re.match(rf"(.+?) {suffix}", beneficiary, flags=re.IGNORECASE)
        if m:
            beneficiary = m.group(1).strip()
            break
    for prefix in DETAIL_START_PREFIXES:
        m = re.match(rf"^(\w+?\s{prefix}\s)", beneficiary, flags=re.IGNORECASE)
        if m:
            beneficiary = beneficiary[m.end():]
            break
    beneficiary = re.sub(r"\s+[a-zA-Z0-9.\-_]+@[a-zA-Z]{3,}\b.*$", "", beneficiary)
    beneficiary = re.sub(r"\s+(?:UPI ID|Ref No|Mobile|Phone|UTR).*", "", beneficiary, flags=re.IGNORECASE)
    beneficiary = re.sub(r"\s+\d{10,12}\b.*$", "", beneficiary)
    return beneficiary.rstrip(",. ").strip()


def parse_phonepe_pdf_text(pdf_text: str) -> List[Dict]:
    lines = [ln.strip() for ln in pdf_text.splitlines()]
    lines = [
        ln for ln in lines
        if ln and not (
            ln.startswith("Page ")
            or ln.startswith("This is a system generated ")
            or ln.startswith("Date Transaction Details ")
        )
    ]

    out: List[Dict] = []
    i = 0
    while i < len(lines):
        dm = DATE_PREFIX_RE.match(lines[i])
        if not dm:
            i += 1
            continue

        notes_text = dm.group(0).strip() + " "
        mon_str, day_str, year_str = dm.group(1), dm.group(2), dm.group(3)
        date_iso = f"{year_str}-{MONTHS[mon_str]:02d}-{int(day_str):02d}"

        remainder = lines[i][dm.end():].strip()
        type_amt_match = re.search(
            r"(DEBIT|CREDIT)\s*(?:₹)?\s*([0-9,]+(?:\.[0-9]+)?)", remainder, flags=re.IGNORECASE
        )

        details_text = ""
        time_found = False
        j = i + 1
        while j < len(lines) and not (
            DATE_PREFIX_RE.match(lines[j])
            or lines[j - 1].startswith("Paid by ")
            or lines[j - 1].startswith("Credited to ")
            or lines[j - 1].startswith("Debited from ")
        ):
            if time_found:
                details_text += lines[j].strip() + " "
                j += 1
                continue
            time_match = re.match(r"^(\d{1,2}):(\d{2})\s*(AM|PM)", lines[j], flags=re.IGNORECASE)
            if time_match:
                notes_text += time_match.group(0).strip() + " "
                details_text += lines[j][time_match.end():].strip() + " "
                hour_int = int(time_match.group(1))
                minute_int = int(time_match.group(2))
                am_pm = time_match.group(3).upper()
                if am_pm == "PM" and hour_int != 12:
                    hour_int += 12
                elif am_pm == "AM" and hour_int == 12:
                    hour_int = 0
                date_iso = f"{date_iso}T{hour_int:02d}:{minute_int:02d}:00Z"
                time_found = True
            j += 1
        if not time_found:
            date_iso += "T00:00:00Z"

        if type_amt_match:
            notes_text += type_amt_match.group(0).strip() + " "
            details_text = f"{remainder[: type_amt_match.start()].strip()} {details_text}".strip()
            dc = type_amt_match.group(1).upper()
            debit_credit = DEBIT if dc == "DEBIT" else CREDIT
            amount = clean_number(type_amt_match.group(2))
            if not details_text:
                details_text = remainder
            beneficiary = _extract_short_beneficiary(details_text)
            notes_text = " ".join(f"{notes_text} {details_text}".split()).strip()
            out.append({
                "date": date_iso, "amount": amount, "debit_credit": debit_credit,
                "beneficiary": beneficiary, "notes": notes_text, "source": "statement",
            })
        i = j

    return out
