# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any
import hashlib
import json
import math

SOURCE_TRUST = {
    "owned_official": 1.0,
    "internal_attribution": 0.8,
    "public_research": 0.6,
}

PATTERN_FEATURE_KEYS = (
    "topic",
    "hook_type",
    "sentence_shape",
    "opening_length_bucket",
    "question_style",
    "cta_type",
    "content_lane",
    "format",
    "visual_type",
    "visual_pattern",
    "video_opening_type",
    "proof_style",
    "offer_style",
    "posting_time_bucket",
    "engagement_shape",
)

SIGNAL_KEYS = (
    "interaction_rate_score",
    "conversation_rate_score",
    "amplification_rate_score",
    "view_velocity_score",
    "click_rate_score",
    "conversion_rate_score",
    "revenue_efficiency_score",
)


def validate_unit_interval(value: float | None, field: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a number or null")
    value = float(value)
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError(f"{field} must be within 0.0-1.0")
    return value


def deterministic_id(prefix: str, parts: list[str]) -> str:
    raw = json.dumps([str(x) for x in parts], ensure_ascii=False, separators=(",", ":"))
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16].upper()
    return f"{prefix.upper()}-{digest}"


def load_config(path: str | Path = "trie_config.json") -> dict[str, Any]:
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("TRIE config must be an object")
    return data


@dataclass(frozen=True)
class NormalizedRecord:
    source_type: str
    source_ref: str
    observed_at: str
    lane: str
    features: dict[str, Any]
    signals: dict[str, float | None]
    risk_flags: tuple[str, ...] = ()
    source_trust: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["risk_flags"] = list(self.risk_flags)
        return d


@dataclass(frozen=True)
class PatternAggregate:
    pattern_id: str
    lane: str
    features: dict[str, Any]
    sample_size: int
    source_counts: dict[str, int]
    source_trust_factor: float
    freshness_weight: float
    signals: dict[str, float | None]
    risk_flags: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["risk_flags"] = list(self.risk_flags)
        return d


@dataclass(frozen=True)
class RankedPattern:
    pattern_id: str
    lane: str
    features: dict[str, Any]
    sample_size: int
    source_counts: dict[str, int]
    source_trust_factor: float
    freshness_weight: float
    signals: dict[str, float | None]
    risk_flags: tuple[str, ...]
    growth_score: float | None
    revenue_score: float | None
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["risk_flags"] = list(self.risk_flags)
        return d


@dataclass(frozen=True)
class Recommendation:
    schema: str
    recommendation_id: str
    generated_at: str
    pattern_id: str
    lane: str
    topic: str
    hook_pattern: str
    format: str
    visual_pattern: str
    cta: str
    growth_score: float | None
    revenue_score: float | None
    confidence: float
    sample_size: int
    canary: bool = True
    source_policy: str = "derived_patterns_only"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FeedbackRecord:
    recommendation_id: str
    status: str
    observed_at: str
    post_id: str | None = None
    views: int | None = None
    likes: int | None = None
    replies: int | None = None
    reposts: int | None = None
    quotes: int | None = None
    shares: int | None = None
    clicks: int | None = None
    conversions: int | None = None
    revenue: float | None = None
    error_code: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
