# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any

from .models import PatternAggregate, RankedPattern


def weighted_available_mean(
    signals: dict[str, float | None], weights: dict[str, float]
) -> float | None:
    pairs = [(signals.get(k), float(w)) for k, w in weights.items() if signals.get(k) is not None]
    if not pairs:
        return None
    denominator = sum(weight for _, weight in pairs)
    if denominator <= 0:
        raise ValueError("available weights must sum to a positive value")
    return sum(float(value) * weight for value, weight in pairs) / denominator


def rank_pattern(pattern: PatternAggregate, config: dict[str, Any]) -> RankedPattern:
    growth = weighted_available_mean(pattern.signals, config["growth_weights"])
    revenue = weighted_available_mean(pattern.signals, config["revenue_weights"])
    sample_factor = min(1.0, pattern.sample_size / 10.0)
    confidence = sample_factor * pattern.freshness_weight * pattern.source_trust_factor
    confidence = min(1.0, max(0.0, confidence))
    return RankedPattern(
        pattern_id=pattern.pattern_id,
        lane=pattern.lane,
        features=dict(pattern.features),
        sample_size=pattern.sample_size,
        source_counts=dict(pattern.source_counts),
        source_trust_factor=pattern.source_trust_factor,
        freshness_weight=pattern.freshness_weight,
        signals=dict(pattern.signals),
        risk_flags=tuple(pattern.risk_flags),
        growth_score=growth,
        revenue_score=revenue,
        confidence=confidence,
    )


def rank_patterns(patterns: list[PatternAggregate], config: dict[str, Any]) -> list[RankedPattern]:
    return sorted((rank_pattern(x, config) for x in patterns), key=lambda x: x.pattern_id)
