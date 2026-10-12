# -*- coding: utf-8 -*-
"""Instagram 두 계정 실험의 24h/72h 성과를 집계하고 승자 후보를 기록한다."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import instagram_dual_experiment as ide

BASE = Path(__file__).resolve().parent
OUT = BASE / "analytics" / "instagram_account_winner.json"


def _read(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except Exception:
        return {}


def _parse_time(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(dt.timezone.utc)
    except Exception:
        return None


def sample_near_age(entry: dict, target_hours: int, tolerance_hours: int = 30) -> dict | None:
    published = _parse_time(entry.get("timestamp"))
    if not published:
        return None
    candidates = []
    for sample in entry.get("samples") or []:
        collected = _parse_time(sample.get("collected_at"))
        if not collected:
            continue
        age = (collected - published).total_seconds() / 3600.0
        if age < target_hours:
            continue
        if age > target_hours + tolerance_hours:
            continue
        candidates.append((abs(age - target_hours), age, sample))
    if not candidates:
        return None
    _, age, sample = min(candidates, key=lambda x: x[0])
    metrics = dict(sample.get("metrics") or {})
    metrics["age_hours"] = round(age, 2)
    metrics["like_count"] = sample.get("like_count") or 0
    metrics["comments_count"] = sample.get("comments_count") or 0
    return metrics


def marker_ids(base: Path, account_key: str) -> set[str]:
    ids: set[str] = set()
    for path in (base / "cards").glob("*/instagram_pub_reel*.json"):
        payload = _read(path)
        key = payload.get("account_key") or ide.PRIMARY_ACCOUNT
        if key == account_key and payload.get("post_id"):
            ids.add(str(payload["post_id"]))
    return ids


def history_path(base: Path, account_key: str) -> Path:
    return base / "analytics" / f"instagram_history_{ide.marker_key(account_key)}.json"


def samples_for_window(base: Path, account_key: str, target_hours: int) -> list[dict]:
    wanted = marker_ids(base, account_key)
    history = _read(history_path(base, account_key))
    rows = []
    for media_id, entry in (history.get("media") or {}).items():
        if media_id not in wanted:
            continue
        sample = sample_near_age(entry, target_hours)
        if sample:
            rows.append(sample)
    return rows


def evaluate(base: Path = BASE, min_samples: int = 20) -> dict:
    windows = {}
    for hours in (24, 72):
        samples = {account: samples_for_window(base, account, hours) for account in ide.ACCOUNTS}
        windows[f"{hours}h"] = ide.choose_winner(samples, min_samples=min_samples)
    final = windows["72h"] if windows["72h"]["status"] == "ready" else windows["24h"]
    return {
        "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "strategy": "crossed_account_slot_caption_v1",
        "winner": final.get("winner") if final.get("status") == "ready" else None,
        "decision_window": "72h" if windows["72h"]["status"] == "ready" else "24h",
        "status": final.get("status"),
        "windows": windows,
    }


def main() -> None:
    payload = evaluate()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] Instagram account experiment: status={payload['status']} winner={payload['winner']}")


if __name__ == "__main__":
    main()
