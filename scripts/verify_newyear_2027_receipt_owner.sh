#!/usr/bin/env bash
set -euo pipefail

RECEIPT="${1:?receipt path required}"
case "$RECEIPT" in
  newyear_2027/receipts/*/*.json) ;;
  *) echo "[FAIL] invalid receipt path: $RECEIPT" >&2; exit 2 ;;
esac

ROOT="$(git rev-parse --show-toplevel)"
LOCAL="$ROOT/$RECEIPT"
[ -f "$LOCAL" ] || { echo "[FAIL] local receipt missing: $LOCAL" >&2; exit 3; }
TMP="$(mktemp "${RUNNER_TEMP:-/tmp}/ny2027-owner.XXXXXX.json")"
trap 'rm -f "$TMP"' EXIT

git -C "$ROOT" fetch --quiet origin main
git -C "$ROOT" show "origin/main:$RECEIPT" > "$TMP" || {
  echo "[FAIL] durable receipt missing on origin/main: $RECEIPT" >&2
  exit 4
}
python3 "$ROOT/newyear_2027_runner.py" receipt-owner --durable "$TMP" --local "$LOCAL"
