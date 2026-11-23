"""Scope-stable asset staging for Github raw hosting; never publish itself.

Keep unrelated scheduled dates, unreviewed Instagram A/B media, temporary TTS,
and prior receipt files out of git add. New FLUX files must pass the *same*
independent signed approval used by external media publishers.
"""
from __future__ import annotations
import argparse
import re
import subprocess
import sys
from pathlib import Path
ROOT_PATH = Path(__file__).resolve().parents[1]
if str(ROOT_PATH) not in sys.path:
    sys.path.insert(0, str(ROOT_PATH))
from scripts.zodiac_publish_guard import check, styled_manifest, ReleaseHold, ROOT
from scripts.visual_quality_gate import video_check

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def allowed_paths(day: str, root: Path = ROOT) -> list[str]:
    if not DATE_RE.fullmatch(day):
        raise ReleaseHold("RELEASE_INVALID_DATE")
    root = Path(root)
    styled = styled_manifest(day, root) is not None
    gate = check(day, root=root, mode="cards")
    card_dir = root / "cards" / day
    images = sorted(card_dir.glob("card_*.jpg" if styled else "card_*.png"))
    if not styled and not images:
        images = sorted(card_dir.glob("card_*.jpg"))
    if not images:
        raise ReleaseHold("RELEASE_PUBLIC_CARD_FILES_MISSING")
    if styled and [p.name for p in images] != [f"card_{i:02d}.jpg" for i in range(1, 7)]:
        raise ReleaseHold("RELEASE_CARD_INVENTORY_MISMATCH")
    paths = [p.relative_to(root).as_posix() for p in images]
    main_video = root / "reels" / f"{day}_tts.mp4"
    if not main_video.is_file():
        raise ReleaseHold("RELEASE_PUBLIC_MAIN_REEL_MISSING")
    check(day, root=root, mode="video", video=main_video)
    paths.append(main_video.relative_to(root).as_posix())
    # Do not even stage IG A/B variants unless individually signed (styled),
    # or independently playable under legacy policy (pre-2026-11-22).
    for variant in ("A", "B"):
        f = root / "reels" / f"{day}_tts_ig_{variant}.mp4"
        if not f.exists():
            continue
        if styled:
            try:
                check(day, root=root, mode="video", video=f)
            except (ReleaseHold, OSError, ValueError):
                # Unapproved file stays local and cannot leak to raw hosting.
                continue
        elif video_check(f, require_audio=True).get("status") != "PASS":
            continue
        paths.append(f.relative_to(root).as_posix())
    return paths


def stage(day: str, root: Path = ROOT) -> list[str]:
    files = allowed_paths(day, root)
    staged = subprocess.run(["git", "diff", "--cached", "--name-only"], cwd=root,
                            capture_output=True, text=True, check=True).stdout.strip()
    if staged:
        raise ReleaseHold("RELEASE_UNEXPECTED_PRESTAGED_FILES")
    subprocess.run(["git", "add", "--", *files], cwd=root, check=True)
    actual = subprocess.run(["git", "diff", "--cached", "--name-only"], cwd=root,
                            capture_output=True, text=True, check=True).stdout.splitlines()
    if not set(actual).issubset(set(files)):
        raise ReleaseHold("RELEASE_STAGING_OUTSIDE_APPROVAL_SCOPE")
    return files


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("day")
    p.add_argument("--stage", action="store_true", help="explicit git stage after validation")
    args = p.parse_args()
    files = stage(args.day) if args.stage else allowed_paths(args.day)
    for file in files:
        print(f"[SIGNED_SCOPE] {file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
