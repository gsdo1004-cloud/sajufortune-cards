# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .io import read_json
from .models import load_config
from .pipeline import run_pipeline


def _serialized(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"


def _write_pair(memory_path: Path, recommendation_path: Path, memory: Any, recommendations: Any) -> None:
    memory_text = _serialized(memory)
    recommendation_text = _serialized(recommendations)
    memory_path.parent.mkdir(parents=True, exist_ok=True)
    recommendation_path.parent.mkdir(parents=True, exist_ok=True)
    memory_tmp = memory_path.with_name(memory_path.name + ".tmp")
    recommendation_tmp = recommendation_path.with_name(recommendation_path.name + ".tmp")
    try:
        memory_tmp.write_text(memory_text, encoding="utf-8")
        recommendation_tmp.write_text(recommendation_text, encoding="utf-8")
        os.replace(memory_tmp, memory_path)
        os.replace(recommendation_tmp, recommendation_path)
    finally:
        if memory_tmp.exists():
            memory_tmp.unlink()
        if recommendation_tmp.exists():
            recommendation_tmp.unlink()


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="TRIE recommendation-only canary")
    ap.add_argument("--input", required=True)
    ap.add_argument("--config", required=True)
    ap.add_argument("--memory-out", required=True)
    ap.add_argument("--recommendations-out", required=True)
    ap.add_argument("--objective", default="balanced", choices=("balanced", "growth", "revenue"))
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    raw = read_json(args.input)
    if not isinstance(raw, list):
        raise ValueError("input must be a JSON list")
    config = load_config(args.config)
    now = datetime.now(timezone.utc)
    memory, recommendations = run_pipeline(raw, now=now, config=config, objective=args.objective)
    _write_pair(Path(args.memory_out), Path(args.recommendations_out), memory, recommendations)
    print(json.dumps({
        "ok": True,
        "mode": "ADVISORY_ONLY",
        "memory_records": len(memory),
        "recommendations": len(recommendations),
        "external_calls": 0,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
