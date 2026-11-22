#!/usr/bin/env python3
"""Free, deterministic 12-zodiac card asset gate. Does not publish to social APIs."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import shutil
import tempfile
import sys
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
EXPECTED = tuple(f"card_{i:02}.jpg" for i in range(1, 7))
SIZE = (1080, 1920)
MIN_BYTES = 60_000


def verify(day: str, root: Path | None = None) -> list[Path]:
    dt.date.fromisoformat(day)
    root = root or ROOT
    folder = root / "cards" / day
    # zodiac_cardnews.py prefers PNG over JPEG; never allow a partial PNG
    # set to silently eclipse the new complete JPEG set.
    pngs = sorted(folder.glob("card_*.png"))
    if pngs:
        raise ValueError(f"legacy PNG assets need manual review: {[p.name for p in pngs]}")
    paths = [folder / name for name in EXPECTED]
    if [p.name for p in sorted(folder.glob("card_*.jpg"))] != list(EXPECTED):
        raise ValueError(f"incomplete or unexpected JPEG assets for {day}")
    for p in paths:
        if not p.is_file() or p.stat().st_size < MIN_BYTES:
            raise ValueError(f"missing or undersize card: {p}")
        with Image.open(p) as im:
            im.verify()
        with Image.open(p) as im:
            if im.size != SIZE or im.format != "JPEG":
                raise ValueError(f"wrong card format or dimensions: {p.name} {im.format} {im.size}")
    print(f"[PASS] {day}: six JPEG cards verified (1080x1920, >=60KB)")
    return paths


def _publication_receipt_exists(folder: Path) -> bool:
    """Never change cards after any tracked social/YouTube publication."""
    patterns = ("threads_pub_*.json", "instagram_pub_*.json",
                "youtube_pub*.json", "uploaded.json")
    return any(any(folder.glob(pattern)) for pattern in patterns)


def _promote_unpublished_flux_cards(day: str, folder: Path, manifest_hash: str) -> list[Path]:
    """Replace only unpublished cards, with rollback if rendering fails."""
    folder.parent.mkdir(parents=True, exist_ok=True)
    folder.mkdir(parents=True, exist_ok=True)
    old_cards = list(folder.glob("card_*.jpg"))
    marker = folder / "flux_backgrounds_applied.json"
    with tempfile.TemporaryDirectory(prefix=".flux-card-rollback-", dir=folder.parent) as temp:
        backup = Path(temp)
        for image in old_cards:
            shutil.copyfile(image, backup / image.name)
        old_marker = marker.read_bytes() if marker.exists() else None
        try:
            from zodiac_cardnews_tpl import build
            build(day)
            ready = verify(day)
            marker.write_text(
                json.dumps({"schema":1, "date":day,
                            "flux_manifest_sha256":manifest_hash,
                            "status":"APPLIED"}, indent=2) + "\n", encoding="utf-8")
            return ready
        except Exception:
            # Never publish a half-updated set; restore original six cards
            # exactly as they were, and preserve the original marker.
            for image in folder.glob("card_*.jpg"):
                image.unlink()
            for image in old_cards:
                shutil.copyfile(backup / image.name, image)
            if old_marker is None:
                marker.unlink(missing_ok=True)
            else:
                marker.write_bytes(old_marker)
            raise


def ensure(day: str) -> list[Path]:
    dt.date.fromisoformat(day)
    folder = ROOT / "cards" / day
    if list(folder.glob("card_*.png")):
        raise ValueError("cannot replace legacy PNG assets automatically")
    flux_manifest = ROOT / "assets" / "flux_daily" / day / "manifest.json"
    if flux_manifest.is_file():
        from scripts.flux_first_card_assets import verify as verify_flux
        verify_flux(day, ROOT)  # complete six files + SHA256 + format + nonblank
        manifest_sha = hashlib.sha256(flux_manifest.read_bytes()).hexdigest()
        marker = folder / "flux_backgrounds_applied.json"
        try:
            applied = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            applied = {}
        if applied.get("flux_manifest_sha256") == manifest_sha:
            return verify(day)
        if _publication_receipt_exists(folder):
            # Do not change content already shared on any platform.
            print(f"[HOLD] {day}: published cards protected; no FLUX rewrite")
            return verify(day)
        print(f"[FLUX] {day}: promote fully verified backgrounds before publication")
        return _promote_unpublished_flux_cards(day, folder, manifest_sha)

    try:
        return verify(day)
    except (OSError, ValueError, SyntaxError) as exc:
        print(f"[RECOVER] {day}: {exc}; generating with local PIL template (zero paid API calls)")
    from zodiac_cardnews_tpl import build
    build(day)
    return verify(day)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=("ensure", "verify"))
    ap.add_argument("date")
    args = ap.parse_args()
    if args.mode == "ensure":
        ensure(args.date)
    else:
        verify(args.date)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
