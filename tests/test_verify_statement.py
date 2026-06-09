"""Tests for the statement verifier.

These pin the two bugs the verifier originally shipped with, so they cannot
silently come back:

  * the account-header consistency check conflated the "Paid by" / "Credited to"
    direction verbs and so could never pass on a real statement;
  * the ``--bank`` check compared the bank prefix against the un-stripped verb
    and so always failed.

Run with the local venv:

    .venv/bin/pytest
"""

from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import statement_generator as generator  # noqa: E402
import verify_statement as verifier  # noqa: E402


def _generate(out_dir: Path, *extra: str) -> Path:
    argv = [
        "-y",
        "--seed", "42",
        "--range", "2026-01-01:2026-02-28",
        "--profile", "salary-heavy",
        "--bank", "HDFC Bank",
        "--output-dir", str(out_dir),
        *extra,
    ]
    with redirect_stdout(io.StringIO()):
        assert generator.main(argv) == 0
    return out_dir


def _verify(*argv: str) -> tuple[int, str]:
    err = io.StringIO()
    with redirect_stdout(io.StringIO()), redirect_stderr(err):
        rc = verifier.main(list(argv))
    return rc, err.getvalue()


def _rewrite(out_dir: Path, rows: list[dict]) -> None:
    """Persist tampered rows back to both CSV and JSON so they stay in parity."""
    generator._write_csv(out_dir / "statement.csv", rows)
    generator._write_json(out_dir / "statement.json", rows)


# --------------------------------------------------------------------------- #
# happy path
# --------------------------------------------------------------------------- #
def test_clean_statement_passes_meta_driven(tmp_path):
    out = _generate(tmp_path)
    rc, _ = _verify(str(out))  # no flags: expectations come from meta.json
    assert rc == 0


def test_clean_statement_passes_with_explicit_flags(tmp_path):
    out = _generate(tmp_path)
    rc, _ = _verify(
        str(out),
        "--range", "2026-01-01:2026-02-28",
        "--profile", "salary-heavy",
        "--bank", "HDFC Bank",
    )
    assert rc == 0


# --------------------------------------------------------------------------- #
# bug #1 regression: header consistency must accept mixed debit/credit verbs
# --------------------------------------------------------------------------- #
def test_mixed_direction_headers_are_consistent(tmp_path):
    out = _generate(tmp_path)
    rows = json.loads((out / "statement.json").read_text())
    # Sanity: the fixture really does contain both verbs sharing one account.
    verbs = {r["Transaction Detail"][3].split(" ", 1)[0] for r in rows}
    assert {"Paid", "Credited"} <= verbs
    rc, err = _verify(str(out))
    assert rc == 0, err


def test_genuinely_inconsistent_account_is_flagged(tmp_path):
    out = _generate(tmp_path)
    rows = json.loads((out / "statement.json").read_text())
    # Swap one row onto a different account number -> should now fail.
    rows[0]["Transaction Detail"][3] = "Paid by HDFC Bank A/C XX9999"
    _rewrite(out, rows)
    rc, err = _verify(str(out))
    assert rc == 1
    assert "account header is not consistent" in err


# --------------------------------------------------------------------------- #
# bug #2 regression: --bank check must match the stripped account header
# --------------------------------------------------------------------------- #
def test_correct_bank_passes(tmp_path):
    out = _generate(tmp_path)
    rc, err = _verify(str(out), "--bank", "HDFC Bank")
    assert rc == 0, err


def test_wrong_bank_fails(tmp_path):
    out = _generate(tmp_path)
    rc, err = _verify(str(out), "--bank", "Axis Bank")
    assert rc == 1
    assert "does not match expected bank" in err


# --------------------------------------------------------------------------- #
# parity / range / missing-file checks
# --------------------------------------------------------------------------- #
def test_csv_json_row_count_mismatch_is_flagged(tmp_path):
    out = _generate(tmp_path)
    rows = json.loads((out / "statement.json").read_text())
    (out / "statement.json").write_text(json.dumps(rows[:-1], indent=2) + "\n")
    rc, err = _verify(str(out))
    assert rc == 1
    assert "differ" in err


def test_date_outside_expected_range_is_flagged(tmp_path):
    out = _generate(tmp_path)
    rc, err = _verify(str(out), "--range", "2026-01-10:2026-02-20")
    assert rc == 1
    assert "before expected start" in err or "after expected end" in err


def test_missing_files_reported(tmp_path):
    rc, err = _verify(str(tmp_path))
    assert rc == 1
    assert "Missing CSV file" in err
    assert "Missing JSON file" in err


def test_meta_defaults_apply_bank_check(tmp_path):
    # meta.json carries bank=HDFC; tamper one account and verify (no flags) must
    # still fail on the bank prefix, proving meta-driven expectations are wired.
    out = _generate(tmp_path)
    rows = json.loads((out / "statement.json").read_text())
    for r in rows:
        verb, _, _ = r["Transaction Detail"][3].partition(" ")
        prefix = "Paid by " if r["type"] == "debit" else "Credited to "
        r["Transaction Detail"][3] = f"{prefix}Axis Bank A/C XX1234"
    _rewrite(out, rows)
    rc, err = _verify(str(out))
    assert rc == 1
    assert "does not match expected bank" in err
