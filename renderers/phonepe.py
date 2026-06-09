"""Render canonical records as a PhonePe-style *transaction statement* PDF.

The layout mirrors PhonePe's statement table (Date / Transaction Details / Type
/ Amount) so that ``pdftotext -layout`` reproduces the line structure the
backend ``parse_phonepe_pdf_text`` consumes:

    Jan 05, 2026   Paid to Amazon India          DEBIT   ₹1,200.00
    10:30 AM       Transaction ID: TXN...
                   UTR No.: UTR...
                   Paid by HDFC Bank A/C XX1234

Text-based PDF (never an image) — the pipeline runs ``pdftotext`` over it.
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from . import common, fonts

_FONT, _BOLD, _ = fonts.register()

_BODY = ParagraphStyle("body", fontName=_FONT, fontSize=8, leading=11)
_HEAD = ParagraphStyle("head", fontName=_BOLD, fontSize=8, leading=11)
_TITLE = ParagraphStyle("title", fontName=_BOLD, fontSize=15, leading=18)
_META = ParagraphStyle("meta", fontName=_FONT, fontSize=9, leading=13)
_WMARK = ParagraphStyle("wmark", fontName=_FONT, fontSize=8,
                        leading=11, textColor=colors.grey)


def _period(records: list[dict]) -> str:
    dates = sorted(r["date"] for r in records)
    return f"{common.phonepe_date(dates[0])} - {common.phonepe_date(dates[-1])}"


def render(records: list[dict], out_path: Path, *, holder: str = "Sample User") -> Path:
    handle = common.upi_handle(holder, "ybl")
    doc = SimpleDocTemplate(
        str(out_path), pagesize=A4,
        leftMargin=15 * mm, rightMargin=15 * mm, topMargin=15 * mm, bottomMargin=15 * mm,
    )

    story = [
        Paragraph("PhonePe", _TITLE),
        Paragraph("Transaction Statement", _HEAD),
        Spacer(1, 4),
        Paragraph(f"Name: {holder}", _META),
        Paragraph(f"UPI ID: {handle}", _META),
        Paragraph(f"Statement Period: {_period(records)}", _META),
        Paragraph("SYNTHETIC SAMPLE - NOT A REAL STATEMENT", _WMARK),
        Spacer(1, 8),
    ]

    data = [[
        Paragraph("Date", _HEAD), Paragraph("Transaction Details", _HEAD),
        Paragraph("Type", _HEAD), Paragraph("Amount", _HEAD),
    ]]
    for r in records:
        date_cell = f"{common.phonepe_date(r['date'])}<br/>{common.clock_12h(r['time'])}"
        detail_cell = "<br/>".join(str(x) for x in r["Transaction Detail"])
        type_cell = "DEBIT" if common.is_debit(r) else "CREDIT"
        amount_cell = common.rupee(float(r["amount"]))
        data.append([
            Paragraph(date_cell, _BODY), Paragraph(detail_cell, _BODY),
            Paragraph(type_cell, _BODY), Paragraph(amount_cell, _BODY),
        ])

    table = Table(data, colWidths=[26 * mm, 95 * mm, 18 * mm, 26 * mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.black),
        ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.lightgrey),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(table)
    story.append(Spacer(1, 10))
    story.append(Paragraph("This is a system generated statement.", _WMARK))

    doc.build(story)
    return out_path
