#!/usr/bin/env bash
set -euo pipefail

RECEIPT="${1:?receipt path required}"
MESSAGE="${2:?commit message required}"

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
mkdir -p "$(dirname "$WT/$RECEIPT")"
cp "$SOURCE" "$WT/$RECEIPT"

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
