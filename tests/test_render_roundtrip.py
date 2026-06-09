"""Round-trip tests: canonical JSON -> rendered PDF -> pdftotext -> parser.

These prove each renderer/parser pair is self-consistent — that a statement we
render is read back into rows matching the source data. For PhonePe the parser
is the one vendored from the backend, so a pass there means our rendering +
extraction harness matches the format production already accepts.

Note: this proves renderer<->parser agreement, NOT real-world fidelity. The
Paytm/GPay formats are reconstructions; recalibrate against a real statement.
"""

from __future__ import annotations

import io
import json
import shutil
import subprocess
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import statement_generator as generator  # noqa: E402
from parsers.gpay_parser import parse_gpay_pdf_text  # noqa: E402
from parsers.paytm_parser import parse_paytm_pdf_text  # noqa: E402
from parsers.phonepe_parser import parse_phonepe_pdf_text  # noqa: E402
from renderers import common, gpay, paytm, phonepe  # noqa: E402

pytestmark = pytest.mark.skipif(
    shutil.which("pdftotext") is None, reason="pdftotext (poppler-utils) not installed"
)

APPS = {
    "phonepe": (phonepe.render, parse_phonepe_pdf_text),
    "paytm": (paytm.render, parse_paytm_pdf_text),
    "gpay": (gpay.render, parse_gpay_pdf_text),
}


@pytest.fixture(scope="module")
def records(tmp_path_factory) -> list[dict]:
    out = tmp_path_factory.mktemp("gen")
    argv = [
        "-y", "--seed", "7", "--range", "2026-01-05:2026-01-25",
        "--profile", "salary-heavy", "--bank", "HDFC Bank", "--output-dir", str(out),
    ]
    with redirect_stdout(io.StringIO()):
        assert generator.main(argv) == 0
    return json.loads((out / "statement.json").read_text())


def _pdftotext(pdf: Path) -> str:
    return subprocess.check_output(["pdftotext", "-layout", str(pdf), "-"]).decode("utf-8")


@pytest.mark.parametrize("app", list(APPS))
def test_render_is_text_extractable(records, tmp_path, app):
    render, _ = APPS[app]
    pdf = render(records, tmp_path / f"{app}.pdf")
    text = _pdftotext(pdf)
    # A real (text) PDF, not an image: the holder + at least one counterparty
    # must come back as selectable text.
    assert "Sample User" in text
    assert common.counterparty(records[0]) in text


@pytest.mark.parametrize("app", list(APPS))
def test_roundtrip_row_count(records, tmp_path, app):
    render, parse = APPS[app]
    pdf = render(records, tmp_path / f"{app}.pdf")
    parsed = parse(_pdftotext(pdf))
    assert len(parsed) == len(records)


@pytest.mark.parametrize("app", list(APPS))
def test_roundtrip_fields_match(records, tmp_path, app):
    render, parse = APPS[app]
    pdf = render(records, tmp_path / f"{app}.pdf")
    parsed = parse(_pdftotext(pdf))
    assert len(parsed) == len(records)
    for src, got in zip(records, parsed):
        assert got["date"].startswith(src["date"])  # date (+ time) preserved
        assert round(got["amount"], 2) == round(float(src["amount"]), 2)
        assert got["debit_credit"] == ("DEBIT" if common.is_debit(src) else "CREDIT")
        assert got["beneficiary"] == common.counterparty(src)
        assert got["source"] == "statement"


@pytest.mark.parametrize("app", list(APPS))
def test_amount_totals_preserved(records, tmp_path, app):
    render, parse = APPS[app]
    pdf = render(records, tmp_path / f"{app}.pdf")
    parsed = parse(_pdftotext(pdf))
    src_total = round(sum(float(r["amount"]) for r in records), 2)
    got_total = round(sum(r["amount"] for r in parsed), 2)
    assert got_total == src_total


def test_phonepe_uses_backend_vendored_parser():
    # Guard against drift: the vendored parser must still expose the backend's
    # public entrypoint name so a sync stays a straight copy.
    assert callable(parse_phonepe_pdf_text)
    assert parse_phonepe_pdf_text.__module__.endswith("phonepe_parser")
