# -*- coding: utf-8 -*-
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any

from .patterns import aggregate_patterns
from .planner import plan_recommendations
from .ranker import rank_patterns
from .scout import normalize_records


def _resolve_synthetic_now(raw_records: list[dict[str, Any]], now: datetime) -> list[dict[str, Any]]:
    resolved = deepcopy(raw_records)
    for raw in resolved:
        if raw.get("observed_at") == "$NOW":
            source_ref = str(raw.get("source_ref") or "")
            if not source_ref.startswith("synthetic:"):
                raise ValueError("$NOW is allowed only for synthetic canary records")
            raw["observed_at"] = now.isoformat()
    return resolved


def run_pipeline(
    raw_records: list[dict[str, Any]], *, now: datetime, config: dict[str, Any],
    objective: str = "balanced", limit: int = 10
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    resolved = _resolve_synthetic_now(raw_records, now)
    normalized = normalize_records(resolved)
    aggregates = aggregate_patterns(normalized, now=now, config=config)
    ranked = rank_patterns(aggregates, config)
    recommendations = plan_recommendations(
        ranked, generated_at=now, config=config, objective=objective, limit=limit
    )
    memory = [{"schema": "trie-pattern-memory-v1", **item.to_dict()} for item in aggregates]
    recs = [item.to_dict() for item in recommendations]
    return memory, recs
