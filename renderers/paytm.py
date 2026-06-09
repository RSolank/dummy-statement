"""Render canonical records as a Paytm UPI-statement-style PDF.

Calibrated against a real Paytm "Passbook Payments History" statement. The
``pdftotext -layout`` output this produces:

    Paytm Statement for
    5 JAN'26 - 1 FEB'26
    ...
      Date &        Transaction Details      Notes & Tags   Your Account   Amount
      Time

      05 Jan        Paid to Amazon India     Tag:           HDFC Bank      - Rs.1,200.00
      1:30 PM       UPI ID: amazon.india@ybl  # Payment      XX1234
                    UPI Ref No: 412345678901

Real-format specifics this matches (so the recalibrated ``paytm_parser`` reads
it back): ``Rs.`` not ``₹``; year-less ``DD Mon`` rows with the year in the
period header; **unsigned** credit amounts vs ``- Rs.`` debits; five columns.
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
_WMARK = ParagraphStyle("wmark", fontName=_FONT, fontSize=8, leading=11, textColor=colors.grey)


def _ref_no(record: dict) -> str:
    digits = "".join(ch for ch in common.utr_no(record) if ch.isdigit())
    return (digits + "000000000000")[:12]


def _amount_cell(record: dict) -> str:
    # Debit: "- Rs.X". Credit: unsigned "Rs.X" (matches Paytm add-money/credits).
    value = common.amount_str(float(record["amount"]))
    return f"- Rs.{value}" if common.is_debit(record) else f"Rs.{value}"


def render(records: list[dict], out_path: Path, *, holder: str = "Sample User") -> Path:
    handle = common.upi_handle(holder, "paytm")
    doc = SimpleDocTemplate(
        str(out_path), pagesize=A4,
        leftMargin=15 * mm, rightMargin=15 * mm, topMargin=15 * mm, bottomMargin=15 * mm,
    )

    paid = sum(float(r["amount"]) for r in records if common.is_debit(r))
    recv = sum(float(r["amount"]) for r in records if not common.is_debit(r))

    story = [
        Paragraph("Paytm", _TITLE),
        Paragraph("Statement for", _HEAD),
        Paragraph(common.paytm_period(records), _META),
        Spacer(1, 4),
        Paragraph(f"Name: {holder}", _META),
        Paragraph(f"UPI ID: {handle}", _META),
        Paragraph(f"Total Money Paid: - Rs.{common.amount_str(paid)}", _META),
        Paragraph(f"Total Money Received: + Rs.{common.amount_str(recv)}", _META),
        Paragraph("SYNTHETIC SAMPLE - NOT A REAL STATEMENT", _WMARK),
        Spacer(1, 8),
        Paragraph("Passbook Payments History", _HEAD),
        Spacer(1, 4),
    ]

    data = [[
        Paragraph("Date &<br/>Time", _HEAD),
        Paragraph("Transaction Details", _HEAD),
        Paragraph("Notes &amp; Tags", _HEAD),
        Paragraph("Your Account", _HEAD),
        Paragraph("Amount", _HEAD),
    ]]
    for r in records:
        bank = common.bank_short(common.account_header(r))
        cp_handle = common.upi_handle(common.counterparty(r), "ybl")
        date_cell = f"{common.paytm_daymon(r['date'])}<br/>{common.clock_12h(r['time'])}"
        detail_cell = (
            f"{r['Transaction Detail'][0]}<br/>"
            f"UPI ID: {cp_handle}<br/>"
            f"UPI Ref No: {_ref_no(r)}"
        )
        notes_cell = "Tag:<br/># Payment"
        data.append([
            Paragraph(date_cell, _BODY), Paragraph(detail_cell, _BODY),
            Paragraph(notes_cell, _BODY), Paragraph(bank, _BODY),
            Paragraph(_amount_cell(r), _BODY),
        ])

    table = Table(
        data, colWidths=[20 * mm, 66 * mm, 32 * mm, 30 * mm, 32 * mm], repeatRows=1
    )
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.black),
        ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.lightgrey),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(table)
    story.append(Spacer(1, 10))
    story.append(Paragraph("This is a system generated statement.", _WMARK))

    doc.build(story)
    return out_path
