#!/usr/bin/env bash
# Smoke test: generate a seeded statement for every profile and verify it.
# Run this after touching the generator or verifier so an always-failing
# verifier (or broken parity) can never ship unnoticed.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

RANGE="2026-01-01:2026-03-31"
SEED=42

for profile in salary-heavy student family-expense; do
  echo "=== $profile ==="
  "$SCRIPT_DIR/generate_statement.sh" -y \
    --range "$RANGE" --seed "$SEED" \
    --profile "$profile" --bank "HDFC Bank" \
    --output-dir "$TMP/$profile" >/dev/null
  # No flags needed: verify reads meta.json for the expected range/profile/bank.
  "$SCRIPT_DIR/verify_statement.sh" "$TMP/$profile"
done

echo
echo "selftest: all profiles generated + verified OK"
