"""Read-only one-date workflow selector for *opt-in* signed FLUX/Hanbok render.

The only stdout strings are STYLED and LEGACY; never consume any user- or
manifest-controlled shell text as commands. Invalid styled metadata fails closed.
This selector does not itself authorize publication or approve any images.
"""
from __future__ import annotations
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
VALID_STYLES = frozenset(f"STYLE_{i:02d}" for i in range(1, 8))

class WorkflowHold(ValueError):
    pass

def _json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise WorkflowHold("STYLED_METADATA_MISSING_OR_INVALID") from exc
    if not isinstance(data, dict):
        raise WorkflowHold("STYLED_METADATA_INVALID_TYPE")
    return data

def mode(day: str, root: Path = ROOT) -> str:
    try:
        if dt.date.fromisoformat(day).isoformat() != day:
            raise ValueError
    except (ValueError, TypeError) as exc:
        raise WorkflowHold("INVALID_ISO_DATE") from exc
    root = Path(root)
    from scripts.zodiac_publish_guard import styled_manifest, ReleaseHold
    try:
        manifest = styled_manifest(day, root)
    except ReleaseHold as exc:
        raise WorkflowHold(str(exc)) from exc
    if manifest is None:
        return "LEGACY"
    mstyle = manifest.get("style_id")
    if not isinstance(mstyle, str) or mstyle not in VALID_STYLES:
        raise WorkflowHold("UNRECOGNIZED_STYLE_ID")
    return "STYLED"

def main() -> int:
    if len(sys.argv) != 2:
        print("USAGE: zodiac_workflow_avatar_env.py YYYY-MM-DD", file=sys.stderr)
        return 2
    try:
        print(mode(sys.argv[1]))
    except WorkflowHold as exc:
        print("[HOLD] " + str(exc), file=sys.stderr)
        return 3
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
