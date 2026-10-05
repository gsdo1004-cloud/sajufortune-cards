# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime
from typing import Any

from .models import RankedPattern, Recommendation, deterministic_id


def is_eligible(pattern: RankedPattern, config: dict[str, Any]) -> tuple[bool, str]:
    if pattern.sample_size < int(config["min_sample_size"]):
        return False, "sample_size"
    if pattern.confidence < float(config["min_confidence"]):
        return False, "confidence"
    if pattern.growth_score is None and pattern.revenue_score is None:
        return False, "no_evidence"
    blocking = set(config.get("blocking_risk_flags") or [])
    if blocking.intersection(pattern.risk_flags):
        return False, "blocking_risk"
    return True, "eligible"


def _objective_score(pattern: RankedPattern, objective: str) -> float:
    if objective == "growth":
        return -1.0 if pattern.growth_score is None else float(pattern.growth_score)
    if objective == "revenue":
        return -1.0 if pattern.revenue_score is None else float(pattern.revenue_score)
    values = [x for x in (pattern.growth_score, pattern.revenue_score) if x is not None]
    return -1.0 if not values else sum(values) / len(values)


def plan_recommendations(
    patterns: list[RankedPattern], *, generated_at: datetime,
    config: dict[str, Any], objective: str = "balanced", limit: int = 10
) -> list[Recommendation]:
    if objective not in {"growth", "revenue", "balanced"}:
        raise ValueError(f"unsupported objective: {objective}")
    if generated_at.tzinfo is None or generated_at.utcoffset() is None:
        raise ValueError("generated_at must be timezone-aware")
    eligible = [x for x in patterns if is_eligible(x, config)[0]]
    eligible.sort(key=lambda x: (-_objective_score(x, objective), -x.confidence, x.pattern_id))
    stamp = generated_at.isoformat()
    out: list[Recommendation] = []
    for pattern in eligible[:max(0, int(limit))]:
        f = pattern.features
        rid = deterministic_id("TRIE", [pattern.pattern_id, stamp, objective])
        out.append(Recommendation(
            schema="trie-recommendation-v1",
            recommendation_id=rid,
            generated_at=stamp,
            pattern_id=pattern.pattern_id,
            lane=str(f.get("content_lane") or pattern.lane),
            topic=str(f.get("topic") or ""),
            hook_pattern=str(f.get("hook_type") or ""),
            format=str(f.get("format") or ""),
            visual_pattern=str(f.get("visual_pattern") or f.get("visual_type") or ""),
            cta=str(f.get("cta_type") or ""),
            growth_score=pattern.growth_score,
            revenue_score=pattern.revenue_score,
            confidence=pattern.confidence,
            sample_size=pattern.sample_size,
            canary=True,
            source_policy="derived_patterns_only",
        ))
    return out
