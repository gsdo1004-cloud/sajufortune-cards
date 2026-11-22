#!/usr/bin/env python3
"""HomeCode offline FLUX-first image farm; no social publishing, no paid APIs."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

from PIL import Image, ImageStat

# Script entrypoint also works when launched by the existing local asset farm.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.zodiac_style_rotation import style_for_day
from scripts.zodiac_character_prompts import prompt_for, protected_boxes, SUBJECTS

ROOT = Path(__file__).resolve().parents[1]
STEMS = ("01_표지", "02_띠별A", "03_띠별B", "04_띠별C", "05_띠별D", "06_12띠요약")
SIZE = (1080, 1920)
SCHEMA = "social-flux-backgrounds-v1"
BROKER_ROOT = Path(os.environ.get("SOCIAL_FLUX_BROKER_ROOT", "/mnt/d/AutomationBrain"))
PROMPTS = (
    "serene golden sunrise, Korean mountains, eastern zodiac symbols",
    "cute friendly rat ox and tiger, magical warm meadow, peaceful Korean folk art",
    "friendly rabbit graceful Eastern dragon and cute snake in a heavenly garden",
    "horse goat and monkey, lush misty Korean waterfall, cinematic warm sunlight",
    "rooster dog pig, gentle twilight Korean palace garden, exquisite gold light",
    "twelve Korean zodiac animals depicted as elegant abstract constellations",
)
PROVIDERS = {"flux2_klein_local", "gemini_subscription_included_if_available"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def folder(day: str, root: Path = ROOT) -> Path:
    assert dt.date.fromisoformat(day).isoformat() == day
    return root / "assets" / "flux_daily" / day


def verify(day: str, root: Path = ROOT) -> dict:
    target = folder(day, root)
    m = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    if m.get("schema") != SCHEMA or m.get("date") != day:
        raise ValueError("FLUX manifest identity mismatch")
    entries = m.get("files") or []
    if [x.get("name") for x in entries] != [s + ".jpg" for s in STEMS]:
        raise ValueError("FLUX six-file inventory incomplete")
    expected = {"manifest.json"} | {s + ".jpg" for s in STEMS}
    if {p.name for p in target.iterdir() if p.is_file()} != expected:
        raise ValueError("FLUX inventory unexpected or missing file")
    style = style_for_day(day)
    if m.get("style_id") and m["style_id"] != style["id"]:
        raise ValueError("daily STYLE rotation mismatch")
    if m.get("paid_api_calls") != 0:
        raise ValueError("paid API usage not permitted")
    for i, entry in enumerate(entries):
        if m.get("style_id"):
            if entry.get("style_id") != style["id"] or entry.get("seed") is None:
                raise ValueError("style/seed missing")
            if entry.get("protected_regions") != [list(b) for b in protected_boxes(STEMS[i], *SIZE)]:
                raise ValueError("protected region contract mismatch")
        path = target / entry["name"]
        if not path.is_file() or path.is_symlink() or path.stat().st_size < 50_000:
            raise ValueError("FLUX image missing/undersized")
        with Image.open(path) as im:
            im.verify()
        with Image.open(path) as im:
            if im.format != "JPEG" or im.size != SIZE:
                raise ValueError("FLUX image type/size invalid")
            if max(ImageStat.Stat(im.convert("RGB")).stddev) < 10:
                raise ValueError("FLUX image blank")
        if entry.get("provider") not in PROVIDERS or entry.get("sha256") != sha256(path):
            raise ValueError("FLUX provenance/hash mismatch")
    return m


def background_path_for(day: str, stem: str, root: Path = ROOT) -> Path | None:
    if stem not in STEMS:
        raise ValueError("invalid FLUX card stem")
    target = folder(day, root)
    if not target.exists():
        return None
    verify(day, root)
    return target / (stem + ".jpg")


def _render_safe_jpeg(raw: Path, out: Path) -> None:
    with Image.open(raw) as im:
        rgb = im.convert("RGB")
        if min(rgb.size) < 400 or max(ImageStat.Stat(rgb).stddev) < 10:
            raise ValueError("blank/undersize provider output")
        scale = max(SIZE[0] / rgb.width, SIZE[1] / rgb.height)
        resized = rgb.resize((round(rgb.width * scale), round(rgb.height * scale)), Image.Resampling.LANCZOS)
        ox, oy = (resized.width - SIZE[0]) // 2, (resized.height - SIZE[1]) // 2
        resized.crop((ox, oy, ox + SIZE[0], oy + SIZE[1])).save(out, "JPEG", quality=86, optimize=True)
    if out.stat().st_size < 50_000:
        raise ValueError("JPEG too small")


def _generate(prompt: str, path: Path, seed: int) -> str:
    if not BROKER_ROOT.is_dir():
        raise RuntimeError("local FLUX broker not found")
    sys.path.insert(0, str(BROKER_ROOT))
    from imagegen_broker.provider_chain import generate_with_fallback
    result = generate_with_fallback(
        prompt, path,
        negative="text, watermark, cropped animals, horror, scary snakes, frightening rats",
        width=768, height=1344, steps=4, seed=seed, timeout_seconds=390,
        provider_order=["flux2_klein_local", "gemini_subscription_included_if_available"],
        allow_paid=False, max_paid_provider_attempts=0,
        emergency_fallback=False, commercial_use=True,
    )
    provider = result.get("provider")
    # The shared broker marks ALL successful raw generations PENDING_QA.
    # That is intentional and must not be changed globally. For this separate
    # offline social background lane, our strict JPEG validation, six-item
    # manifest/hash gate and downstream card validation perform that QA.
    # Never accept semantic-degraded or unapproved-provider results.
    if (not result.get("ok") or result.get("semantic_degraded")
            or provider not in PROVIDERS):
        raise RuntimeError("local FLUX and included image API unavailable")
    return provider


def prepare(day: str, root: Path = ROOT, generator=None) -> dict:
    target = folder(day, root)
    if target.exists():
        return verify(day, root)
    receipts = ("threads_pub_*.json", "instagram_pub_*.json",
                "youtube_pub*.json", "uploaded.json")
    card_folder = root / "cards" / day
    if any(any(card_folder.glob(pat)) for pat in receipts):
        raise ValueError("published day cannot be rewritten")
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=".flux-staging-", dir=target.parent))
    gen = generator or _generate
    try:
        entries = []
        style = style_for_day(day)
        for i, stem in enumerate(STEMS, 1):
            raw = temp / f".raw_{i}.png"
            jpg = temp / (stem + ".jpg")
            prompt = prompt_for(day, stem, "card")
            seed = int(day.replace("-", "")) * 10 + i
            provider = gen(prompt, raw, seed)
            if provider not in PROVIDERS:
                raise ValueError("unapproved image provider")
            _render_safe_jpeg(raw, jpg)
            raw.unlink(missing_ok=True)
            entries.append({"name": jpg.name, "sha256": sha256(jpg), "provider": provider,
                            "style_id":style["id"], "style_name":style["name"],
                            "subject":"east_asian_zodiac",
                            "main_zodiac":list(SUBJECTS[i-1]),
                            "protected_regions":[list(b) for b in protected_boxes(stem,*SIZE)],
                            "prompt":prompt, "seed":seed,
                            "safe_top_ratio":0.22, "safe_bottom_ratio":0.14,
                            "image_provider":provider, "model":provider})
        m = {"schema": SCHEMA, "date": day, "mode": "FLUX_LOCAL_THEN_INCLUDED_API",
             "style_id":style["id"], "style_name":style["name"],
             "subject":"east_asian_zodiac", "layout_protection_source":"composition_contract",
             "allow_paid":False, "max_paid_provider_attempts":0,
             "paid_api_calls": 0, "files": entries}
        (temp / "manifest.json").write_text(json.dumps(m, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if target.exists():
            raise ValueError("concurrent target appeared, hold")
        temp.rename(target)
        try:
            return verify(day, root)
        except Exception:
            target.rename(temp)
            raise
    finally:
        if temp.exists():
            shutil.rmtree(temp)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["prepare", "verify", "status"])
    ap.add_argument("date")
    args = ap.parse_args()
    try:
        if args.mode == "status":
            print(json.dumps({"date": args.date, "prepared": folder(args.date).exists()}))
            return 0
        m = prepare(args.date) if args.mode == "prepare" else verify(args.date)
        print(json.dumps({"ok": True, "date": args.date, "count": 6, "providers":
                          [x["provider"] for x in m["files"]], "paid_api_calls": 0}))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "date": args.date,
                          "reason": type(exc).__name__, "stage": args.mode}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

