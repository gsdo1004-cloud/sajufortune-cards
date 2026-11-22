"""Fail-closed audit evidence binding for independently checked zodiac portraits.

This verifier establishes file existence, SHA integrity, and per-image matching;
it cannot independently authenticate the human reviewer, so the external audit
and actual visual inspection remain separate release prerequisites.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from scripts.visual_quality_gate import sha256


class ReviewEvidenceHold(ValueError):
    pass


def verify_review_evidence(manifest: dict, folder: Path) -> dict:
    reference = manifest.get("reviewer_reference")
    match = re.fullmatch(
        r"review_evidence[.]json#sha256=([0-9a-f]{64})",
        reference if isinstance(reference, str) else "",
    )
    if not match:
        raise ReviewEvidenceHold("ATLAS_REVIEW_REFERENCE_INVALID")
    evidence_path = folder / "review_evidence.json"
    if not evidence_path.is_file() or evidence_path.is_symlink():
        raise ReviewEvidenceHold("ATLAS_REVIEW_EVIDENCE_MISSING")
    if sha256(evidence_path) != match.group(1):
        raise ReviewEvidenceHold("ATLAS_REVIEW_EVIDENCE_SHA_MISMATCH")
    try:
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ReviewEvidenceHold("ATLAS_REVIEW_EVIDENCE_INVALID_JSON") from exc

    reviewer = evidence.get("reviewer")
    reviewed_at = evidence.get("reviewed_at")
    try:
        moment = dt.datetime.fromisoformat(reviewed_at)
    except (ValueError, TypeError) as exc:
        raise ReviewEvidenceHold("ATLAS_REVIEW_TIMESTAMP_INVALID") from exc
    if (
        evidence.get("schema") != "zodiac-independent-review-v1"
        or evidence.get("status") != "PASS"
        or evidence.get("style_id") != manifest.get("style_id")
        or evidence.get("verification_method") != manifest.get("verification_method")
        or evidence.get("paid_api_calls") != 0
        or not isinstance(reviewer, str)
        or not (3 <= len(reviewer.strip()) <= 128)
        or reviewer.casefold() == "flux2_klein_local"
        or moment.tzinfo is None
        or moment.year < 2026
    ):
        raise ReviewEvidenceHold("ATLAS_REVIEW_METADATA_INVALID")
    files = evidence.get("files")
    manifest_files = manifest.get("files") or []
    if not isinstance(files, list) or len(files) != 12 or len(manifest_files) != 12:
        raise ReviewEvidenceHold("ATLAS_REVIEW_FILES_INCOMPLETE")
    for expected, reviewed in zip(manifest_files, files):
        if not isinstance(reviewed, dict):
            raise ReviewEvidenceHold("ATLAS_REVIEW_FILE_INVALID")
        sign = expected.get("sign")
        if (
            reviewed.get("sign") != sign
            or reviewed.get("sha256") != expected.get("sha256")
            or reviewed.get("status") != "PASS"
            or reviewed.get("detected_species") != sign
            or reviewed.get("subject_count") != 1
            or reviewed.get("cropped_face") is not False
            or reviewed.get("malformed_anatomy") is not False
            or reviewed.get("text_artifacts") is not False
            or (sign == "dragon" and reviewed.get("eastern_dragon_verified") is not True)
            or (sign in ("rat", "snake") and reviewed.get("friendly_non_scary") is not True)
            or not isinstance(reviewed.get("review_notes"), str)
            or len(reviewed["review_notes"].strip()) < 8
        ):
            raise ReviewEvidenceHold("ATLAS_REVIEW_FILE_MISMATCH_" + str(sign))
    return evidence
