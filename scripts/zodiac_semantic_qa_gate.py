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
    if manifest.get("verified_atlas_manifest_sha256"):
        # Deterministic one-to-one composition from twelve individually audited
        # original FLUX portraits eliminates multi-animal diffusion duplicates.
        from scripts.zodiac_mascot_atlas import verify_atlas, atlas_dir
        from scripts.visual_quality_gate import sha256
        verified=verify_atlas(day,root)
        if sha256(atlas_dir(day,root)/"manifest.json")!=manifest["verified_atlas_manifest_sha256"]:
            raise SemanticHold("ATLAS_MANIFEST_SHA_CHANGED")
        if any(entry.get("verified_atlas_manifest_sha256")!=manifest["verified_atlas_manifest_sha256"]
               for entry in manifest.get("files",[])):
            raise SemanticHold("CARD_ATLAS_PROVENANCE_MISMATCH")
        return {"status":"PASS","verification_method":verified["verification_method"],
                "source":"individually_verified_12_zodiac_atlas"}
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
        faces=review.get("faces") or []
        if (len(faces)!=len(expected) or
            [x.get("sign") for x in faces]!=expected or
            any(not isinstance(x.get("bbox"),list) or len(x["bbox"])!=4 or
                not all(isinstance(v,int) for v in x["bbox"]) or
                not (0<=x["bbox"][0]<x["bbox"][2]<=1080 and
                     0<=x["bbox"][1]<x["bbox"][3]<=1920)
                for x in faces)):
            raise SemanticHold(f"SEMANTIC_FACE_BOXES_MISSING_OR_INVALID_{idx+1}")
        if (review.get("name")!=entry["name"] or review.get("sha256")!=entry["sha256"] or
            review.get("species")!=expected or
            review.get("status")!="PASS" or
            review.get("duplicate_species_count")!=0 or
            review.get("cropped_faces") is not False or
            review.get("malformed_anatomy") is not False or
            review.get("text_artifacts") is not False or
            ("dragon" in expected and review.get("eastern_dragon_verified") is not True) or
            (set(("rat","snake")) & set(expected) and review.get("friendly_non_scary") is not True)):
            raise SemanticHold(f"SEMANTIC_QA_IMAGE_FAIL_{idx+1}")
    return audit

def face_boxes_for(day: str, stem: str, root: Path) -> list[tuple[int,int,int,int]]:
    """Use real audited faces or deterministic portrait tiles, not prompt guess."""
    from scripts.zodiac_character_prompts import STEMS
    if stem not in STEMS:raise ValueError("unknown card stem")
    folder=root/"assets"/"flux_daily"/day
    manifest_path=folder/"manifest.json"
    if not manifest_path.is_file():return []
    manifest=json.loads(manifest_path.read_text(encoding="utf-8"))
    if not manifest.get("style_id"):return []
    index=STEMS.index(stem)
    if manifest.get("verified_atlas_manifest_sha256"):
        verify_semantic(day,root,manifest)
        entries=manifest["files"]
        from scripts.zodiac_mascot_atlas import layout_regions
        required=layout_regions(stem)
        if entries[index].get("face_boxes")!=required:
            raise SemanticHold("ATLAS_FACE_REGION_PROVENANCE_MISMATCH")
        return [tuple(x["bbox"]) for x in required]
    receipt=audit_path(day,root)
    if not receipt.is_file():
        # Generative staging may still render; publishing must verify_semantic,
        # which refuses missing independent reviews.
        return []
    audit=verify_semantic(day,root,manifest)
    return [tuple(x["bbox"]) for x in audit["images"][index]["faces"]]
