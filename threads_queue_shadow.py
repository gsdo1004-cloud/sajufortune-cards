"""Read-only shadow observer for the existing Threads zodiac publisher."""
from __future__ import annotations
import argparse, json
from datetime import datetime, timezone
from pathlib import Path
import threads_publish_queue as q

ROOT = Path(__file__).resolve().parent

def observe(cards_root: Path | None = None, now: str | None = None) -> dict:
    cards_root = cards_root or (ROOT / "cards")
    now = now or datetime.now(timezone.utc).isoformat()
    active = [x for x in q.load() if x.get("kind") == "zodiac_carousel" and x.get("status") in q.ACTIVE]
    observations = []
    for row in active:
        target = str(row.get("target", ""))
        marker = cards_root / target / "threads_pub_carousel.json"
        post_id, state = "", "WAITING_RECEIPT"
        if marker.exists():
            try:
                post_id = str(json.loads(marker.read_text(encoding="utf-8")).get("post_id", "")).strip()
                state = "RECEIPT_MATCH" if post_id else "INVALID_RECEIPT"
            except Exception:
                state = "INVALID_RECEIPT"
        observations.append({"key": row.get("key"), "target": target, "queue_status": row.get("status"),
            "scheduled_at": row.get("scheduled_at"), "shadow_state": state,
            "threads_id": post_id or None, "receipt": str(marker)})
    counts = {}
    for item in observations:
        counts[item["shadow_state"]] = counts.get(item["shadow_state"], 0) + 1
    return {"ok": not any(x["shadow_state"] == "INVALID_RECEIPT" for x in observations),
        "mode": "SHADOW_READ_ONLY", "checked_at": now, "external_calls": 0, "queue_mutations": 0,
        "active_zodiac_jobs": len(active), "by_shadow_state": counts, "observations": observations}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cards-root")
    args = ap.parse_args()
    print(json.dumps(observe(Path(args.cards_root) if args.cards_root else None), ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
