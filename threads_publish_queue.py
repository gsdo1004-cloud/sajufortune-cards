"""Persistent Threads publish queue candidate.

Phase 1 is deliberately dry-run only: no network calls and no publishing.
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "state" / "threads_publish_queue.jsonl"
AUDIT = ROOT / "state" / "threads_publish_queue_audit.jsonl"
ACTIVE = {"PENDING", "RETRY", "RUNNING"}
TERMINAL = {"PUBLISHED", "FAILED", "FAILED_UNVERIFIED"}


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def load() -> list[dict]:
    if not STATE.exists():
        return []
    rows = []
    for line in STATE.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def save(rows: list[dict]) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".threads_queue_", dir=str(STATE.parent))
    os.close(fd)
    tmp = Path(name)
    with tmp.open("w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    tmp.replace(STATE)


def audit(event: dict) -> None:
    AUDIT.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")


def enqueue(key: str, scheduled_at: str, kind: str, target: str, payload: dict | None = None, max_retries: int = 3) -> dict:
    rows = load()
    if any(x.get("key") == key and x.get("status") in ACTIVE for x in rows):
        return {"ok": False, "reason": "duplicate_active_key", "key": key}
    row = {
        "key": key, "scheduled_at": scheduled_at, "kind": kind, "target": target,
        "status": "PENDING", "retry_count": 0, "max_retries": max_retries,
        "payload": payload or {},
        "lease_until": None, "last_error": None,
        "created_at": utcnow(), "updated_at": utcnow(),
    }
    rows.append(row)
    save(rows)
    audit({"at": utcnow(), "event": "ENQUEUE", "key": key})
    return {"ok": True, "item": row}


def due(at: str | None = None) -> list[dict]:
    at = at or utcnow()
    return [x for x in load()
            if x.get("status") in {"PENDING", "RETRY"}
            and str(x.get("scheduled_at", "")) <= at]



def claim(key: str, at: str | None = None, lease_seconds: int = 300) -> dict:
    at = at or utcnow()
    now_dt = datetime.fromisoformat(at)
    rows = load()
    for row in rows:
        if row.get("key") != key or row.get("status") not in {"PENDING", "RETRY"}:
            continue
        if str(row.get("scheduled_at", "")) > at:
            return {"ok": False, "reason": "not_due", "key": key}
        row["status"] = "RUNNING"
        row["lease_until"] = (now_dt + timedelta(seconds=lease_seconds)).isoformat()
        row["updated_at"] = at
        save(rows)
        audit({"at": at, "event": "CLAIM", "key": key, "lease_until": row["lease_until"]})
        return {"ok": True, "item": row}
    return {"ok": False, "reason": "not_claimable", "key": key}


def recover_expired(at: str | None = None) -> dict:
    at = at or utcnow()
    rows = load()
    recovered = []
    for row in rows:
        lease = row.get("lease_until")
        if row.get("status") == "RUNNING" and lease and str(lease) <= at:
            row["status"] = "RETRY"
            row["lease_until"] = None
            row["last_error"] = "expired_lease_recovered"
            row["updated_at"] = at
            recovered.append(row.get("key"))
    if recovered:
        save(rows)
        audit({"at": at, "event": "RECOVER_EXPIRED", "keys": recovered})
    return {"ok": True, "recovered": recovered}


def complete(key: str, threads_id: str, at: str | None = None) -> dict:
    at = at or utcnow()
    rows = load()
    for row in rows:
        if row.get("key") == key and row.get("status") == "RUNNING":
            row.update(status="PUBLISHED", threads_id=threads_id, published_at=at,
                       lease_until=None, last_error=None, updated_at=at)
            save(rows)
            audit({"at": at, "event": "PUBLISHED", "key": key, "threads_id": threads_id})
            return {"ok": True, "item": row}
    return {"ok": False, "reason": "not_running", "key": key}


def complete_ui(key: str, verification: dict, at: str | None = None) -> dict:
    """Complete a UI publish only with explicit on-screen verification metadata."""
    at = at or utcnow()
    if not verification.get("account") or not verification.get("exact_text"):
        return {"ok": False, "reason": "ui_verification_incomplete", "key": key}
    rows = load()
    for row in rows:
        if row.get("key") == key and row.get("status") == "RUNNING":
            row.update(status="PUBLISHED", published_at=at, lease_until=None, last_error=None,
                       updated_at=at, ui_verification=verification)
            save(rows)
            audit({"at": at, "event": "UI_PUBLISHED_VERIFIED", "key": key, "verification": verification})
            return {"ok": True, "item": row}
    return {"ok": False, "reason": "not_running", "key": key}


def fail(key: str, error: str, at: str | None = None) -> dict:
    at = at or utcnow()
    rows = load()
    for row in rows:
        if row.get("key") != key or row.get("status") != "RUNNING":
            continue
        row["retry_count"] = int(row.get("retry_count", 0)) + 1
        row["status"] = "FAILED" if row["retry_count"] >= int(row.get("max_retries", 3)) else "RETRY"
        row["lease_until"] = None
        row["last_error"] = error[:1000]
        row["updated_at"] = at
        save(rows)
        audit({"at": at, "event": row["status"], "key": key, "retry_count": row["retry_count"]})
        return {"ok": True, "item": row}
    return {"ok": False, "reason": "not_running", "key": key}



def fail_unverified(key: str, error: str = "receipt_not_verified", at: str | None = None) -> dict:
    """Terminal failure after a submit attempt; never auto-retry because publish may have succeeded."""
    at = at or utcnow()
    rows = load()
    for row in rows:
        if row.get("key") == key and row.get("status") == "RUNNING":
            row.update(status="FAILED_UNVERIFIED", lease_until=None, last_error=error[:1000], updated_at=at)
            save(rows); audit({"at": at, "event": "FAILED_UNVERIFIED", "key": key})
            return {"ok": True, "item": row}
    return {"ok": False, "reason": "not_running", "key": key}

def reconcile_zodiac_receipts(cards_root: Path | None = None, at: str | None = None) -> dict:
    """Mark queued zodiac jobs published when the existing publisher receipt exists."""
    at = at or utcnow()
    cards_root = cards_root or (ROOT / "cards")
    rows = load()
    matched = []
    invalid = []
    changed = False
    for row in rows:
        if row.get("kind") != "zodiac_carousel" or row.get("status") not in ACTIVE:
            continue
        target = str(row.get("target", ""))
        marker = cards_root / target / "threads_pub_carousel.json"
        if not marker.exists():
            continue
        try:
            receipt = json.loads(marker.read_text(encoding="utf-8"))
            threads_id = str(receipt.get("post_id", "")).strip()
        except Exception:
            threads_id = ""
        if not threads_id:
            invalid.append(row.get("key"))
            continue
        row.update(status="PUBLISHED", threads_id=threads_id, published_at=at,
                   lease_until=None, last_error=None, updated_at=at,
                   reconciled_from=str(marker))
        matched.append(row.get("key"))
        changed = True
    if changed:
        save(rows)
        audit({"at": at, "event": "RECONCILE_RECEIPTS", "keys": matched})
    return {"ok": True, "published": matched, "invalid_receipts": invalid}



def run_worker_once(publisher=None, at: str | None = None, live: bool = False) -> dict:
    """Process at most one due item. Live mode requires two explicit safety gates."""
    at = at or utcnow()
    recover_expired(at)
    ready = due(at)
    if not ready:
        return {"ok": True, "mode": "LIVE" if live else "DRY_RUN", "processed": 0}
    item = ready[0]
    if not live:
        return {"ok": True, "mode": "DRY_RUN", "processed": 0,
                "would_publish": item.get("key"), "external_calls": 0}
    if os.environ.get("THREADS_QUEUE_LIVE") != "1":
        return {"ok": False, "reason": "live_gate_disabled", "processed": 0}
    if publisher is None:
        return {"ok": False, "reason": "publisher_missing", "processed": 0}
    claimed = claim(str(item["key"]), at)
    if not claimed.get("ok"):
        return {"ok": False, "reason": "claim_failed", "processed": 0}
    try:
        threads_id = str(publisher(claimed["item"])).strip()
        if not threads_id:
            raise RuntimeError("publisher returned empty threads id")
        complete(str(item["key"]), threads_id, at)
        return {"ok": True, "mode": "LIVE", "processed": 1,
                "key": item["key"], "threads_id": threads_id}
    except Exception as exc:
        failed = fail(str(item["key"]), str(exc), at)
        return {"ok": False, "mode": "LIVE", "processed": 1,
                "key": item["key"], "status": failed.get("item", {}).get("status"),
                "error": str(exc)[:1000]}


def dry_run(at: str | None = None) -> dict:
    rows = load()
    ready = due(at)
    result = {
        "ok": True, "mode": "DRY_RUN", "queue_items": len(rows),
        "due_items": len(ready), "would_publish": [x.get("key") for x in ready],
        "external_calls": 0, "queue_mutations": 0, "checked_at": utcnow(),
    }
    audit({"at": utcnow(), "event": "DRY_RUN", **result})
    return result


def status() -> dict:
    rows = load()
    counts = {}
    for row in rows:
        s = str(row.get("status", "UNKNOWN"))
        counts[s] = counts.get(s, 0) + 1
    return {"ok": True, "count": len(rows), "by_status": counts}


def main() -> None:
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    en = sp.add_parser("enqueue")
    en.add_argument("--key", required=True)
    en.add_argument("--scheduled-at", required=True)
    en.add_argument("--kind", choices=["zodiac_carousel", "text", "promo", "threads_ui_reply"], required=True)
    en.add_argument("--target", required=True)
    sp.add_parser("dry-run")
    sp.add_parser("status")
    a = ap.parse_args()
    if a.cmd == "enqueue":
        result = enqueue(a.key, a.scheduled_at, a.kind, a.target)
    elif a.cmd == "dry-run":
        result = dry_run()
    else:
        result = status()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
