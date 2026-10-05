# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime
from typing import Any
import math

from .models import FeedbackRecord, Recommendation

_ALLOWED_STATUS = {"published", "rejected", "metrics_incomplete", "complete"}
_COUNT_FIELDS = ("views", "likes", "replies", "reposts", "quotes", "shares", "clicks", "conversions")


def _aware_timestamp(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError("observed_at is required")
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception as exc:
        raise ValueError("observed_at must be ISO-8601") from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("observed_at must be timezone-aware")
    return text


def _count(raw: dict[str, Any], field: str) -> int | None:
    value = raw.get(field)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or int(value) != value or value < 0:
        raise ValueError(f"{field} must be a non-negative integer or null")
    return int(value)


def normalize_feedback(raw: dict[str, Any]) -> FeedbackRecord:
    if not isinstance(raw, dict):
        raise ValueError("feedback must be an object")
    recommendation_id = str(raw.get("recommendation_id") or "").strip()
    status = str(raw.get("status") or "").strip()
    if not recommendation_id:
        raise ValueError("recommendation_id is required")
    if status not in _ALLOWED_STATUS:
        raise ValueError(f"unsupported feedback status: {status or 'missing'}")
    observed_at = _aware_timestamp(raw.get("observed_at"))
    counts = {field: _count(raw, field) for field in _COUNT_FIELDS}
    revenue_raw = raw.get("revenue")
    revenue: float | None
    if revenue_raw is None:
        revenue = None
    elif (
        isinstance(revenue_raw, bool)
        or not isinstance(revenue_raw, (int, float))
        or not math.isfinite(float(revenue_raw))
        or float(revenue_raw) < 0
    ):
        raise ValueError("revenue must be a finite non-negative number or null")
    else:
        revenue = float(revenue_raw)
    return FeedbackRecord(
        recommendation_id=recommendation_id,
        status=status,
        observed_at=observed_at,
        post_id=(str(raw.get("post_id")).strip() if raw.get("post_id") is not None else None),
        revenue=revenue,
        error_code=(str(raw.get("error_code")).strip() if raw.get("error_code") is not None else None),
        **counts,
    )


def attach_feedback(
    recommendations: list[Recommendation], feedback: list[FeedbackRecord]
) -> list[dict[str, Any]]:
    by_id = {r.recommendation_id: {**r.to_dict(), "feedback": []} for r in recommendations}
    for item in feedback:
        if item.recommendation_id not in by_id:
            raise ValueError(f"unknown recommendation_id: {item.recommendation_id}")
        by_id[item.recommendation_id]["feedback"].append(item.to_dict())
    return [by_id[r.recommendation_id] for r in recommendations]
