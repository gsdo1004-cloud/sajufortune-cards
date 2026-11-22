"""Fail-closed species/face audit receipts for generated zodiac images.

A composition prompt cannot prove content accuracy. A separately-produced
audit must independently identify exactly the expected species. This module
only verifies the *evidence*; it does not pretend to be an animal detector.
"""
from __future__ import annotations
import datetime as dt
import json
from pathlib import Path
from scripts.zodiac_character_prompts import STEMS, SUBJECTS
from scripts.zodiac_style_rotation import style_for_day

class SemanticHold(ValueError):pass

def audit_path(day: str, root: Path) -> Path:
    dt.date.fromisoformat(day)
    return root / "assets" / "zodiac_semantic_qa" / f"{day}.json"

def verify_semantic(day: str, root: Path, manifest: dict) -> dict:
    if not manifest.get("style_id"):
        return {"status":"LEGACY_NOT_AUDITED"}
    path=audit_path(day,root)
    if not path.is_file():
        raise SemanticHold("SEMANTIC_QA_MISSING: real zodiac count/identity not verified")
    try:
        audit=json.loads(path.read_text(encoding="utf-8"))
    except (OSError,ValueError) as exc:
        raise SemanticHold("SEMANTIC_QA_INVALID_JSON") from exc
    method=audit.get("verification_method")
    if (audit.get("schema")!="zodiac-semantic-qa-v1" or
        audit.get("date")!=day or
        audit.get("style_id")!=style_for_day(day)["id"] or
        method not in ("independent_visual_review","local_vision_model") or
        not audit.get("reviewer_reference") or
        audit.get("status")!="PASS"):
        raise SemanticHold("SEMANTIC_QA_NOT_INDEPENDENT_PASS")
    entries=manifest.get("files") or []
    reviews=audit.get("images") or []
    if len(entries)!=6 or len(reviews)!=6:
        raise SemanticHold("SEMANTIC_QA_MISSING_SIX_IMAGE_REVIEWS")
    for idx,(entry,review) in enumerate(zip(entries,reviews)):
        expected=list(SUBJECTS[idx])
        if (review.get("name")!=entry["name"] or review.get("sha256")!=entry["sha256"] or
            review.get("species")!=expected or
            review.get("status")!="PASS" or
            review.get("duplicate_species_count")!=0 or
            review.get("cropped_faces") is not False or
            review.get("malformed_anatomy") is not False or
            review.get("text_artifacts") is not False):
            raise SemanticHold(f"SEMANTIC_QA_IMAGE_FAIL_{idx+1}")
    return audit
