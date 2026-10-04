#!/usr/bin/env bash
set -euo pipefail

BRANCH="$1"
MAX_ATTEMPTS=5

resolve_safe_rebase_conflicts() {
  local conflicts
  conflicts="$(git diff --name-only --diff-filter=U)"
  [ -n "$conflicts" ] || return 1

  local f
  while IFS= read -r f; do
    case "$f" in
      threads_growth_state.json|threads_growth_report.md|threads_growth_capabilities.json|threads_growth_PAUSED.json|cards/*/threads_pub_*.json|cards/*/youtube_pub*.json|cards/*/instagram_pub_*.json|promo/*/pub_*.json)
        echo "[WARN] safe-push conflict: keeping newer origin/$BRANCH for volatile state: $f"
        git checkout --ours -- "$f"
        git add "$f"
        ;;
      *)
        echo "[FAIL] safe-push rebase conflict needs manual handling: $f"
        return 1
        ;;
    esac
  done <<< "$conflicts"

  if git diff --cached --quiet; then
    git rebase --skip
  else
    GIT_EDITOR=true git rebase --continue
  fi
}

for ATTEMPT in 1 2 3 4 5; do
  git fetch --quiet origin "$BRANCH"

  if ! git rebase "origin/$BRANCH"; then
    if ! resolve_safe_rebase_conflicts; then
      git rebase --abort >/dev/null 2>&1 || true
      exit 1
    fi
  fi

  if git push origin "HEAD:$BRANCH"; then
    echo "[OK] safe-push success (attempt $ATTEMPT/$MAX_ATTEMPTS)"
    exit 0
  fi

  if [ "$ATTEMPT" = "$MAX_ATTEMPTS" ]; then
    echo "[FAIL] safe-push failed after $MAX_ATTEMPTS attempts"
    exit 1
  fi

  echo "[WARN] origin/$BRANCH advanced; rebasing and retrying ($ATTEMPT/$MAX_ATTEMPTS)"
  sleep $((ATTEMPT * 2))
done
