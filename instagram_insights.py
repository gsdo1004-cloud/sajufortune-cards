# -*- coding: utf-8 -*-
"""Instagram 최근 콘텐츠 성과를 계정별로 수집하고 시간 경과 샘플을 보관한다."""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

import requests

import instagram_dual_experiment as ide

BASE = Path(__file__).resolve().parent
API_VERSION = os.environ.get("INSTAGRAM_API_VERSION", "v21.0").strip() or "v21.0"
IG = f"https://graph.instagram.com/{API_VERSION}"


def account_key() -> str:
    return os.environ.get("INSTAGRAM_ACCOUNT_KEY", "").strip() or ide.PRIMARY_ACCOUNT


def output_path() -> Path:
    key = account_key()
    if key == ide.PRIMARY_ACCOUNT:
        return BASE / "analytics" / "instagram_insights.json"
    return BASE / "analytics" / f"instagram_insights_{ide.marker_key(key)}.json"


def history_path() -> Path:
    key = account_key()
    return BASE / "analytics" / f"instagram_history_{ide.marker_key(key)}.json"


def env():
    uid = os.environ.get("INSTAGRAM_USER_ID", "").strip()
    tok = os.environ.get("INSTAGRAM_ACCESS_TOKEN", "").strip()
    if not uid or not tok:
        raise RuntimeError("Instagram credentials missing")
    return uid, tok


def collect(limit=30):
    uid, tok = env()
    fields = "id,caption,media_type,media_product_type,timestamp,permalink,like_count,comments_count"
    r = requests.get(
        f"{IG}/{uid}/media",
        params={"fields": fields, "limit": limit, "access_token": tok},
        timeout=30,
    )
    data = r.json()
    if r.status_code >= 400:
        raise RuntimeError(str(data.get("error", {}).get("message") or r.status_code))
    out = []
    metric_names = ("views", "reach", "saved", "shares", "total_interactions")
    for item in data.get("data", []):
        row = {
            k: item.get(k)
            for k in (
                "id",
                "media_type",
                "media_product_type",
                "timestamp",
                "permalink",
                "like_count",
                "comments_count",
            )
        }
        cap = (item.get("caption") or "").replace("\n", " ")
        row["caption_head"] = cap[:120]
        metrics = {}
        try:
            q = requests.get(
                f"{IG}/{item['id']}/insights",
                params={"metric": ",".join(metric_names), "access_token": tok},
                timeout=30,
            )
            j = q.json()
            if q.status_code < 400:
                for m in j.get("data", []):
                    values = m.get("values") or []
                    value = values[-1].get("value") if values else None
                    if value is None:
                        value = (m.get("total_value") or {}).get("value")
                    if m.get("name") and value is not None:
                        metrics[m.get("name")] = value
        except Exception:
            pass
        row["metrics"] = metrics
        out.append(row)
    return {
        "collected_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "account_key": account_key(),
        "expected_username": os.environ.get("INSTAGRAM_EXPECTED_USERNAME", "").strip(),
        "count": len(out),
        "media": out,
    }


def merge_history(existing: dict, payload: dict, key: str, max_samples: int = 16) -> dict:
    history = existing if isinstance(existing, dict) else {}
    if history.get("account_key") not in (None, "", key):
        history = {}
    media = history.get("media") if isinstance(history.get("media"), dict) else {}
    collected_at = payload.get("collected_at")
    for item in payload.get("media", []):
        media_id = str(item.get("id") or "").strip()
        if not media_id:
            continue
        entry = media.get(media_id) if isinstance(media.get(media_id), dict) else {}
        samples = entry.get("samples") if isinstance(entry.get("samples"), list) else []
        samples.append(
            {
                "collected_at": collected_at,
                "metrics": item.get("metrics") or {},
                "like_count": item.get("like_count"),
                "comments_count": item.get("comments_count"),
            }
        )
        entry.update(
            {
                "timestamp": item.get("timestamp") or entry.get("timestamp"),
                "permalink": item.get("permalink") or entry.get("permalink"),
                "media_product_type": item.get("media_product_type") or entry.get("media_product_type"),
                "samples": samples[-max_samples:],
            }
        )
        media[media_id] = entry
    return {
        "account_key": key,
        "updated_at": collected_at,
        "media": media,
    }


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except Exception:
        return {}


def main():
    payload = collect()
    out = output_path()
    hist = history_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    history = merge_history(_read_json(hist), payload, account_key())
    hist.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"[OK] Instagram insights: account={account_key()} "
        f"{payload['count']} media -> {out}; history -> {hist}"
    )


if __name__ == "__main__":
    main()
