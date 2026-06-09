"""Render canonical records as a Google Pay activity-statement-style PDF.

Unlike PhonePe/Paytm (wide tables), GPay history is a stacked list. Assumed
``pdftotext`` output per transaction:

    5 Jan 2026, 2:30 PM
    Paid to Amazon India
    ₹1,200.00
    HDFC Bank XX1234
    Completed - UPI transaction ID: 412345678901

Amounts are unsigned; direction comes from the ``Paid to`` / ``Received from``
verb. Recalibrate against a real GPay statement when one is available.
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer

from . import common, fonts

_FONT, _BOLD, _ = fonts.register()
_TITLE = ParagraphStyle("title", fontName=_BOLD, fontSize=15, leading=18)
_META = ParagraphStyle("meta", fontName=_FONT, fontSize=9, leading=13)
_WMARK = ParagraphStyle("wmark", fontName=_FONT, fontSize=8, leading=11, textColor=colors.grey)
_WHEN = ParagraphStyle("when", fontName=_FONT, fontSize=8, leading=11, textColor=colors.grey)
_DESC = ParagraphStyle("desc", fontName=_BOLD, fontSize=9, leading=12)
_AMT = ParagraphStyle("amt", fontName=_FONT, fontSize=9, leading=12)
_SUB = ParagraphStyle("sub", fontName=_FONT, fontSize=8, leading=11, textColor=colors.grey)


def _ref_no(record: dict) -> str:
    digits = "".join(ch for ch in common.utr_no(record) if ch.isdigit())
    return (digits + "000000000000")[:12]


def render(records: list[dict], out_path: Path, *, holder: str = "Sample User") -> Path:
    handle = common.upi_handle(holder, "okhdfcbank")
    doc = SimpleDocTemplate(
        str(out_path), pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm, topMargin=15 * mm, bottomMargin=15 * mm,
    )

    story = [
        Paragraph("Google Pay", _TITLE),
        Paragraph(f"Transaction history for {holder} ({handle})", _META),
        Paragraph("SYNTHETIC SAMPLE - NOT A REAL STATEMENT", _WMARK),
        Spacer(1, 10),
        HRFlowable(width="100%", thickness=0.5, color=colors.lightgrey),
        Spacer(1, 6),
    ]

    for r in records:
        debit = common.is_debit(r)
        bank = common.bank_short(common.account_header(r))
        when = f"{common.gpay_date(r['date'])}, {common.clock_12h(r['time'])}"
        story.extend([
            Paragraph(when, _WHEN),
            Paragraph(str(r["Transaction Detail"][0]), _DESC),
            Paragraph(common.rupee(float(r["amount"])), _AMT),
            Paragraph(bank, _SUB),
            Paragraph(f"Completed - UPI transaction ID: {_ref_no(r)}", _SUB),
            Spacer(1, 5),
            HRFlowable(width="100%", thickness=0.25, color=colors.whitesmoke),
            Spacer(1, 5),
        ])

    story.append(Spacer(1, 8))
    story.append(Paragraph("This is a system generated statement.", _WMARK))
    doc.build(story)
    return out_path
