# Dummy Statement Generator

A toolkit for generating **synthetic** UPI / bank statement records, rendering
them as PhonePe / Paytm / Google Pay-styled PDFs, and parsing those PDFs back
into normalized transaction rows. Useful for building and testing statement
parsers without real, personal financial data.

Everything it ships is synthetic. The only real data it ever touches is a
statement *you* drop in to calibrate a parser — and the repo is configured to
keep those out of version control (see [Privacy](#privacy)).

## Privacy

- **Never commit a real statement.** `.gitignore` excludes any `*.pdf` / `*.csv`
  / `*.json` at the repo root — the spot where you drop a real statement for
  calibration. Synthetic samples under `fixtures/` are tracked on purpose.
- The test suite reads a real statement only at runtime (and skips entirely when
  none is present); no real names, account numbers, UPI IDs, or amounts are
  embedded in any source, test, or doc. Calibration tests derive their
  expectations from the statement's own summary header at runtime.

## What it produces

- `statement.csv`
- `statement.json`
- `meta.json` — the run parameters (seed, range, profile, bank, income/expense,
  row counts) so a statement can be reproduced and verified later

Both files are written from the same in-memory record set so they always match.
Each row contains:

- `date`
- `time`
- `Transaction Detail`
- `type` (`debit` / `credit`)
- `amount`

`Transaction Detail` is a list with four items:

- `Paid to X` or `Received from X`
- `Transaction ID: ...`
- `UTR No.: ...`
- `Paid by ...` or `Credited to ...`

The CSV stores that block as a JSON string in one cell.

## Quick start

Use the local virtualenv only:

```bash
./generate_statement.sh -y
```

That writes a fresh timestamped folder under `dummy-statement/runs/`.

## Interactive mode

Run without `-y` to be prompted for the values the generator needs:

```bash
./generate_statement.sh
```

You can provide flags instead of prompts:

```bash
./generate_statement.sh --period quarterly --income 150000 --expense 110000
./generate_statement.sh --range 2026-01-01:2026-03-31 --seed 42
./generate_statement.sh --start 2026-01-01 --end 2026-01-31 -y
```

## Flags

- `-y`, `--yes`: skip prompts and use defaults
- `--period`: `weekly`, `monthly`, `quarterly`, `annually`, or `custom`
- `--profile`: `salary-heavy`, `student`, or `family-expense` — tunes the
  merchant/person mix and amount patterns
- `--bank`: one of the supported banks (or `random`) stamped into the
  statement header
- `--range`: explicit `START:END` range, both `YYYY-MM-DD`
- `--start` / `--end`: explicit dates without the compact range form
- `--income`: average monthly income used to shape credit totals
- `--expense`: average monthly expense used to shape debit totals
- `--seed`: optional random seed for reproducible output
- `--output-dir`: write files into a specific directory instead of a
  timestamped run folder

## Defaults

- Period: `quarterly`
- Profile: `salary-heavy`
- Bank: `random`
- Income: `120000`
- Expense: `90000`
- Output: a new timestamped directory under `dummy-statement/runs/`
- Seed: random unless you provide one

## Verifying

`verify_statement.sh` validates a generated folder: CSV ↔ JSON parity, the
date window, header consistency, and the per-profile mix heuristics.

```bash
./verify_statement.sh dummy-statement/runs/<stamp>
```

When the folder contains a `meta.json` (every fresh run writes one), the
verifier reads the expected range, profile, and bank from it, so no flags are
needed. You can still override any expectation explicitly:

```bash
./verify_statement.sh path/to/run --range 2026-01-01:2026-03-31 --profile salary-heavy --bank "HDFC Bank"
```

## Self-test

`selftest.sh` is a dependency-free smoke test: it generates a seeded statement
for every profile and verifies each one. Run it after changing the generator or
verifier:

```bash
./selftest.sh
```

## Tests

The generator and verifier ship with a `pytest` suite under `tests/`. The tool
itself is pure standard library; `pytest` is only needed to run the tests:

```bash
.venv/bin/pip install -r requirements.txt
.venv/bin/pytest
```

`tests/test_verify_statement.py` also pins the two header-handling bugs the
verifier originally had, so they cannot silently regress.

## App-styled PDF statements + parsers

The canonical `statement.json` can be rendered into per-app PDF statements that
match how PhonePe / Paytm / Google Pay lay out their transaction history. The
PDFs are **text-based** (never images) so the backend's `pdftotext` pipeline can
read them back.

```bash
./generate_statement.sh -y --seed 7 --range 2026-01-05:2026-01-25 --output-dir runs/demo
./render_statement.sh runs/demo --app all        # writes phonepe.pdf / paytm.pdf / gpay.pdf
./render_statement.sh runs/demo --app paytm       # just one app
```

Layout:

```text
renderers/   phonepe.py · paytm.py · gpay.py   (+ common.py, fonts.py)
parsers/     phonepe_parser.py · paytm_parser.py · gpay_parser.py   (+ contract.py)
```

- **`parsers/paytm_parser.py` and `parsers/gpay_parser.py` are the deliverables.**
  They emit the same row contract as the backend's PhonePe parser (see
  `parsers/contract.py`) and are written to be lifted into
  `backend/app/modules/transactions/statement_upload/parsers/` + registered —
  the only edit needed is swapping the local `DEBIT`/`CREDIT` strings for the
  backend's `app.constants.DebitCredit` enum.
- **`parsers/phonepe_parser.py` is vendored from the backend** unchanged (bar the
  contract swap) so the whole render→`pdftotext`→parse harness is validated
  against a format production already accepts. Keep it in sync if the backend
  parser changes.
- **`fonts.py`** registers a Unicode TTF (DejaVuSans) so the `₹` glyph renders;
  without one it omits the symbol rather than emit a box the parser can't read.

### Round-trip tests

`tests/test_render_roundtrip.py` renders each app's PDF, runs `pdftotext`, parses
it back, and asserts the rows match the source JSON (count, date/time, amount,
debit/credit, beneficiary). It is skipped automatically if `pdftotext` is absent.

> ⚠️ The round-trip proves **renderer ↔ parser self-consistency**, not
> real-world fidelity. Each parser's assumed format is documented at the top of
> its module. Recalibrate against a real statement before relying on these in
> production.

### Calibrating against a real statement

`parsers/paytm_parser.py` has been calibrated against a real Paytm UPI Statement
(`Rs.` amounts, year-less `DD Mon` rows with the year in the period header,
unsigned credits, five wrapping columns). Drop a real statement PDF named
`Paytm*Statement*.pdf` into this folder and
`tests/test_paytm_real_statement.py` parses it and checks the parser reproduces
the totals the statement reports about itself (e.g. debit total == the header's
"Total Money Paid"). That test is the calibration anchor — it skips when no real
PDF is present, and the synthetic Paytm renderer was updated to emit the same
real format so the round-trip stays meaningful.

`parsers/gpay_parser.py` is still calibrated only to its reconstruction — drop a
real Google Pay statement in and add the equivalent anchor test to harden it.

## Notes

- The generator is parser-first and uses statement wording that lines up with
  the repo's existing PhonePe-style parser vocabulary.
- Merchant transactions are debit-heavy.
- Credit rows are intentionally few, and merchant credits only appear as rare
  refunds.
- The generator is designed to keep each period roughly balanced, with a small
  number of wider deviations so the data looks human rather than synthetic.

## Small fixture

A tiny local fixture is available at `dummy-statement/fixtures/sample_week_seed42/`.
It was generated with:

```bash
./generate_statement.sh -y --range 2026-05-31:2026-06-06 --seed 42 --output-dir dummy-statement/fixtures/sample_week_seed42
```

Use it as a stable example when you want to inspect the output shape without
creating a fresh timestamped run.
