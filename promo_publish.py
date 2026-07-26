"""홍보 카드뉴스(캐러셀) + 쇼츠(릴스) 스레드 발행.

  python promo_publish.py carousel free
  python promo_publish.py reel free
  python promo_publish.py all free
  python promo_publish.py all --auto      # 주차로 세트 자동 선택

발행 로직(컨테이너 → threads_publish)은 띠별운세와 동일한 zodiac_cardnews·zodiac_reels
함수를 그대로 쓴다. 이미지·영상은 GitHub raw 로 호스팅하므로 커밋·푸시가 선행돼야 한다.

본문에 링크를 넣지 않는다 — 스레드는 본문 링크가 노출을 눌러, 프로필 유입이 우리 관례다.
같은 세트를 같은 날 두 번 올리지 않도록 멱등 마커를 남긴다.
"""
from __future__ import annotations
import json
import sys
import datetime as dt
from pathlib import Path

import promo_content as pc
from zodiac_cardnews import publish_carousel, publish_reply, RAW_BASE
from zodiac_reels import publish_video

BASE = Path(__file__).resolve().parent
OUT = BASE / "promo"

FIRST_COMMENT = (
    "무료 오늘의 운세는 프로필 링크에서 바로 보실 수 있어요 🔮\n"
    "궁금한 점은 댓글로 편하게 남겨주세요."
)


def _week_index(today: dt.date | None = None) -> int:
    """주차 기준 세트 순환. 토요일 1회 발행이므로 주 단위로 하나씩 넘어간다."""
    d = today or dt.date.today()
    return d.isocalendar()[1]


def _marker(key: str, kind: str) -> Path:
    return OUT / key / f"pub_{kind}_{dt.date.today().isoformat()}.json"


def do_carousel(key: str) -> None:
    s = pc.BY_KEY[key]
    mk = _marker(key, "carousel")
    if mk.exists():
        print(f"[스킵] {key} 캐러셀 오늘 이미 발행됨")
        return
    files = sorted((OUT / key).glob("card_*.png"))
    if len(files) < 2:
        raise SystemExit(f"[FAIL] 카드가 없습니다: promo/{key}")
    urls = [f"{RAW_BASE}/promo/{key}/{f.name}" for f in files]
    pid = publish_carousel(urls, s["caption"])
    print(f"[OK] promo carousel: {pid}")
    try:
        publish_reply(pid, FIRST_COMMENT)
    except Exception as e:
        print(f"[WARN] 첫댓글 실패: {e}")
    mk.write_text(json.dumps({"post_id": pid}, ensure_ascii=False), encoding="utf-8")


def do_reel(key: str) -> None:
    s = pc.BY_KEY[key]
    mk = _marker(key, "reel")
    if mk.exists():
        print(f"[스킵] {key} 릴스 오늘 이미 발행됨")
        return
    video = OUT / key / "shorts.mp4"
    if not video.exists():
        raise SystemExit(f"[FAIL] 영상이 없습니다: {video}")
    pid = publish_video(f"{RAW_BASE}/promo/{key}/shorts.mp4", s["caption"])
    print(f"[OK] promo reel: {pid}")
    try:
        publish_reply(pid, FIRST_COMMENT)
    except Exception as e:
        print(f"[WARN] 첫댓글 실패: {e}")
    mk.write_text(json.dumps({"post_id": pid}, ensure_ascii=False), encoding="utf-8")


def main():
    args = sys.argv[1:]
    mode = args[0] if args else "all"
    key = None
    for a in args[1:]:
        if a == "--auto":
            key = pc.pick_set(_week_index())["key"]
        elif not a.startswith("--"):
            key = a
    key = key or pc.pick_set(_week_index())["key"]
    if key not in pc.BY_KEY:
        raise SystemExit(f"세트는 {list(pc.BY_KEY)} 중 하나여야 합니다")

    print(f"=== 홍보 발행: {key} ({pc.BY_KEY[key]['title']}) ===")
    if mode in ("carousel", "all"):
        do_carousel(key)
    if mode in ("reel", "all"):
        do_reel(key)


if __name__ == "__main__":
    main()
