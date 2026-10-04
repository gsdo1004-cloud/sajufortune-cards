# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse, json, os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

GRAPH = "https://graph.threads.net/v1.0"
EXPECTED_USERNAME = "gsdo10042026"
EXPECTED_PILOT_ID = "RCEPILOT-62E11AA62C032706"
EXPECTED_CONTENT_ID = "RCE-FORTUNE-TH-20261004-A33D9B36"
KST = timezone(timedelta(hours=9))
OUT = Path("rce_pilot_insights_output.json")
METRICS = ("views", "likes", "replies", "reposts", "quotes", "shares")


def _iso() -> str:
    return datetime.now(KST).isoformat(timespec="seconds")


def _read(path: Path) -> dict[str, Any]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise ValueError("receipt must be object")
    return obj


def _metric_value(item: dict[str, Any]) -> int:
    values = item.get("values")
    if isinstance(values, list) and values:
        raw = (values[-1] or {}).get("value") if isinstance(values[-1], dict) else 0
    elif isinstance(item.get("total_value"), dict):
        raw = (item.get("total_value") or {}).get("value", 0)
    else:
        raw = item.get("value", 0)
    try:
        return max(0, int(float(raw or 0)))
    except Exception:
        return 0


def collect(pilot_id: str) -> dict[str, Any]:
    if pilot_id != EXPECTED_PILOT_ID:
        raise ValueError("unsupported pilot id")
    receipt_path = Path("rce_pilot_receipts") / f"{pilot_id}.json"
    receipt = _read(receipt_path)
    if receipt.get("schema") != "rce-pilot-publication-receipt-v1":
        raise ValueError("publication receipt schema mismatch")
    if receipt.get("pilot_id") != pilot_id or receipt.get("content_id") != EXPECTED_CONTENT_ID:
        raise ValueError("publication receipt identity mismatch")
    if receipt.get("platform") != "threads" or receipt.get("username") != EXPECTED_USERNAME:
        raise ValueError("publication receipt account mismatch")
    post_id = str(receipt.get("post_id") or "").strip()
    if not post_id:
        raise ValueError("publication receipt missing post id")

    token = str(os.environ.get("THREADS_ACCESS_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("THREADS_ACCESS_TOKEN missing")
    me = requests.get(
        f"{GRAPH}/me",
        params={"fields": "id,username", "access_token": token},
        timeout=15,
    ).json()
    username = str(me.get("username") or "").strip().lstrip("@").lower()
    if username != EXPECTED_USERNAME:
        raise RuntimeError(f"Threads account mismatch: expected @{EXPECTED_USERNAME}, got @{username or 'unknown'}")

    data = requests.get(
        f"{GRAPH}/{post_id}/insights",
        params={"metric": ",".join(METRICS), "access_token": token},
        timeout=30,
    ).json()
    if isinstance(data, dict) and data.get("error"):
        err = data.get("error") or {}
        raise RuntimeError(f"Threads insights failed: {err.get('message') or err}")
    rows = data.get("data") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        raise RuntimeError("Threads insights response missing data")
    metrics = {name: 0 for name in METRICS}
    raw_names = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if name in metrics:
            metrics[name] = _metric_value(item)
            raw_names.append(name)

    result = {
        "schema": "rce-pilot-threads-insights-v1",
        "pilot_id": pilot_id,
        "content_id": EXPECTED_CONTENT_ID,
        "platform": "threads",
        "platform_content_id": post_id,
        "username": EXPECTED_USERNAME,
        "collected_at": _iso(),
        "metrics": metrics,
        "interaction_total": sum(metrics[x] for x in ("likes", "replies", "reposts", "quotes", "shares")),
        "available_metric_names": sorted(set(raw_names)),
        "source": "official_threads_post_insights",
        "github_run_id": os.environ.get("GITHUB_RUN_ID"),
        "contains_pii": False,
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pilot-id", required=True)
    args = ap.parse_args()
    print(json.dumps(collect(args.pilot_id), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
