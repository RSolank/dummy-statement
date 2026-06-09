"""Render a generated statement folder into per-app PDF statements.

Reads ``<run_dir>/statement.json`` and writes ``phonepe.pdf`` / ``paytm.pdf`` /
``gpay.pdf`` alongside it. The PDFs are text-based so the backend's
``pdftotext`` pipeline can read them back.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from renderers import gpay, paytm, phonepe  # noqa: E402

RENDERERS = {"phonepe": phonepe.render, "paytm": paytm.render, "gpay": gpay.render}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render statement.json into per-app PDF statements.")
    parser.add_argument("run_dir", help="Folder containing statement.json")
    parser.add_argument(
        "--app", choices=[*RENDERERS, "all"], default="all",
        help="Which app statement(s) to render (default: all)",
    )
    parser.add_argument("--holder", default="Sample User", help="Account holder name for the header")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run_dir = Path(args.run_dir).expanduser().resolve()
    json_path = run_dir / "statement.json"
    if not json_path.exists():
        print(f"Missing {json_path}", file=sys.stderr)
        return 1

    records = json.loads(json_path.read_text(encoding="utf-8"))
    apps = list(RENDERERS) if args.app == "all" else [args.app]
    for app in apps:
        out = RENDERERS[app](records, run_dir / f"{app}.pdf", holder=args.holder)
        print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
