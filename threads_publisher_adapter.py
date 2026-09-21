"""Adapter from queue jobs to the existing official Threads publisher.

Importing this module never publishes. Network work only happens inside
publish_job(), which the queue worker protects behind its live gates.
"""
from pathlib import Path

import threads_conversion as conv
import zodiac_cardnews as zc


def build_zodiac_payload(item: dict) -> dict:
    target = str(item["target"])
    outdir = Path(zc.__file__).resolve().parent / "cards" / target
    marker = outdir / "threads_pub_carousel.json"
    if marker.exists():
        raise RuntimeError(f"receipt already exists for {target}")
    files = sorted(outdir.glob("card_*.png")) or sorted(outdir.glob("card_*.jpg"))
    if not files:
        raise RuntimeError(f"no card assets for {target}")
    urls = [f"{zc.RAW_BASE}/cards/{target}/{f.name}" for f in files]
    base_caption = f"{zc.date_full(target)} 오늘의 띠별 운세 🔮\n내 띠는 오늘 어떤 흐름일까요?"
    return {"target": target, "urls": urls,
            "caption": conv.apply(base_caption, "carousel", target)}


def publish_job(item: dict) -> str:
    if item.get("kind") != "zodiac_carousel":
        raise RuntimeError(f"unsupported queue kind: {item.get('kind')}")
    payload = build_zodiac_payload(item)
    return str(zc.publish_carousel(payload["urls"], payload["caption"], payload["target"]))
