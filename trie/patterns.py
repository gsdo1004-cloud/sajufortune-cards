# -*- coding: utf-8 -*-
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Any

from .models import (
    NormalizedRecord,
    PatternAggregate,
    PATTERN_FEATURE_KEYS,
    SIGNAL_KEYS,
    deterministic_id,
)


def _parse_aware(value: str) -> datetime:
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception as exc:
        raise ValueError(f"invalid observed_at: {value}") from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("observed_at must be timezone-aware")
    return dt


def freshness_weight(observed_at: str, now: datetime, config: dict[str, Any]) -> float:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    observed = _parse_aware(observed_at)
    delta = now - observed
    if delta < -timedelta(minutes=5):
        raise ValueError("observed_at is materially in the future")
    age_days = max(0.0, delta.total_seconds() / 86400.0)
    for bucket in config["freshness_buckets"]:
        max_days = bucket.get("max_days")
        if max_days is None or age_days <= float(max_days):
            return float(bucket["weight"])
    raise ValueError("freshness configuration has no terminal bucket")


def pattern_key(record: NormalizedRecord) -> tuple[str, ...]:
    values = [record.lane]
    for key in PATTERN_FEATURE_KEYS:
        value = record.features.get(key)
        values.append("" if value is None else str(value))
    return tuple(values)


def aggregate_patterns(
    records: list[NormalizedRecord], *, now: datetime, config: dict[str, Any]
) -> list[PatternAggregate]:
    grouped: dict[tuple[str, ...], list[NormalizedRecord]] = defaultdict(list)
    for record in records:
        grouped[pattern_key(record)].append(record)

    out: list[PatternAggregate] = []
    for key, members in grouped.items():
        lane = key[0]
        features = {
            feature_key: value
            for feature_key, value in zip(PATTERN_FEATURE_KEYS, key[1:])
            if value != ""
        }
        sample_size = len(members)
        source_counts = dict(sorted(Counter(x.source_type for x in members).items()))
        trust = sum(x.source_trust for x in members) / sample_size
        freshness = sum(freshness_weight(x.observed_at, now, config) for x in members) / sample_size
        signals: dict[str, float | None] = {}
        for signal in SIGNAL_KEYS:
            values = [x.signals.get(signal) for x in members if x.signals.get(signal) is not None]
            signals[signal] = (sum(values) / len(values)) if values else None
        risk_flags = tuple(sorted({flag for x in members for flag in x.risk_flags}))
        pattern_id = deterministic_id("TRIEPAT", list(key))
        out.append(
            PatternAggregate(
                pattern_id=pattern_id,
                lane=lane,
                features=features,
                sample_size=sample_size,
                source_counts=source_counts,
                source_trust_factor=trust,
                freshness_weight=freshness,
                signals=signals,
                risk_flags=risk_flags,
            )
        )
    return sorted(out, key=lambda x: x.pattern_id)
