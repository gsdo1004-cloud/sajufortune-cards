# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any
import math

from .models import (
    NormalizedRecord,
    PATTERN_FEATURE_KEYS,
    SIGNAL_KEYS,
    SOURCE_TRUST,
    validate_unit_interval,
)

FORBIDDEN_KEYS = {
    "full_text", "body", "raw_post", "image_bytes", "video_bytes",
    "downloaded_image", "downloaded_video", "birth_date", "birth_time",
    "gender", "personal_question", "access_token", "api_key", "private_key",
}


def _scan_forbidden(value: Any, path: str = "root") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key) in FORBIDDEN_KEYS:
                raise ValueError(f"forbidden field: {path}.{key}")
            _scan_forbidden(child, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for idx, child in enumerate(value):
            _scan_forbidden(child, f"{path}[{idx}]")


def normalize_record(raw: dict[str, Any]) -> NormalizedRecord:
    if not isinstance(raw, dict):
        raise ValueError("record must be an object")
    _scan_forbidden(raw)
    source_type = str(raw.get("source_type") or "").strip()
    if source_type not in SOURCE_TRUST:
        raise ValueError(f"unsupported source type: {source_type or 'missing'}")
    source_ref = str(raw.get("source_ref") or "").strip()
    observed_at = str(raw.get("observed_at") or "").strip()
    lane = str(raw.get("lane") or "").strip()
    if not source_ref or not observed_at or not lane:
        raise ValueError("source_ref, observed_at, lane are required")

    raw_features = raw.get("features") or {}
    if not isinstance(raw_features, dict):
        raise ValueError("features must be an object")
    features: dict[str, Any] = {}
    for key in PATTERN_FEATURE_KEYS:
        if key not in raw_features:
            continue
        value = raw_features[key]
        if value is None:
            features[key] = None
            continue
        if isinstance(value, (dict, list, tuple, set)):
            raise ValueError(f"pattern feature {key} must be scalar")
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(f"pattern feature {key} must be finite")
        if not isinstance(value, (str, int, float, bool)):
            raise ValueError(f"pattern feature {key} has unsupported type")
        features[key] = value

    raw_signals = raw.get("signals") or {}
    if not isinstance(raw_signals, dict):
        raise ValueError("signals must be an object")
    signals: dict[str, float | None] = {}
    for key in SIGNAL_KEYS:
        if key in raw_signals:
            signals[key] = validate_unit_interval(raw_signals[key], key)

    raw_flags = raw.get("risk_flags") or []
    if not isinstance(raw_flags, (list, tuple)):
        raise ValueError("risk_flags must be a list")
    flags = tuple(sorted({str(x).strip() for x in raw_flags if str(x).strip()}))

    return NormalizedRecord(
        source_type=source_type,
        source_ref=source_ref,
        observed_at=observed_at,
        lane=lane,
        features=features,
        signals=signals,
        risk_flags=flags,
        source_trust=SOURCE_TRUST[source_type],
    )


def normalize_records(raw_records: list[dict[str, Any]]) -> list[NormalizedRecord]:
    if not isinstance(raw_records, list):
        raise ValueError("records must be a list")
    return [normalize_record(raw) for raw in raw_records]
