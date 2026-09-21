"""Threads queue watchdog. Safe default: reconcile + dry-run only."""
import argparse
import json
from pathlib import Path

import threads_publish_queue as q
import threads_publisher_adapter as adapter


def run(live: bool = False, cards_root: Path | None = None) -> dict:
    recovered = q.recover_expired()
    reconciled = q.reconcile_zodiac_receipts(cards_root)
    worker = q.run_worker_once(adapter.publish_job, live=live)
    return {
        "ok": bool(worker.get("ok", False)),
        "live_requested": live,
        "recovered": recovered.get("recovered", []),
        "reconciled": reconciled.get("published", []),
        "invalid_receipts": reconciled.get("invalid_receipts", []),
        "worker": worker,
        "queue": q.status(),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true",
                    help="Request live processing; still requires THREADS_QUEUE_LIVE=1")
    args = ap.parse_args()
    print(json.dumps(run(live=args.live), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
