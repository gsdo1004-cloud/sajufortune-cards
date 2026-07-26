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
# 말투 = 반말 (2026-07-27 전환).
# 스레드는 존댓말 글이 거의 없다. 블로그 문체로 쓰면 광고처럼 읽혀 반응이 죽는다.
# 사주 파는 계정들이 스레드에서 잘 되는 방식은 정보를 먼저 던지고, 더 궁금하면
# 알아서 오게 두는 것이다. 매달리는 문구("꼭 확인하세요")는 오히려 안 먹힌다.
#
# ⚠️ 과장·단정 금지: "무조건", "100%", "반드시", "보장" 류는 쓰지 않는다(PG 심사 규칙).
#    링크 URL 도 본문에 넣지 않는다 — 스레드는 링크가 있으면 도달이 눌린다.
TEMPLATES = [
    "{md}({wd}) 오늘은 {ganzhi}.\n"
    "기운 타는 띠는 {top}.\n"
    "내 띠는 어떤 날인지, 프로필에 무료로 열어놨다 🔮",

    "아침부터 마음이 분주하면 잠깐 멈춰볼 것.\n"
    "{md} 일진은 {ganzhi}. 서두르는 것보다 한 박자 늦추는 게 나은 날이다.\n"
    "띠별 흐름은 프로필에 있다",

    "{ganzhi}. {md}({wd})의 기운.\n"
    "{top} — 오늘 이 띠들은 하려던 거 밀어붙여도 되는 날.\n"
    "나머지 띠는 프로필에서 무료로 본다 🔮",

    "오늘 뭐부터 할지 정했나.\n"
    "{md} 일진 {ganzhi}으로 보면 {top}한테 유리한 흐름이다.\n"
    "내 띠 궁금하면 프로필 링크",

    "{md}({wd}) 아침.\n"
    "오늘은 {ganzhi} — 새로 벌이기보다 정리에 어울리는 기운.\n"
    "12띠 전체는 프로필에 정리해 뒀다 🔮",

    "잘 풀리는 날이랑 아닌 날, 뭐가 다른가 싶을 때가 있다.\n"
    "{md} 오늘은 {ganzhi}. {top}{이가} 앞서 나가는 날이다.\n"
    "내 띠 확인은 프로필에서",

    "{top}.\n"
    "{md}({wd}) 오늘 기운 좋은 띠다. 일진은 {ganzhi}.\n"
    "내 띠 없다고 서운해할 것 없다. 흐름은 매일 바뀌니까 🔮",

    "{md} {ganzhi}.\n"
    "사주는 정해진 답이 아니라 그날 기운의 결이다. 오늘은 {top}{이가} 그 결을 탄다.\n"
    "내 띠 흐름은 프로필에서 무료로 볼 수 있다",

    "운세 본다고 뭐가 달라지냐 싶겠지만,\n"
    "{md}({wd}) {ganzhi} — 오늘 같은 날은 무리하지 않는 게 이득이다.\n"
    "{top}{은는} 예외. 나머지 띠는 프로필에 정리해 뒀다 🔮",
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


def _josa(word: str, with_batchim: str, without: str) -> str:
    """받침에 맞는 조사. '양띠이 그 결을', '닭띠은 예외' 같은 게 실제로 나왔다.
    조사 하나 틀리면 자동 생성물이라는 티가 바로 난다."""
    if not word:
        return without
    ch = word.strip()[-1]
    if not ("가" <= ch <= "힣"):
        return without
    return with_batchim if (ord(ch) - 0xAC00) % 28 else without


def build_text(date_iso: str) -> str:
    d = dt.date.fromisoformat(date_iso)
    md, wd = _fmt_date(d)
    try:
        ganzhi = day_context(d).get("label") or "오늘의 일진"   # 예: '경자일'
    except Exception:
        ganzhi = "오늘의 일진"
    tpl = TEMPLATES[d.toordinal() % len(TEMPLATES)]
    top = _top_signs(date_iso)
    return tpl.format(md=md, wd=wd, ganzhi=ganzhi, top=top,
                      이가=_josa(top, "이", "가"),
                      은는=_josa(top, "은", "는"),
                      을를=_josa(top, "을", "를"),
                      한테=_josa(top, "한테", "한테"))


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
