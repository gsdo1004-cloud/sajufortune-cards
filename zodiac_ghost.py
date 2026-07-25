"""쓰레드 유령 게시물(Ghost post) 자동 발행 — 매일 아침 한 줄.

유령 게시물은 24시간 뒤 자동 보관되는 임시 글이다. 계정에 영구 콘텐츠로 쌓이지
않으므로, 매일 올려도 "같은 글 도배"로 보이지 않는다. 정규 발행물(카드뉴스·릴스)은
저녁에 나가므로, 아침에는 이걸로 프로필 방문을 만든다.

Threads API 는 2025-12-15 부터 ghost post 를 지원한다.
  POST /{threads-user-id}/threads  ... media_type=TEXT, text=..., is_ghost_post=true
  POST /{threads-user-id}/threads_publish  ... creation_id=...
  https://developers.facebook.com/docs/threads/create-posts/ghost-posts/

본문에는 링크를 넣지 않는다(스레드는 본문 링크가 있으면 노출이 눌린다 — 프로필
링크로 유도하는 것이 우리 관례). 문구는 날짜·일진·오늘 기운 좋은 띠를 섞어
매일 달라지고, 같은 형태가 반복되지 않도록 템플릿을 날짜로 회전시킨다.

실행:
  python zodiac_ghost.py            # 오늘자 발행
  python zodiac_ghost.py --dry-run  # 문구만 출력(발행 안 함)
  python zodiac_ghost.py 2026-07-28 # 날짜 지정
환경변수: THREADS_ACCESS_TOKEN, THREADS_USER_ID
"""
from __future__ import annotations
import os
import sys
import json
import time
import datetime as dt
from pathlib import Path

import zodiac_seo as zs
from ganzhi_zodiac import day_context

BASE = Path(__file__).resolve().parent
GRAPH = "https://graph.threads.net/v1.0"

WEEKDAY_KO = ["월", "화", "수", "목", "금", "토", "일"]

# 템플릿 — 날짜로 회전시킨다. {ganzhi} 일진, {top} 기운 좋은 띠 3개, {md} 7월 28일,
# {wd} 요일. 링크는 넣지 않는다(프로필 링크로 유도).
TEMPLATES = [
    "{md}({wd}) 오늘은 {ganzhi}입니다.\n"
    "오늘 기운을 타는 띠는 {top}이에요.\n"
    "내 띠는 어떤 하루인지, 프로필에서 무료로 확인해보세요 🔮",

    "아침부터 마음이 분주하신가요?\n"
    "{md} 오늘의 일진은 {ganzhi}. 서두르기보다 한 박자 늦추면 좋은 날입니다.\n"
    "띠별 흐름은 프로필 링크에 올려두었어요 🙂",

    "{ganzhi}. {md}({wd})의 기운입니다.\n"
    "{top} — 오늘 이 띠들은 하려던 일을 밀고 나가기 좋아요.\n"
    "나머지 띠는 프로필에서 확인하세요 🔮",

    "오늘 하루, 무엇부터 하실 건가요?\n"
    "{md} 일진 {ganzhi} 기준으로 보면 {top}에게 특히 유리한 흐름입니다.\n"
    "내 띠 운세는 프로필 링크에서 무료로 봅니다 🙂",

    "{md}({wd}) 아침입니다.\n"
    "오늘은 {ganzhi} — 결정보다 정리에 어울리는 기운이에요.\n"
    "12띠 전체 흐름은 프로필에 정리해 두었습니다 🔮",

    "잘 풀리는 날과 그렇지 않은 날, 차이가 궁금하셨다면.\n"
    "{md} 오늘은 {ganzhi}이고, {top}이 앞서 나가는 날입니다.\n"
    "내 띠 확인은 프로필 링크에서요 🙂",

    "{top}.\n"
    "{md}({wd}) 오늘 기운이 좋은 띠입니다. 일진은 {ganzhi}.\n"
    "내 띠가 없다고 서운해 마세요 — 흐름은 매일 바뀝니다. 프로필에서 확인해보세요 🔮",
]


def _fmt_date(d: dt.date) -> tuple[str, str]:
    return f"{d.month}월 {d.day}일", WEEKDAY_KO[d.weekday()]


ORDER = ["rat", "ox", "tiger", "rabbit", "dragon", "snake",
         "horse", "goat", "monkey", "rooster", "dog", "pig"]


def _top_signs(date_iso: str, n: int = 3) -> str:
    """그날 점수가 높은 띠 n개. 카드·릴스와 같은 근거(zodiac_seo.make_reading)를 쓴다."""
    try:
        R = {s: zs.make_reading(s, date_iso) for s in ORDER}
        order = sorted(ORDER, key=lambda s: R[s].overall_score, reverse=True)[:n]
        # sign_ko 는 이미 '쥐띠' 형태라 '띠'를 덧붙이면 '쥐띠띠'가 된다.
        return ", ".join(R[s].sign_ko if R[s].sign_ko.endswith("띠")
                         else f"{R[s].sign_ko}띠" for s in order)
    except Exception:
        return "여러 띠"


def build_text(date_iso: str) -> str:
    d = dt.date.fromisoformat(date_iso)
    md, wd = _fmt_date(d)
    try:
        ganzhi = day_context(d).get("label") or "오늘의 일진"   # 예: '경자일'
    except Exception:
        ganzhi = "오늘의 일진"
    tpl = TEMPLATES[d.toordinal() % len(TEMPLATES)]
    return tpl.format(md=md, wd=wd, ganzhi=ganzhi, top=_top_signs(date_iso))


def publish_ghost(text: str) -> str:
    import requests
    tok = os.environ["THREADS_ACCESS_TOKEN"]
    uid = os.environ["THREADS_USER_ID"]
    base = f"{GRAPH}/{uid}"

    j = requests.post(f"{base}/threads", timeout=30, data={
        "media_type": "TEXT", "text": text,
        "is_ghost_post": "true", "access_token": tok}).json()
    cid = j.get("id")
    if not cid:
        raise SystemExit(f"[FAIL] ghost container: {j}")
    time.sleep(3)
    j = requests.post(f"{base}/threads_publish", timeout=30,
                      data={"creation_id": cid, "access_token": tok}).json()
    pid = j.get("id")
    if not pid:
        raise SystemExit(f"[FAIL] ghost publish: {j}")
    return pid


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry-run" in sys.argv
    date_iso = args[0] if args else zs.today_iso()

    text = build_text(date_iso)
    print(f"----- {date_iso} 유령 게시물 -----\n{text}\n------------------------")
    if dry:
        print("[DRY-RUN] 발행하지 않았습니다.")
        return

    # 멱등 가드: 같은 날 두 번 올리지 않는다.
    marker = BASE / "cards" / date_iso / "threads_pub_ghost.json"
    if marker.exists():
        print(f"[스킵] {date_iso} 유령 게시물 이미 발행됨")
        return

    pid = publish_ghost(text)
    print(f"[OK] ghost post: {pid}")
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({"post_id": pid, "text": text}, ensure_ascii=False),
                      encoding="utf-8")


if __name__ == "__main__":
    main()
