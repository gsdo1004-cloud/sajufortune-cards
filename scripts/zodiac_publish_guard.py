"""Fail-closed, read-only proof gate before ANY seven-style FLUX social publication.

Legacy unstyled dates continue through their existing policy. New 7-style
FLUX assets require an externally approved HMAC-authenticated release record
bound to source atlas, six cards, and EACH individual published video.
This module cannot make an independent reviewer legitimate or fabricate QA.
No approval key is provisioned by this PR. Missing key/approval => HOLD.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import hmac
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# python scripts/zodiac_publish_guard.py must import the package from repo root.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SIGNATURE_FIELD = "hmac_sha256"
APPROVAL_ENV = "ZODIAC_RELEASE_REVIEW_HMAC_KEY"


class ReleaseHold(ValueError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path, reason: str) -> dict:
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ReleaseHold(reason) from exc
    if not isinstance(result, dict):
        raise ReleaseHold(reason)
    return result


# The first seven-style promotion shipped on 2026-11-22. Existing
# historical PNG dates keep their legacy publisher, but a new JPEG/MP4
# without intact source/layout identity must never be accepted as legacy.
STYLE_PROTECTION_START = dt.date(2026, 11, 22)


def _styled_artifact_evidence(day: str, root: Path) -> bool:
    """Read-only independent evidence: tolerate deletion of BOTH manifests.

    Raw files, rendered layout, style schedule, and review/receipt markers
    are considered even when the adjacent JSON was removed during a sync.
    """
    cards = root / "cards" / day
    source = root / "assets" / "flux_daily" / day
    if source.exists():
        if any(entry.name != "manifest.json" for entry in source.iterdir()):
            return True
        manifest_path = source / "manifest.json"
        if manifest_path.exists():
            item = _read_json(manifest_path, "RELEASE_SOURCE_MANIFEST_INVALID")
            if item.get("schema") == "social-flux-backgrounds-v1":
                return True
    if (root / "assets" / "zodiac_release_approvals" / (day + ".json")).exists():
        return True
    if any((cards / name).exists() for name in (
        "flux_backgrounds_applied.json", "layout_manifest.json",
        "visual_style.json", "review_evidence.json",
    )):
        # A layout / visual_style file alone is not proof of styled content;
        # inspect it below and classify malformed metadata conservatively.
        for name in ("layout_manifest.json", "visual_style.json"):
            path = cards / name
            if path.exists():
                meta = _read_json(path, "RELEASE_LAYOUT_BROKEN")
                if (meta.get("style_id") or
                    meta.get("protection_source") == "composition_contract_not_animal_detection" or
                    str(meta.get("family_id", "")).startswith("STYLE_")):
                    return True
        if (cards / "flux_backgrounds_applied.json").exists() or (cards / "review_evidence.json").exists():
            return True
    if dt.date.fromisoformat(day) >= STYLE_PROTECTION_START:
        if list(cards.glob("card_*.jpg")) or list(cards.glob("card_*.jpeg")):
            return True
        if list((root / "reels").glob(day + "_tts*.mp4")):
            # A dated reel is not independently attributed to a verified
            # legacy source. Require a source manifest or historical legacy
            # proof for new dates; never trust only a video file name.
            return True
    return False


def styled_manifest(day: str, root: Path = ROOT) -> dict | None:
    dt.date.fromisoformat(day)
    if dt.date.fromisoformat(day).isoformat() != day:
        raise ReleaseHold("RELEASE_INVALID_DATE")
    source = root / "assets" / "flux_daily" / day / "manifest.json"
    layout = root / "cards" / day / "layout_manifest.json"
    if not source.exists():
        if _styled_artifact_evidence(day, root):
            raise ReleaseHold("RELEASE_STYLED_ASSETS_WITHOUT_MANIFEST")
        return None
    manifest = _read_json(source, "RELEASE_SOURCE_MANIFEST_INVALID")
    if not manifest.get("style_id"):
        if _styled_artifact_evidence(day, root):
            raise ReleaseHold("RELEASE_STYLE_ID_DOWNGRADE_DETECTED")
        return None
    if layout.exists():
        card_layout = _read_json(layout, "RELEASE_LAYOUT_BROKEN")
        if card_layout.get("style_id") not in (None, manifest["style_id"]):
            raise ReleaseHold("RELEASE_LAYOUT_STYLE_MISMATCH")
    return manifest


def _signature_valid(record: dict, key: str) -> bool:
    if not isinstance(key, str) or len(key) < 32:
        return False
    supplied = record.get(SIGNATURE_FIELD)
    if not isinstance(supplied, str) or len(supplied) != 64:
        return False
    payload = {k: v for k, v in record.items() if k != SIGNATURE_FIELD}
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":")).encode("utf-8")
    expected = hmac.new(key.encode("utf-8"), canonical, hashlib.sha256).hexdigest()
    return hmac.compare_digest(supplied, expected)


def _video_path(day: str, root: Path, video: str | Path) -> Path:
    selected = Path(video)
    file = selected if selected.is_absolute() else root / selected
    expected_dir = (root / "reels").resolve()
    if file.resolve().parent != expected_dir:
        raise ReleaseHold("RELEASE_VIDEO_PATH_NOT_REELS")
    if not file.name.startswith(day + "_tts") or file.suffix != ".mp4":
        raise ReleaseHold("RELEASE_VIDEO_NAME_UNEXPECTED")
    return file


def check(day: str, *, root: Path = ROOT, mode: str = "video",
          video: str | Path | None = None, approval_key: str | None = None) -> dict:
    """Read-only preflight: no social uploads, receipt mutation or provider calls."""
    root = Path(root)
    if mode not in ("video", "cards"):
        raise ReleaseHold("RELEASE_UNKNOWN_MODE")
    manifest = styled_manifest(day, root)
    if manifest is None:
        return {"status": "LEGACY_UNCHANGED", "date": day, "mode": mode}

    # Never interpret mere presence of a source as an independent approval.
    from scripts.zodiac_card_assets import verify as verify_cards
    from scripts.flux_first_card_assets import verify as verify_flux
    from scripts.zodiac_mascot_atlas import atlas_dir, verify_atlas
    from scripts.visual_quality_gate import video_check
    try:
        verified_source = verify_flux(day, root)
        if verified_source.get("style_id") != manifest.get("style_id"):
            raise ValueError("FLUX_SOURCE_STYLE_MISMATCH")
        cards = verify_cards(day, root)
        atlas = verify_atlas(day, root)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        raise ReleaseHold("RELEASE_SOURCE_INDEPENDENT_QA_HOLD") from exc

    source_path = root / "assets" / "flux_daily" / day / "manifest.json"
    layout_path = root / "cards" / day / "layout_manifest.json"
    atlas_path = atlas_dir(day, root) / "manifest.json"
    approval = _read_json(root / "assets" / "zodiac_release_approvals" / (day + ".json"),
                          "RELEASE_ATTESTATION_MISSING_OR_INVALID")
    try:
        approved_at = dt.datetime.fromisoformat(approval.get("approved_at", ""))
    except (ValueError, TypeError) as exc:
        raise ReleaseHold("RELEASE_APPROVED_AT_INVALID") from exc
    reviewer_id = approval.get("reviewer_id")
    if (approval.get("schema") != "zodiac-signed-release-v1"
            or approval.get("status") != "APPROVED"
            or approval.get("date") != day
            or approval.get("style_id") != manifest.get("style_id")
            or not isinstance(approval.get("scopes"), list)
            or len(set(str(x) for x in approval["scopes"])) != len(approval["scopes"])
            or any(x not in ("video", "cards") for x in approval["scopes"])
            or mode not in approval["scopes"]
            or not isinstance(reviewer_id, str)
            or len(reviewer_id.strip()) < 4
            or reviewer_id.casefold() in ("local_model", "flux2_klein_local", "self")
            or approved_at.tzinfo is None
            or approval.get("source_manifest_sha256") != sha256(source_path)
            or approval.get("layout_manifest_sha256") != sha256(layout_path)
            or approval.get("atlas_manifest_sha256") != sha256(atlas_path)
            or approval.get("cards_sha256") != {p.name: sha256(p) for p in cards}
            or atlas.get("status") != "PASS"):
        raise ReleaseHold("RELEASE_APPROVAL_PROVENANCE_MISMATCH")
    key = approval_key if approval_key is not None else os.environ.get(APPROVAL_ENV, "")
    if not _signature_valid(approval, key):
        raise ReleaseHold("RELEASE_SIGNED_REVIEW_MISSING_OR_INVALID")

    selected = None
    checked_hash = None
    if mode == "video":
        selected = _video_path(day, root, video or f"reels/{day}_tts.mp4")
        try:
            checked = video_check(selected, require_audio=True)
        except (OSError, ValueError) as exc:
            raise ReleaseHold("RELEASE_FULL_TTS_VIDEO_QA_FAILED") from exc
        if (checked.get("status") != "PASS" or
                not 15 <= checked.get("duration_seconds", 0) <= 85.0):
            raise ReleaseHold("RELEASE_FULL_TTS_VIDEO_UNAPPROVED")
        checked_hash = checked["sha256"]
        if (not isinstance(approval.get("videos_sha256"), dict)
                or approval["videos_sha256"].get(selected.name) != checked_hash):
            raise ReleaseHold("RELEASE_VIDEO_SHA_UNAPPROVED")
        if (approval.get("avatar_and_voice_qa_status") != "PASS" or
                approval.get("twelve_signs_narration_qa_status") != "PASS"):
            raise ReleaseHold("RELEASE_HANBOK_AND_TTS_QA_UNAPPROVED")

    return {"status": "VERIFIED_SIGNED_RELEASE", "date": day, "mode": mode,
            "source_manifest_sha256": sha256(source_path),
            "video_sha256": checked_hash,
            "approved_reviewer": reviewer_id,
            "video": str(selected) if selected else None}


def immutable_raw_url(url: str) -> str:
    """Bind external media to an exact successful git push commit, not main."""
    from urllib.parse import urlparse
    import re
    uri = urlparse(url)
    prefix = "/gsdo1004-cloud/sajufortune-cards/main/"
    if uri.scheme != "https" or uri.netloc != "raw.githubusercontent.com" or not uri.path.startswith(prefix):
        raise ReleaseHold("RELEASE_REMOTE_URL_NOT_APPROVED")
    commit = os.environ.get("ZODIAC_RAW_COMMIT_SHA", "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ReleaseHold("RELEASE_IMMUTABLE_RAW_COMMIT_UNAVAILABLE")
    return f"https://raw.githubusercontent.com/gsdo1004-cloud/sajufortune-cards/{commit}/{uri.path[len(prefix):]}"


def verify_remote_sha(url: str, expected_sha: str, *, max_bytes: int = 120_000_000,
                      require_immutable: bool = False) -> None:
    """Read-only CDN identity check; strict styled URLs must pin commit SHA."""
    from urllib.parse import urlparse
    import re
    uri = urlparse(url)
    prefix = "/gsdo1004-cloud/sajufortune-cards/"
    ref = uri.path[len(prefix):].split("/", 1)[0] if uri.path.startswith(prefix) else ""
    if (uri.scheme != "https" or uri.netloc != "raw.githubusercontent.com"
            or uri.query or uri.fragment or ref not in ("main",) and not re.fullmatch(r"[a-f0-9]{40}", ref)
            or (require_immutable and ref == "main")):
        raise ReleaseHold("RELEASE_REMOTE_URL_NOT_APPROVED")
    import requests
    digest = hashlib.sha256()
    total = 0
    try:
        with requests.get(url, stream=True, timeout=45, allow_redirects=False) as response:
            if response.status_code != 200:
                raise ReleaseHold("RELEASE_REMOTE_NOT_READY")
            for chunk in response.iter_content(65536):
                total += len(chunk)
                if total > max_bytes:
                    raise ReleaseHold("RELEASE_REMOTE_TOO_LARGE")
                digest.update(chunk)
    except requests.RequestException as exc:
        raise ReleaseHold("RELEASE_REMOTE_UNAVAILABLE") from exc
    if total <= 0 or not hmac.compare_digest(digest.hexdigest(), expected_sha):
        raise ReleaseHold("RELEASE_REMOTE_SHA_MISMATCH")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("video", "cards"))
    parser.add_argument("date")
    parser.add_argument("--video", default=None)
    args = parser.parse_args()
    result = check(args.date, mode=args.mode, video=args.video)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
