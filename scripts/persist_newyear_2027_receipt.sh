#!/usr/bin/env bash
set -euo pipefail

ACTION="${1:?claim or finalize required}"
RECEIPT="${2:?receipt path required}"
MESSAGE="${3:?commit message required}"

case "$ACTION" in claim|finalize) ;; *) echo "[FAIL] invalid action: $ACTION" >&2; exit 2 ;; esac
case "$RECEIPT" in
  newyear_2027/receipts/*/*.json) ;;
  *) echo "[FAIL] invalid receipt path: $RECEIPT" >&2; exit 2 ;;
esac

ROOT="$(git rev-parse --show-toplevel)"
SOURCE="$ROOT/$RECEIPT"
[ -f "$SOURCE" ] || { echo "[FAIL] receipt missing: $SOURCE" >&2; exit 3; }

TMP_BASE="${RUNNER_TEMP:-/tmp}"
mkdir -p "$TMP_BASE"
WT="$(mktemp -d "$TMP_BASE/ny2027-receipt.XXXXXX")"
cleanup() {
  git -C "$ROOT" worktree remove --force "$WT" >/dev/null 2>&1 || rm -rf "$WT"
}
trap cleanup EXIT

git -C "$ROOT" fetch --quiet origin main
git -C "$ROOT" worktree add --force --detach "$WT" origin/main >/dev/null
DURABLE="$WT/$RECEIPT"

# The verified runner decides whether this transition is safe. A claim is
# allowed only if main has no receipt. A finalize must match the exact claim.
python3 "$ROOT/newyear_2027_runner.py" receipt-transition \
  --action "$ACTION" --durable "$DURABLE" --incoming "$SOURCE"

mkdir -p "$(dirname "$DURABLE")"
cp "$SOURCE" "$DURABLE"

cd "$WT"
git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git add -- "$RECEIPT"
if git diff --cached --quiet; then
  echo "[SKIP] receipt already persisted: $RECEIPT"
  exit 0
fi
git commit -m "$MESSAGE"
bash scripts/safe_git_push.sh main

# A successful push is not enough: confirm origin/main still contains this run's
# unique owner token and exact receipt state before the caller may continue.
bash "$ROOT/scripts/verify_newyear_2027_receipt_owner.sh" "$RECEIPT"
