"""Synthetic statement generator for dummy UPI / bank statement records.

The generator emits one canonical in-memory record set and serializes it to
both CSV and JSON so the two outputs always stay in sync.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable, Optional


MERCHANTS = [
    "Amazon India",
    "Flipkart",
    "Swiggy",
    "Zomato",
    "BigBasket",
    "Blinkit",
    "Zepto",
    "Uber",
    "Ola",
    "MakeMyTrip",
    "IRCTC",
    "Ajio",
    "Myntra",
    "Tata 1mg",
    "Apollo Pharmacy",
    "Reliance Digital",
    "Croma",
    "Decathlon",
    "BookMyShow",
    "Netflix",
    "Spotify",
    "Prime Video",
    "Hotstar",
    "Jio",
    "Airtel",
    "Vodafone Idea",
    "DMart",
    "Nike",
    "Adidas",
    "H&M",
    "Pepperfry",
    "Urban Company",
    "Lenskart",
    "NoBroker",
    "PVR Cinemas",
    "Shell",
    "HP Petrol",
    "IndianOil",
    "SBI Card",
    "ICICI Bank",
    "HDFC Bank",
    "Axis Bank",
    "Bajaj Finance",
    "Tanishq",
    "Titan",
    "Westside",
    "Fabindia",
    "IKEA",
    "Swastik Travels",
    "Cloud Kitchen",
]

FIRST_NAMES = [
    "Aarav",
    "Aanya",
    "Aditya",
    "Ananya",
    "Arjun",
    "Diya",
    "Ishaan",
    "Kavya",
    "Krish",
    "Meera",
    "Nisha",
    "Rahul",
    "Riya",
    "Saanvi",
    "Siddharth",
    "Tanya",
    "Vihaan",
    "Varun",
    "Yash",
    "Zoya",
]

LAST_NAMES = [
    "Sharma",
    "Verma",
    "Gupta",
    "Mehta",
    "Iyer",
    "Reddy",
    "Nair",
    "Kapoor",
    "Singh",
    "Chopra",
    "Patel",
    "Bose",
    "Pillai",
    "Joshi",
    "Malhotra",
    "Khan",
    "Das",
    "Saxena",
    "Kulkarni",
    "Bhatia",
]

ACCOUNT_BANKS = [
    "HDFC Bank",
    "ICICI Bank",
    "SBI",
    "Axis Bank",
    "Kotak Mahindra Bank",
    "IndusInd Bank",
    "Federal Bank",
]

BANK_HEADER_TEMPLATES = {
    "HDFC Bank": "HDFC Bank A/C XX{suffix}",
    "ICICI Bank": "ICICI Bank A/C XX{suffix}",
    "SBI": "State Bank of India A/C XX{suffix}",
    "Axis Bank": "Axis Bank A/C XX{suffix}",
    "Kotak Mahindra Bank": "Kotak Bank A/C XX{suffix}",
    "IndusInd Bank": "IndusInd Bank A/C XX{suffix}",
    "Federal Bank": "Federal Bank A/C XX{suffix}",
}

BANK_INPUTS = ACCOUNT_BANKS + ["random"]

MERCHANT_GROUPS = {
    "groceries": ("BigBasket", "Blinkit", "Zepto", "DMart"),
    "food": ("Swiggy", "Zomato", "Cloud Kitchen"),
    "transport": ("Uber", "Ola", "IRCTC", "MakeMyTrip", "Swastik Travels"),
    "shopping": (
        "Amazon India",
        "Flipkart",
        "Ajio",
        "Myntra",
        "Nike",
        "Adidas",
        "H&M",
        "Pepperfry",
        "Urban Company",
        "Westside",
        "Fabindia",
        "IKEA",
    ),
    "bills": (
        "Jio",
        "Airtel",
        "Vodafone Idea",
        "SBI Card",
        "ICICI Bank",
        "HDFC Bank",
        "Axis Bank",
        "Bajaj Finance",
    ),
    "health": ("Tata 1mg", "Apollo Pharmacy", "Lenskart"),
    "fuel": ("Shell", "HP Petrol", "IndianOil"),
    "entertainment": (
        "BookMyShow",
        "Netflix",
        "Spotify",
        "Prime Video",
        "Hotstar",
        "PVR Cinemas",
    ),
    "finance": ("SBI Card", "ICICI Bank", "HDFC Bank", "Axis Bank", "Bajaj Finance"),
    "other": ("Reliance Digital", "Croma", "Decathlon", "NoBroker", "Tanishq", "Titan"),
}

DEFAULT_MONTHLY_INCOME = 120000.0
DEFAULT_MONTHLY_EXPENSE = 90000.0
DEFAULT_PERIOD = "quarterly"
DEFAULT_PROFILE = "salary-heavy"
DEFAULT_BANK = "random"
DEFAULT_OUTPUT_ROOT = Path(__file__).resolve().parent / "runs"

GENERATOR_VERSION = "1.0"


@dataclass(frozen=True)
class ProfileSpec:
    name: str
    description: str
    merchant_weights: dict[str, float]
    debit_person_prob: float
    credit_extra_chance: float
    credit_extra_split_range: tuple[float, float]
    credit_extra_person_prob: float
    debit_count_divisor_range: tuple[float, float]
    amount_small_range: tuple[float, float]
    amount_medium_range: tuple[float, float]
    amount_large_range: tuple[float, float]
    tier_weights: tuple[float, float, float]
    outlier_boost: float


PROFILE_SPECS = {
    "salary-heavy": ProfileSpec(
        name="salary-heavy",
        description="Salary-like inflows, mostly merchant debits, low person-to-person movement.",
        merchant_weights={
            "groceries": 3.0,
            "food": 2.2,
            "transport": 1.8,
            "shopping": 1.2,
            "bills": 2.0,
            "health": 1.0,
            "fuel": 1.0,
            "entertainment": 0.8,
            "finance": 0.7,
            "other": 0.6,
        },
        debit_person_prob=0.10,
        credit_extra_chance=0.20,
        credit_extra_split_range=(0.72, 0.88),
        credit_extra_person_prob=0.72,
        debit_count_divisor_range=(1800, 4600),
        amount_small_range=(90, 650),
        amount_medium_range=(650, 3200),
        amount_large_range=(3200, 16000),
        tier_weights=(0.22, 0.66, 0.12),
        outlier_boost=2.8,
    ),
    "student": ProfileSpec(
        name="student",
        description="Smaller spends, more food/transport/entertainment, more peer reimbursements.",
        merchant_weights={
            "groceries": 1.0,
            "food": 3.2,
            "transport": 2.4,
            "shopping": 0.9,
            "bills": 0.8,
            "health": 0.6,
            "fuel": 0.4,
            "entertainment": 2.8,
            "finance": 0.4,
            "other": 0.7,
        },
        debit_person_prob=0.24,
        credit_extra_chance=0.40,
        credit_extra_split_range=(0.60, 0.82),
        credit_extra_person_prob=0.84,
        debit_count_divisor_range=(900, 2200),
        amount_small_range=(40, 350),
        amount_medium_range=(350, 1800),
        amount_large_range=(1800, 7000),
        tier_weights=(0.38, 0.52, 0.10),
        outlier_boost=2.2,
    ),
    "family-expense": ProfileSpec(
        name="family-expense",
        description="Groceries, medicines, fuel and bills dominate; some family transfers and travel.",
        merchant_weights={
            "groceries": 3.6,
            "food": 1.6,
            "transport": 1.3,
            "shopping": 1.0,
            "bills": 2.8,
            "health": 2.2,
            "fuel": 2.6,
            "entertainment": 0.7,
            "finance": 0.9,
            "other": 0.9,
        },
        debit_person_prob=0.16,
        credit_extra_chance=0.28,
        credit_extra_split_range=(0.68, 0.86),
        credit_extra_person_prob=0.60,
        debit_count_divisor_range=(1500, 3600),
        amount_small_range=(80, 500),
        amount_medium_range=(500, 2600),
        amount_large_range=(2600, 12000),
        tier_weights=(0.26, 0.62, 0.12),
        outlier_boost=2.5,
    ),
}


@dataclass(frozen=True)
class RunConfig:
    start_date: date
    end_date: date
    monthly_income: float
    monthly_expense: float
    seed: Optional[int]
    profile: str
    bank: str
    output_dir: Path


def _parse_amount(raw: str, label: str) -> float:
    try:
        value = float(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"{label} must be numeric") from exc
    if value <= 0:
        raise argparse.ArgumentTypeError(f"{label} must be greater than zero")
    return value


def _parse_date(raw: str, label: str) -> date:
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"{label} must use YYYY-MM-DD"
        ) from exc


def _parse_range(raw: str) -> tuple[date, date]:
    if ":" not in raw:
        raise argparse.ArgumentTypeError(
            "--range must use START:END in YYYY-MM-DD format"
        )
    start_raw, end_raw = raw.split(":", 1)
    start = _parse_date(start_raw, "range start")
    end = _parse_date(end_raw, "range end")
    if start > end:
        raise argparse.ArgumentTypeError("range start must be <= range end")
    return start, end


def _prompt(message: str, *, default: str | None = None) -> str:
    suffix = f" [{default}]" if default is not None else ""
    value = input(f"{message}{suffix}: ").strip()
    return value or (default or "")


def _prompt_float(message: str, default: float) -> float:
    while True:
        raw = _prompt(message, default=f"{default:.2f}")
        try:
            return _parse_amount(raw, message)
        except argparse.ArgumentTypeError as exc:
            print(exc, file=sys.stderr)


def _prompt_date(message: str, default: date) -> date:
    while True:
        raw = _prompt(message, default=default.isoformat())
        try:
            return _parse_date(raw, message)
        except argparse.ArgumentTypeError as exc:
            print(exc, file=sys.stderr)


def _prompt_int(message: str) -> Optional[int]:
    raw = _prompt(message, default="")
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        print(f"{message} must be an integer", file=sys.stderr)
        return _prompt_int(message)


def _choose_period(prompt_enabled: bool, provided: str | None) -> str:
    if provided:
        return provided
    if not prompt_enabled:
        return DEFAULT_PERIOD
    print("Select a period mode:")
    print("  1) weekly")
    print("  2) monthly")
    print("  3) quarterly")
    print("  4) annually")
    print("  5) custom range")
    while True:
        choice = _prompt("Period", default="3")
        mapping = {
            "1": "weekly",
            "2": "monthly",
            "3": "quarterly",
            "4": "annually",
            "5": "custom",
            "weekly": "weekly",
            "monthly": "monthly",
            "quarterly": "quarterly",
            "annually": "annually",
            "annual": "annually",
            "custom": "custom",
        }
        selected = mapping.get(choice.lower())
        if selected:
            return selected
        print("Please choose 1, 2, 3, 4, 5, or one of the named options.")


def _choose_profile(prompt_enabled: bool, provided: str | None) -> str:
    if provided:
        value = provided.strip().lower()
        if value not in PROFILE_SPECS:
            raise SystemExit(
                f"Unknown profile '{provided}'. Choose one of: "
                + ", ".join(PROFILE_SPECS)
            )
        return value
    if not prompt_enabled:
        return DEFAULT_PROFILE
    print("Select a profile:")
    for idx, (name, spec) in enumerate(PROFILE_SPECS.items(), start=1):
        print(f"  {idx}) {name} - {spec.description}")
    options = {str(idx): name for idx, name in enumerate(PROFILE_SPECS, start=1)}
    while True:
        choice = _prompt("Profile", default="1")
        if choice.lower() in PROFILE_SPECS:
            return choice.lower()
        selected = options.get(choice)
        if selected:
            return selected
        print("Please choose one of the listed profile numbers or names.")


def _choose_bank(prompt_enabled: bool, provided: str | None) -> str:
    if provided:
        value = provided.strip()
        if value.lower() == "random":
            return DEFAULT_BANK
        canonical = next((name for name in ACCOUNT_BANKS if name.lower() == value.lower()), None)
        if canonical is None:
            raise SystemExit(
                f"Unknown bank '{provided}'. Choose one of: "
                + ", ".join(BANK_INPUTS)
            )
        return canonical
    if not prompt_enabled:
        return DEFAULT_BANK
    print("Select a bank (or random):")
    for idx, name in enumerate(BANK_INPUTS, start=1):
        print(f"  {idx}) {name}")
    options = {str(idx): name for idx, name in enumerate(BANK_INPUTS, start=1)}
    while True:
        choice = _prompt("Bank", default="random")
        if choice.lower() == "random":
            return DEFAULT_BANK
        canonical = next((name for name in ACCOUNT_BANKS if name.lower() == choice.lower()), None)
        if canonical:
            return canonical
        selected = options.get(choice)
        if selected:
            return selected
        print("Please choose one of the listed bank numbers or names.")


def _rolling_start(end_date: date, period: str) -> date:
    days = {"weekly": 6, "monthly": 29, "quarterly": 89, "annually": 364}[period]
    return end_date - timedelta(days=days)


def _month_windows(start: date, end: date) -> list[tuple[date, date]]:
    windows: list[tuple[date, date]] = []
    cursor = date(start.year, start.month, 1)
    while cursor <= end:
        if cursor.month == 12:
            next_month = date(cursor.year + 1, 1, 1)
        else:
            next_month = date(cursor.year, cursor.month + 1, 1)
        window_start = max(start, cursor)
        window_end = min(end, next_month - timedelta(days=1))
        if window_start <= window_end:
            windows.append((window_start, window_end))
        cursor = next_month
    return windows


def _pick_weekday(rng: random.Random, start: date, end: date) -> date:
    candidates = []
    current = start
    while current <= end:
        candidates.append(current)
        current += timedelta(days=1)
    weekdays = [d for d in candidates if d.weekday() < 5]
    pool = weekdays or candidates
    return rng.choice(pool)


def _pick_date(rng: random.Random, start: date, end: date) -> date:
    current = start + timedelta(days=rng.randint(0, (end - start).days))
    return current


def _pick_time(rng: random.Random) -> str:
    hour = rng.choices(
        population=[8, 9, 11, 13, 15, 18, 20, 22],
        weights=[2, 5, 8, 7, 8, 6, 4, 2],
        k=1,
    )[0]
    minute = rng.randint(0, 59)
    second = rng.randint(0, 59)
    return f"{hour:02d}:{minute:02d}:{second:02d}"


def _group_merchant(name: str) -> str:
    lowered = name.lower()
    for group, merchants in MERCHANT_GROUPS.items():
        if any(marker.lower() in lowered for marker in merchants):
            return group
    return "other"


def _choose_profile_merchant(
    rng: random.Random, merchant_pool: list[str], profile: ProfileSpec
) -> str:
    grouped: dict[str, list[str]] = {}
    for merchant in merchant_pool:
        grouped.setdefault(_group_merchant(merchant), []).append(merchant)
    groups = [name for name, items in grouped.items() if items]
    if not groups:
        return rng.choice(merchant_pool)
    weights = [profile.merchant_weights.get(group, 0.5) for group in groups]
    chosen_group = rng.choices(groups, weights=weights, k=1)[0]
    return rng.choice(grouped[chosen_group])


def _build_person_pool(rng: random.Random, size: int = 40) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    while len(names) < size:
        candidate = f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
        if candidate not in seen:
            seen.add(candidate)
            names.append(candidate)
    return names


def _account_header(rng: random.Random, bank: str) -> str:
    bank_name = rng.choice(ACCOUNT_BANKS) if bank == DEFAULT_BANK else bank
    suffix = "".join(str(rng.randint(0, 9)) for _ in range(4))
    template = BANK_HEADER_TEMPLATES.get(bank_name, "{bank} A/C XX{suffix}")
    return template.format(bank=bank_name, suffix=suffix)


def _txn_id(rng: random.Random, current_date: date, index: int) -> str:
    return f"TXN{current_date.strftime('%Y%m%d')}{index:03d}{rng.randint(10, 99)}"


def _utr_no(rng: random.Random, current_date: date, index: int) -> str:
    return f"UTR{current_date.strftime('%Y%m%d')}{index:03d}{rng.randint(1000, 9999)}"


def _detail_block(
    *,
    direction: str,
    counterparty: str,
    txn_id: str,
    utr_no: str,
    account_header: str,
) -> list[str]:
    if direction == "debit":
        first = f"Paid to {counterparty}"
        fourth = f"Paid by {account_header}"
    else:
        first = f"Received from {counterparty}"
        fourth = f"Credited to {account_header}"
    return [first, f"Transaction ID: {txn_id}", f"UTR No.: {utr_no}", fourth]


def _choice_weighted(rng: random.Random, items: list[str], weights: list[float]) -> str:
    return rng.choices(items, weights=weights, k=1)[0]


def _generate_amounts(
    rng: random.Random,
    target: float,
    count: int,
    *,
    profile: ProfileSpec,
) -> list[float]:
    if count <= 0:
        return []

    raw: list[float] = []
    for _ in range(count):
        tier = rng.choices(
            population=["small", "medium", "large"],
            weights=list(profile.tier_weights),
            k=1,
        )[0]
        if tier == "small":
            value = rng.uniform(*profile.amount_small_range)
        elif tier == "medium":
            value = rng.uniform(*profile.amount_medium_range)
        else:
            value = rng.uniform(*profile.amount_large_range)
        raw.append(value)

    if count >= 6:
        for idx in rng.sample(range(count), k=max(1, count // 8)):
            raw[idx] *= rng.uniform(profile.outlier_boost * 0.6, profile.outlier_boost * 1.4)

    scale = target / sum(raw)
    amounts = [round(value * scale, 2) for value in raw]
    # Spread the rounding residual one paisa at a time across rows rather than
    # dumping the whole remainder onto the last amount (which can visibly skew
    # one row). The total residual is only a few paise, so this stays subtle.
    residual_paise = round((target - sum(amounts)) * 100)
    step = 0.01 if residual_paise > 0 else -0.01
    for offset in range(abs(residual_paise)):
        idx = offset % len(amounts)
        amounts[idx] = round(amounts[idx] + step, 2)
    return amounts


def _generate_month_segment(
    rng: random.Random,
    *,
    segment_start: date,
    segment_end: date,
    account_header: str,
    person_pool: list[str],
    monthly_income: float,
    monthly_expense: float,
    merchant_pool: list[str],
    profile: ProfileSpec,
) -> list[dict[str, object]]:
    days = (segment_end - segment_start).days + 1
    proration = days / 30.4375
    income_target = max(0.01, monthly_income * proration)
    expense_target = max(0.01, monthly_expense * proration)

    txns: list[dict[str, object]] = []

    # Credits are intentionally few: mostly one salary-style inflow and, only
    # sometimes, a second peer refund / reimbursement line.
    credit_count = 1 + int(rng.random() < profile.credit_extra_chance)
    credit_amounts: list[float]
    if credit_count == 1:
        credit_amounts = [round(income_target, 2)]
    else:
        first = round(income_target * rng.uniform(*profile.credit_extra_split_range), 2)
        second = round(max(0.01, income_target - first), 2)
        credit_amounts = [first, second]

    salary_source = rng.choice(person_pool)
    peer_source = rng.choice([name for name in person_pool if name != salary_source]) if len(person_pool) > 1 else salary_source
    refund_source = rng.choice(merchant_pool)
    another_peer = rng.choice(
        [name for name in person_pool if name not in {salary_source, peer_source}]
        or person_pool
    )
    credit_dates = sorted(
        _pick_weekday(rng, segment_start, min(segment_end, segment_start + timedelta(days=6)))
        for _ in range(credit_count)
    )
    for index, amount in enumerate(credit_amounts, start=1):
        if index == 1:
            counterparty = salary_source
        else:
            merchant_refund_weight = 0.12 if profile.name == "salary-heavy" else 0.10
            peer_weight = profile.credit_extra_person_prob
            other_peer_weight = max(0.0, 1.0 - peer_weight - merchant_refund_weight)
            counterparty = _choice_weighted(
                rng,
                [peer_source, refund_source, another_peer],
                [peer_weight, merchant_refund_weight, other_peer_weight],
            )
        txn_day = credit_dates[min(index - 1, len(credit_dates) - 1)]
        txn_id = _txn_id(rng, txn_day, index)
        utr_no = _utr_no(rng, txn_day, index)
        txns.append(
            {
                "date": txn_day.isoformat(),
                "time": _pick_time(rng),
                "Transaction Detail": _detail_block(
                    direction="credit",
                    counterparty=counterparty,
                    txn_id=txn_id,
                    utr_no=utr_no,
                    account_header=account_header,
                ),
                "type": "credit",
                "amount": amount,
                "_sort_key": f"{txn_day.isoformat()} {index:03d} {index:03d}",
            }
        )

    debit_target = max(0.01, expense_target * rng.uniform(0.96, 1.04))
    debit_count = max(8, int(round(debit_target / rng.uniform(*profile.debit_count_divisor_range))))
    debit_amounts = _generate_amounts(rng, debit_target, debit_count, profile=profile)

    for index, amount in enumerate(debit_amounts, start=1):
        txn_day = _pick_date(rng, segment_start, segment_end)
        if txn_day.weekday() < 5 and rng.random() < 0.75:
            txn_day = _pick_weekday(rng, segment_start, segment_end)
        counterparty = (
            rng.choice(person_pool)
            if rng.random() < profile.debit_person_prob
            else _choose_profile_merchant(rng, merchant_pool, profile)
        )
        txn_id = _txn_id(rng, txn_day, 100 + index)
        utr_no = _utr_no(rng, txn_day, 100 + index)
        txns.append(
            {
                "date": txn_day.isoformat(),
                "time": _pick_time(rng),
                "Transaction Detail": _detail_block(
                    direction="debit",
                    counterparty=counterparty,
                    txn_id=txn_id,
                    utr_no=utr_no,
                    account_header=account_header,
                ),
                "type": "debit",
                "amount": amount,
                "_sort_key": f"{txn_day.isoformat()} {100 + index:03d} {index:03d}",
            }
        )

    return txns


def _generate_records(config: RunConfig) -> list[dict[str, object]]:
    rng = random.Random(config.seed)
    person_pool = _build_person_pool(rng, size=40)
    profile = PROFILE_SPECS[config.profile]
    account_header = _account_header(rng, config.bank)

    records: list[dict[str, object]] = []
    for segment_start, segment_end in _month_windows(config.start_date, config.end_date):
        records.extend(
            _generate_month_segment(
                rng,
                segment_start=segment_start,
                segment_end=segment_end,
                account_header=account_header,
                person_pool=person_pool,
                monthly_income=config.monthly_income,
                monthly_expense=config.monthly_expense,
                merchant_pool=MERCHANTS,
                profile=profile,
            )
        )

    records.sort(key=lambda row: (row["date"], row["time"], row["_sort_key"]))
    for row in records:
        row.pop("_sort_key", None)
    return records


def _write_csv(path: Path, records: Iterable[dict[str, object]]) -> None:
    fieldnames = ["date", "time", "Transaction Detail", "type", "amount"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in records:
            writer.writerow(
                {
                    "date": row["date"],
                    "time": row["time"],
                    "Transaction Detail": json.dumps(
                        row["Transaction Detail"], ensure_ascii=False
                    ),
                    "type": row["type"],
                    "amount": f"{float(row['amount']):.2f}",
                }
            )


def _write_json(path: Path, records: list[dict[str, object]]) -> None:
    path.write_text(json.dumps(records, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_meta(path: Path, config: RunConfig, records: list[dict[str, object]]) -> None:
    """Persist the run parameters so a statement can be reproduced/verified later."""
    debit_count = sum(1 for row in records if row["type"] == "debit")
    meta = {
        "generator_version": GENERATOR_VERSION,
        "seed": config.seed,
        "start_date": config.start_date.isoformat(),
        "end_date": config.end_date.isoformat(),
        "profile": config.profile,
        "bank": config.bank,
        "monthly_income": config.monthly_income,
        "monthly_expense": config.monthly_expense,
        "row_count": len(records),
        "debit_count": debit_count,
        "credit_count": len(records) - debit_count,
    }
    path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")


def _print_summary(config: RunConfig, records: list[dict[str, object]], output_dir: Path) -> None:
    debit_total = sum(float(row["amount"]) for row in records if row["type"] == "debit")
    credit_total = sum(float(row["amount"]) for row in records if row["type"] == "credit")
    debit_count = sum(1 for row in records if row["type"] == "debit")
    credit_count = len(records) - debit_count
    print(f"Wrote {len(records)} rows to {output_dir}")
    print(f"  CSV : {output_dir / 'statement.csv'}")
    print(f"  JSON: {output_dir / 'statement.json'}")
    print(
        "  Mix : "
        f"{debit_count} debit / {credit_count} credit, "
        f"debit total={debit_total:.2f}, credit total={credit_total:.2f}"
    )
    print(
        f"  Range: {config.start_date.isoformat()} -> {config.end_date.isoformat()}, "
        f"profile={config.profile}, bank={config.bank}"
    )
    print(f"  Seed : {config.seed if config.seed is not None else 'random (not reproducible)'}")


def _build_config(args: argparse.Namespace) -> RunConfig:
    today = datetime.now().date()
    explicit_range = bool(args.range or (args.start and args.end))
    period = "custom" if explicit_range else _choose_period(not args.yes, args.period)
    profile = _choose_profile(not args.yes, args.profile)
    bank = _choose_bank(not args.yes, args.bank)

    if args.range:
        start_date, end_date = _parse_range(args.range)
    elif args.start or args.end:
        if not (args.start and args.end):
            raise SystemExit("Both --start and --end are required together")
        start_date = _parse_date(args.start, "--start")
        end_date = _parse_date(args.end, "--end")
        if start_date > end_date:
            raise SystemExit("--start must be <= --end")
    elif period == "custom":
        if args.yes:
            start_date = today - timedelta(days=29)
            end_date = today
        else:
            start_date = _prompt_date("Custom range start", today - timedelta(days=29))
            end_date = _prompt_date("Custom range end", today)
    else:
        end_date = today
        start_date = _rolling_start(end_date, period)

    if args.income is not None:
        monthly_income = args.income
    elif args.yes:
        monthly_income = DEFAULT_MONTHLY_INCOME
    else:
        monthly_income = _prompt_float("Average monthly income", DEFAULT_MONTHLY_INCOME)

    if args.expense is not None:
        monthly_expense = args.expense
    elif args.yes:
        monthly_expense = DEFAULT_MONTHLY_EXPENSE
    else:
        monthly_expense = _prompt_float("Average monthly expense", DEFAULT_MONTHLY_EXPENSE)

    if args.seed is not None:
        seed = args.seed
    elif args.yes:
        seed = None
    else:
        seed = _prompt_int("Optional seed (blank for random)")

    if args.output_dir:
        output_dir = Path(args.output_dir).expanduser().resolve()
    else:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = DEFAULT_OUTPUT_ROOT / stamp

    output_dir.mkdir(parents=True, exist_ok=True)
    return RunConfig(
        start_date=start_date,
        end_date=end_date,
        monthly_income=monthly_income,
        monthly_expense=monthly_expense,
        seed=seed,
        profile=profile,
        bank=bank,
        output_dir=output_dir,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate dummy UPI / bank statement records as CSV and JSON."
    )
    parser.add_argument("-y", "--yes", action="store_true", help="Use defaults without prompting")
    parser.add_argument(
        "--period",
        choices=["weekly", "monthly", "quarterly", "annually", "custom"],
        help="Rolling period to generate when no explicit date range is provided",
    )
    parser.add_argument(
        "--profile",
        choices=sorted(PROFILE_SPECS),
        help="Preset mix profile that tunes merchant/person balance and amount patterns",
    )
    parser.add_argument(
        "--bank",
        choices=BANK_INPUTS,
        help="Account bank to stamp into the statement header",
    )
    parser.add_argument(
        "--range",
        help="Explicit date range in START:END form, both YYYY-MM-DD",
    )
    parser.add_argument("--start", help="Explicit start date, YYYY-MM-DD")
    parser.add_argument("--end", help="Explicit end date, YYYY-MM-DD")
    parser.add_argument("--income", type=lambda raw: _parse_amount(raw, "--income"))
    parser.add_argument("--expense", type=lambda raw: _parse_amount(raw, "--expense"))
    parser.add_argument("--seed", type=int, help="Optional RNG seed for reproducible output")
    parser.add_argument(
        "--output-dir",
        help="Write files into this directory instead of a timestamped run folder",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = _build_config(args)
    records = _generate_records(config)
    _write_csv(config.output_dir / "statement.csv", records)
    _write_json(config.output_dir / "statement.json", records)
    _write_meta(config.output_dir / "meta.json", config, records)
    _print_summary(config, records, config.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
