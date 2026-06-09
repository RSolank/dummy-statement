"""Validate a generated dummy statement folder.

The checker compares CSV and JSON row-for-row, confirms the date window, and
applies a few mix heuristics so the output stays useful as a synthetic bank
statement fixture.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date, datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import statement_generator as generator


def _parse_date(raw: str) -> date:
    return datetime.strptime(raw, "%Y-%m-%d").date()


def _parse_range(raw: str) -> tuple[date, date]:
    if ":" not in raw:
        raise argparse.ArgumentTypeError("--range must use START:END")
    start_raw, end_raw = raw.split(":", 1)
    start = _parse_date(start_raw)
    end = _parse_date(end_raw)
    if start > end:
        raise argparse.ArgumentTypeError("range start must be <= range end")
    return start, end


def _load_csv(path: Path) -> list[dict[str, object]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    out: list[dict[str, object]] = []
    for row in rows:
        out.append(
            {
                "date": row["date"],
                "time": row["time"],
                "Transaction Detail": json.loads(row["Transaction Detail"]),
                "type": row["type"],
                "amount": float(row["amount"]),
            }
        )
    return out


def _load_json(path: Path) -> list[dict[str, object]]:
    return json.loads(path.read_text(encoding="utf-8"))


def _bank_prefix(bank: str) -> str | None:
    if bank == "random":
        return None
    template = generator.BANK_HEADER_TEMPLATES.get(bank)
    if not template:
        return None
    return template.split("{suffix}")[0]


# detail[3] carries a direction verb ("Paid by " for debits, "Credited to "
# for credits) in front of the account header. Strip it so the account portion
# can be compared on its own — it is the part that stays constant per run.
_HEADER_VERBS = ("Paid by ", "Credited to ")


def _account_from_header(header: str) -> str:
    for verb in _HEADER_VERBS:
        if header.startswith(verb):
            return header[len(verb):]
    return header


def _profile_thresholds(profile: str) -> dict[str, float]:
    thresholds = {
        "salary-heavy": {
            "min_debit_ratio": 0.70,
            "max_person_debit_ratio": 0.20,
            "max_merchant_credit_ratio": 0.30,
        },
        "student": {
            "min_debit_ratio": 0.65,
            "min_person_debit_ratio": 0.15,
            "max_merchant_credit_ratio": 0.35,
        },
        "family-expense": {
            "min_debit_ratio": 0.70,
            "max_person_debit_ratio": 0.30,
            "min_merchant_debit_ratio": 0.45,
            "max_merchant_credit_ratio": 0.30,
        },
    }
    return thresholds.get(profile, {})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate a generated dummy statement folder.")
    parser.add_argument("output_dir", help="Folder containing statement.csv and statement.json")
    parser.add_argument("--range", dest="date_range", help="Expected date range START:END")
    parser.add_argument("--start", help="Expected start date, YYYY-MM-DD")
    parser.add_argument("--end", help="Expected end date, YYYY-MM-DD")
    parser.add_argument(
        "--profile",
        choices=sorted(generator.PROFILE_SPECS),
        help="Expected profile used when generating the statement",
    )
    parser.add_argument(
        "--bank",
        choices=generator.BANK_INPUTS,
        help="Expected bank used when generating the statement",
    )
    return parser


def _load_meta(output_dir: Path) -> dict[str, object]:
    meta_path = output_dir / "meta.json"
    if not meta_path.exists():
        return {}
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_dir = Path(args.output_dir).expanduser().resolve()
    csv_path = output_dir / "statement.csv"
    json_path = output_dir / "statement.json"

    # If the run wrote a meta.json, use it to fill in any expectation the caller
    # did not pass explicitly. This lets `verify <dir>` check profile/bank/range
    # with no flags, which is exactly what the self-test relies on.
    meta = _load_meta(output_dir)
    if meta:
        if not (args.date_range or args.start or args.end):
            start, end = meta.get("start_date"), meta.get("end_date")
            if start and end:
                args.date_range = f"{start}:{end}"
        if args.profile is None and meta.get("profile") in generator.PROFILE_SPECS:
            args.profile = meta["profile"]
        if args.bank is None and meta.get("bank") in generator.BANK_INPUTS:
            args.bank = meta["bank"]

    errors: list[str] = []
    if not csv_path.exists():
        errors.append(f"Missing CSV file: {csv_path}")
    if not json_path.exists():
        errors.append(f"Missing JSON file: {json_path}")
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    csv_rows = _load_csv(csv_path)
    json_rows = _load_json(json_path)

    if len(csv_rows) != len(json_rows):
        errors.append(f"CSV rows ({len(csv_rows)}) and JSON rows ({len(json_rows)}) differ")

    row_count = min(len(csv_rows), len(json_rows))
    header_values: set[str] = set()
    debit_count = 0
    credit_count = 0
    merchant_debit_count = 0
    person_debit_count = 0
    merchant_credit_count = 0

    expected_start = expected_end = None
    if args.date_range:
        expected_start, expected_end = _parse_range(args.date_range)
    elif args.start or args.end:
        if not (args.start and args.end):
            errors.append("Both --start and --end are required together")
        else:
            expected_start = _parse_date(args.start)
            expected_end = _parse_date(args.end)
    elif csv_rows:
        dates = sorted(row["date"] for row in csv_rows)
        expected_start = _parse_date(dates[0])
        expected_end = _parse_date(dates[-1])

    expected_prefix = _bank_prefix(args.bank) if args.bank else None
    thresholds = _profile_thresholds(args.profile) if args.profile else {}

    for idx in range(row_count):
        csv_row = csv_rows[idx]
        json_row = json_rows[idx]

        for key in ("date", "time", "type"):
            if csv_row[key] != json_row[key]:
                errors.append(f"Row {idx + 1}: CSV and JSON differ for {key}")
        if abs(csv_row["amount"] - float(json_row["amount"])) > 0.01:
            errors.append(f"Row {idx + 1}: CSV and JSON differ for amount")

        csv_detail = csv_row["Transaction Detail"]
        json_detail = json_row["Transaction Detail"]
        if csv_detail != json_detail:
            errors.append(f"Row {idx + 1}: CSV and JSON Transaction Detail differ")
        if not isinstance(json_detail, list) or len(json_detail) != 4:
            errors.append(f"Row {idx + 1}: Transaction Detail must be a 4-item list")
            continue

        detail_first = str(json_detail[0])
        account = _account_from_header(str(json_detail[3]))
        header_values.add(account)

        if expected_prefix and not account.startswith(expected_prefix):
            errors.append(f"Row {idx + 1}: bank header does not match expected bank {args.bank}")

        row_date = _parse_date(csv_row["date"])
        if expected_start and row_date < expected_start:
            errors.append(f"Row {idx + 1}: date {row_date} is before expected start {expected_start}")
        if expected_end and row_date > expected_end:
            errors.append(f"Row {idx + 1}: date {row_date} is after expected end {expected_end}")

        if csv_row["type"] == "debit":
            debit_count += 1
            if detail_first.startswith("Paid to "):
                counterparty = detail_first.removeprefix("Paid to ").strip()
                if counterparty in generator.MERCHANTS:
                    merchant_debit_count += 1
                else:
                    person_debit_count += 1
        elif csv_row["type"] == "credit":
            credit_count += 1
            if detail_first.startswith("Received from "):
                counterparty = detail_first.removeprefix("Received from ").strip()
                if counterparty in generator.MERCHANTS:
                    merchant_credit_count += 1

    if csv_rows and len(header_values) != 1:
        errors.append(
            "Statement account header is not consistent across rows: "
            + ", ".join(sorted(header_values))
        )

    total = len(csv_rows)
    if total:
        debit_ratio = debit_count / total
        credit_ratio = credit_count / total
        merchant_debit_ratio = merchant_debit_count / max(debit_count, 1)
        person_debit_ratio = person_debit_count / max(debit_count, 1)
        merchant_credit_ratio = merchant_credit_count / max(credit_count, 1)

        if debit_ratio < 0.60:
            errors.append(f"Debit-heavy mix failed: debit ratio {debit_ratio:.2%} is too low")
        if credit_ratio > 0.40:
            errors.append(f"Credit mix failed: credit ratio {credit_ratio:.2%} is too high")

        if thresholds:
            if "min_debit_ratio" in thresholds and debit_ratio < thresholds["min_debit_ratio"]:
                errors.append(
                    f"Profile {args.profile}: debit ratio {debit_ratio:.2%} is below "
                    f"{thresholds['min_debit_ratio']:.2%}"
                )
            if "max_person_debit_ratio" in thresholds and person_debit_ratio > thresholds["max_person_debit_ratio"]:
                errors.append(
                    f"Profile {args.profile}: person debit ratio {person_debit_ratio:.2%} exceeds "
                    f"{thresholds['max_person_debit_ratio']:.2%}"
                )
            if "min_person_debit_ratio" in thresholds and person_debit_ratio < thresholds["min_person_debit_ratio"]:
                errors.append(
                    f"Profile {args.profile}: person debit ratio {person_debit_ratio:.2%} is below "
                    f"{thresholds['min_person_debit_ratio']:.2%}"
                )
            if "min_merchant_debit_ratio" in thresholds and merchant_debit_ratio < thresholds["min_merchant_debit_ratio"]:
                errors.append(
                    f"Profile {args.profile}: merchant debit ratio {merchant_debit_ratio:.2%} is below "
                    f"{thresholds['min_merchant_debit_ratio']:.2%}"
                )
            if "max_merchant_credit_ratio" in thresholds and merchant_credit_ratio > thresholds["max_merchant_credit_ratio"]:
                errors.append(
                    f"Profile {args.profile}: merchant credit ratio {merchant_credit_ratio:.2%} exceeds "
                    f"{thresholds['max_merchant_credit_ratio']:.2%}"
                )

    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    print(f"OK: {total} rows")
    print(f"CSV/JSON parity: matched")
    print(f"Debit/Credit mix: {debit_count}/{credit_count}")
    print(f"Merchant debit rows: {merchant_debit_count}")
    print(f"Merchant credit rows: {merchant_credit_count}")
    if header_values:
        print(f"Header: {next(iter(header_values))}")
    if expected_start and expected_end:
        print(f"Date range: {expected_start.isoformat()} -> {expected_end.isoformat()}")
    if args.profile:
        print(f"Profile: {args.profile}")
    if args.bank:
        print(f"Bank: {args.bank}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
