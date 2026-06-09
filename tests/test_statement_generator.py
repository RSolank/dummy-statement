"""Tests for the synthetic statement generator.

Run with the local venv:

    .venv/bin/pytest
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import random
import sys
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import statement_generator as generator  # noqa: E402


def _config(**overrides) -> generator.RunConfig:
    base = dict(
        start_date=date(2026, 1, 1),
        end_date=date(2026, 3, 31),
        monthly_income=120000.0,
        monthly_expense=90000.0,
        seed=42,
        profile="salary-heavy",
        bank="HDFC Bank",
        output_dir=Path("/unused"),
    )
    base.update(overrides)
    return generator.RunConfig(**base)


# --------------------------------------------------------------------------- #
# _generate_records
# --------------------------------------------------------------------------- #
def test_seed_is_deterministic():
    assert generator._generate_records(_config(seed=7)) == generator._generate_records(
        _config(seed=7)
    )


def test_different_seeds_differ():
    assert generator._generate_records(_config(seed=1)) != generator._generate_records(
        _config(seed=2)
    )


def test_all_rows_within_date_window():
    config = _config(start_date=date(2026, 2, 1), end_date=date(2026, 2, 28))
    for row in generator._generate_records(config):
        row_date = date.fromisoformat(row["date"])
        assert config.start_date <= row_date <= config.end_date


def test_records_sorted_by_date_then_time():
    records = generator._generate_records(_config())
    keys = [(r["date"], r["time"]) for r in records]
    assert keys == sorted(keys)


def test_debit_heavy_mix():
    records = generator._generate_records(_config())
    debits = sum(1 for r in records if r["type"] == "debit")
    credits = sum(1 for r in records if r["type"] == "credit")
    assert debits > credits
    # Credits stay rare: at most one salary + one optional extra per month.
    assert credits <= 2 * 3


@pytest.mark.parametrize("profile", sorted(generator.PROFILE_SPECS))
def test_detail_block_structure(profile):
    records = generator._generate_records(_config(profile=profile))
    accounts = set()
    for row in records:
        detail = row["Transaction Detail"]
        assert isinstance(detail, list)
        assert len(detail) == 4
        assert detail[1].startswith("Transaction ID: ")
        assert detail[2].startswith("UTR No.: ")
        if row["type"] == "debit":
            assert detail[0].startswith("Paid to ")
            assert detail[3].startswith("Paid by ")
            accounts.add(detail[3].removeprefix("Paid by "))
        else:
            assert detail[0].startswith("Received from ")
            assert detail[3].startswith("Credited to ")
            accounts.add(detail[3].removeprefix("Credited to "))
    # One account per run, regardless of direction verb.
    assert len(accounts) == 1


def test_bank_header_matches_requested_bank():
    records = generator._generate_records(_config(bank="HDFC Bank"))
    for row in records:
        account = row["Transaction Detail"][3].split(" to ", 1)[-1].split(" by ", 1)[-1]
        assert account.startswith("HDFC Bank A/C XX")


def test_txn_and_utr_id_format():
    for row in generator._generate_records(_config()):
        assert row["Transaction Detail"][1].removeprefix("Transaction ID: ").startswith("TXN")
        assert row["Transaction Detail"][2].removeprefix("UTR No.: ").startswith("UTR")


def test_amounts_are_positive():
    for row in generator._generate_records(_config()):
        assert float(row["amount"]) > 0


# --------------------------------------------------------------------------- #
# _generate_amounts
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("count", [0, -3])
def test_amounts_empty_for_non_positive_count(count):
    profile = generator.PROFILE_SPECS["salary-heavy"]
    assert generator._generate_amounts(random.Random(0), 1000.0, count, profile=profile) == []


def test_amounts_count_and_sum_respected():
    profile = generator.PROFILE_SPECS["salary-heavy"]
    amounts = generator._generate_amounts(random.Random(0), 50000.0, 25, profile=profile)
    assert len(amounts) == 25
    assert sum(amounts) == pytest.approx(50000.0, abs=0.01)
    assert all(a > 0 for a in amounts)


def test_residual_is_not_dumped_on_last_row():
    # Regression for the old "amounts[-1] += whole residual" behaviour: the
    # residual is now spread one paisa at a time, so the total is exact and no
    # single row balloons past the scaled ceiling.
    profile = generator.PROFILE_SPECS["salary-heavy"]
    amounts = generator._generate_amounts(random.Random(123), 50000.0, 25, profile=profile)
    assert sum(amounts) == pytest.approx(50000.0, abs=0.01)
    assert max(amounts) < 50000.0


# --------------------------------------------------------------------------- #
# _month_windows
# --------------------------------------------------------------------------- #
def test_month_windows_single_month():
    assert generator._month_windows(date(2026, 1, 5), date(2026, 1, 20)) == [
        (date(2026, 1, 5), date(2026, 1, 20))
    ]


def test_month_windows_spans_three_months_with_partial_edges():
    assert generator._month_windows(date(2026, 1, 15), date(2026, 3, 10)) == [
        (date(2026, 1, 15), date(2026, 1, 31)),
        (date(2026, 2, 1), date(2026, 2, 28)),
        (date(2026, 3, 1), date(2026, 3, 10)),
    ]


# --------------------------------------------------------------------------- #
# argument parsing / validation
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("bad", ["2026/01/01", "2026-13-01"])
def test_parse_date_rejects_bad_format(bad):
    with pytest.raises(argparse.ArgumentTypeError):
        generator._parse_date(bad, "date")


@pytest.mark.parametrize("bad", ["2026-01-01", "2026-03-01:2026-01-01"])
def test_parse_range_rejects_bad_input(bad):
    with pytest.raises(argparse.ArgumentTypeError):
        generator._parse_range(bad)


def test_parse_range_happy_path():
    assert generator._parse_range("2026-01-01:2026-03-01") == (date(2026, 1, 1), date(2026, 3, 1))


@pytest.mark.parametrize("bad", ["0", "-5", "abc"])
def test_parse_amount_rejects_non_positive_and_non_numeric(bad):
    with pytest.raises(argparse.ArgumentTypeError):
        generator._parse_amount(bad, "--income")


def test_choose_profile_rejects_unknown():
    with pytest.raises(SystemExit):
        generator._choose_profile(prompt_enabled=False, provided="bogus")


def test_choose_bank_rejects_unknown():
    with pytest.raises(SystemExit):
        generator._choose_bank(prompt_enabled=False, provided="Imaginary Bank")


# --------------------------------------------------------------------------- #
# main() end-to-end (writes real files)
# --------------------------------------------------------------------------- #
def _run_main(out_dir: Path, *extra: str) -> Path:
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
        rc = generator.main(argv)
    assert rc == 0
    return out_dir


def test_main_writes_three_artifacts(tmp_path):
    out = _run_main(tmp_path)
    assert (out / "statement.csv").exists()
    assert (out / "statement.json").exists()
    assert (out / "meta.json").exists()


def test_main_csv_and_json_are_in_sync(tmp_path):
    out = _run_main(tmp_path)
    json_rows = json.loads((out / "statement.json").read_text())
    with (out / "statement.csv").open(newline="") as handle:
        csv_rows = list(csv.DictReader(handle))
    assert len(csv_rows) == len(json_rows)
    for c, j in zip(csv_rows, json_rows):
        assert c["date"] == j["date"]
        assert c["time"] == j["time"]
        assert c["type"] == j["type"]
        assert float(c["amount"]) == pytest.approx(float(j["amount"]), abs=0.01)
        assert json.loads(c["Transaction Detail"]) == j["Transaction Detail"]


def test_main_meta_records_run_parameters(tmp_path):
    out = _run_main(tmp_path)
    meta = json.loads((out / "meta.json").read_text())
    assert meta["seed"] == 42
    assert meta["profile"] == "salary-heavy"
    assert meta["bank"] == "HDFC Bank"
    assert meta["start_date"] == "2026-01-01"
    assert meta["end_date"] == "2026-02-28"
    assert meta["generator_version"] == generator.GENERATOR_VERSION
    rows = json.loads((out / "statement.json").read_text())
    assert meta["row_count"] == len(rows)
    assert meta["debit_count"] + meta["credit_count"] == len(rows)


def test_main_seed_reproduces_identical_output(tmp_path):
    out_a = _run_main(tmp_path / "a")
    out_b = _run_main(tmp_path / "b")
    assert (out_a / "statement.json").read_text() == (out_b / "statement.json").read_text()
