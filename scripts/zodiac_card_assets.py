#!/usr/bin/env python3
"""Free, deterministic 12-zodiac card asset gate. Does not publish to social APIs."""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
EXPECTED = tuple(f"card_{i:02}.jpg" for i in range(1, 7))
SIZE = (1080, 1920)
MIN_BYTES = 60_000


def verify(day: str, root: Path = ROOT) -> list[Path]:
    dt.date.fromisoformat(day)
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


def ensure(day: str) -> list[Path]:
    try:
        return verify(day)
    except (OSError, ValueError, SyntaxError) as exc:
        print(f"[RECOVER] {day}: {exc}; generating with local PIL template (zero paid API calls)")
    folder = ROOT / "cards" / day
    if list(folder.glob("card_*.png")):
        # Existing publication formats are preserved, rather than being erased.
        raise ValueError("cannot replace legacy PNG assets automatically")
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
