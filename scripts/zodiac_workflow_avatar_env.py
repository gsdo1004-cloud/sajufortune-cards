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
    manifest_path = root / "assets" / "flux_daily" / day / "manifest.json"
    layout_path = root / "cards" / day / "layout_manifest.json"
    manifest = _json(manifest_path) if manifest_path.exists() else None
    layout = _json(layout_path) if layout_path.exists() else None
    mstyle = manifest.get("style_id") if manifest else None
    lstyle = layout.get("style_id") if layout else None
    if mstyle is None or mstyle == "":
        if lstyle:
            raise WorkflowHold("STYLED_LAYOUT_WITHOUT_ATLAS_MANIFEST")
        return "LEGACY"
    if not isinstance(mstyle, str) or mstyle not in VALID_STYLES:
        raise WorkflowHold("UNRECOGNIZED_STYLE_ID")
    if lstyle and lstyle != mstyle:
        raise WorkflowHold("STYLED_LAYOUT_STYLE_MISMATCH")
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
