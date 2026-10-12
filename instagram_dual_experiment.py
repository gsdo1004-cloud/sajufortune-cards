# -*- coding: utf-8 -*-
"""Instagram 두 계정 띠별운세 A/B 교차 실험의 순수 계획/판정 로직.

게시 자체는 zodiac_instagram.py가 담당한다. 이 모듈은 날짜별로 계정·시간대·
캡션 변종을 교차 배정하고, 충분한 표본이 쌓인 뒤 중앙값 기반으로 계정 승자를
판정한다. 한 번의 바이럴 영상이 전체 결론을 왜곡하지 않도록 평균을 쓰지 않는다.
"""
from __future__ import annotations

import datetime as dt
import re
import statistics
from typing import Iterable

PRIMARY_ACCOUNT = "gsdo10042026"
LEGACY_ACCOUNT = "sajufortune.kr"
ACCOUNTS = (PRIMARY_ACCOUNT, LEGACY_ACCOUNT)
SLOTS = ("early", "late")
VARIANTS = ("A", "B")

VARIANT_INTROS = {
    "A": "오늘 내 띠의 흐름, 끝까지 확인해 보세요 🔮",
    "B": "재물·인연 흐름이 달라지는 띠, 내 띠도 있을까요? 🍀",
}


def marker_key(account_key: str) -> str:
    """Return a stable filesystem-safe account key."""
    return re.sub(r"[^0-9A-Za-z_-]+", "_", (account_key or "").strip()).strip("_")


def plan_for_date(date_iso: str) -> dict:
    """Cross account, slot and caption variant on alternating dates."""
    day = dt.date.fromisoformat(date_iso)
    flip = day.toordinal() % 2
    if flip == 0:
        pairs = (
            (PRIMARY_ACCOUNT, "early", "A"),
            (LEGACY_ACCOUNT, "late", "B"),
        )
    else:
        pairs = (
            (LEGACY_ACCOUNT, "early", "A"),
            (PRIMARY_ACCOUNT, "late", "B"),
        )
    return {
        "date": date_iso,
        "strategy": "crossed_account_slot_caption_v1",
        "assignments": [
            {
                "account_key": account,
                "slot": slot,
                "variant": variant,
                "caption_intro": VARIANT_INTROS[variant],
            }
            for account, slot, variant in pairs
        ],
    }


def assignment_for_slot(date_iso: str, slot: str) -> dict:
    if slot not in SLOTS:
        raise ValueError(f"unknown slot: {slot}")
    for item in plan_for_date(date_iso)["assignments"]:
        if item["slot"] == slot:
            return item
    raise RuntimeError(f"assignment missing for {date_iso}/{slot}")


def _median(rows: Iterable[dict], key: str) -> float:
    values = []
    for row in rows:
        value = row.get(key, 0)
        try:
            values.append(float(value or 0))
        except (TypeError, ValueError):
            values.append(0.0)
    return float(statistics.median(values)) if values else 0.0


def _summary(rows: list[dict]) -> dict:
    return {
        "samples": len(rows),
        "median_views": _median(rows, "views"),
        "median_reach": _median(rows, "reach"),
        "median_shares": _median(rows, "shares"),
        "median_saved": _median(rows, "saved"),
        "median_total_interactions": _median(rows, "total_interactions"),
    }


def _score(summary: dict) -> float:
    # 조회/도달이 계정 추천력을, 공유/저장/상호작용이 콘텐츠 반응을 나타낸다.
    # 원시 합계의 규모 차이를 완화하기 위해 조회/도달은 그대로, 고의도 반응은 가중한다.
    return (
        summary["median_views"]
        + 0.50 * summary["median_reach"]
        + 20.0 * summary["median_shares"]
        + 20.0 * summary["median_saved"]
        + 5.0 * summary["median_total_interactions"]
    )


def choose_winner(samples_by_account: dict[str, list[dict]], min_samples: int = 20) -> dict:
    summaries = {account: _summary(list(samples_by_account.get(account, []))) for account in ACCOUNTS}
    enough = all(summaries[a]["samples"] >= min_samples for a in ACCOUNTS)
    result = {
        "status": "ready" if enough else "collecting",
        "winner": None,
        "min_samples": min_samples,
        "accounts": summaries,
    }
    for summary in summaries.values():
        summary["score"] = round(_score(summary), 3)
    if enough:
        result["winner"] = max(ACCOUNTS, key=lambda account: summaries[account]["score"])
    return result
