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
import threads_conversion as conv
from ganzhi_zodiac import day_context

BASE = Path(__file__).resolve().parent
GRAPH = "https://graph.threads.net/v1.0"
# 2026-09-06: token rotation verified; push triggers a live publish check.

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
    "{cta}",

    "아침부터 마음이 분주하면 잠깐 멈춰볼 것.\n"
    "{md} 일진은 {ganzhi}. 서두르는 것보다 한 박자 늦추는 게 나은 날이다.\n"
    "{cta}",

    "{ganzhi}. {md}({wd})의 기운.\n"
    "{top} — 오늘 이 띠들은 하려던 거 밀어붙여도 되는 날.\n"
    "{cta}",

    "오늘 뭐부터 할지 정했나.\n"
    "{md} 일진 {ganzhi}{으로} 보면 {top}한테 유리한 흐름이다.\n"
    "{cta}",

    "{md}({wd}) 아침.\n"
    "오늘은 {ganzhi} — 새로 벌이기보다 정리에 어울리는 기운.\n"
    "{cta}",

    "잘 풀리는 날이랑 아닌 날, 뭐가 다른가 싶을 때가 있다.\n"
    "{md} 오늘은 {ganzhi}. {top}{이가} 앞서 나가는 날이다.\n"
    "{cta}",

    "{top}.\n"
    "{md}({wd}) 오늘 기운 좋은 띠다. 일진은 {ganzhi}.\n"
    "내 띠 없다고 서운해할 것 없다. 흐름은 매일 바뀌니까.\n"
    "{cta}",

    "{md} {ganzhi}.\n"
    "사주는 정해진 답이 아니라 그날 기운의 결이다. 오늘은 {top}{이가} 그 결을 탄다.\n"
    "{cta}",

    "운세 본다고 뭐가 달라지냐 싶겠지만,\n"
    "{md}({wd}) {ganzhi} — 오늘 같은 날은 무리하지 않는 게 이득이다.\n"
    "{top}{은는} 예외.\n"
    "{cta}",
]


# ── 유입 문구 풀 (2026-07-27) ────────────────────────────────
# 템플릿마다 마무리를 고정해 두면 9일이면 한 바퀴가 돌아 금방 같은 말이 반복된다.
# 본문과 마무리를 분리해 (본문 9) x (마무리 20) = 180 조합으로 늘린다.
# 두 축을 서로 다른 주기로 돌려(본문 %9, 마무리 %20) 같은 짝이 다시 만나기까지 오래 걸린다.
#
# 화법 원칙 — 스레드에서 사주 파는 계정들이 실제로 쓰는 방식:
#   ① 매달리지 않는다. "꼭 보세요" 대신 "궁금하면 와서 봐라" 정도로 둔다
#   ② 무료라는 사실만 담백하게 알린다. 유료 얘기는 꺼내지 않는다(프로필에서 알아서 본다)
#   ③ 조건을 낮춘다 — 생년월일만 있으면 된다는 식으로 진입장벽을 지운다
# ⚠️ 금지: 무조건·100%·반드시·보장·대박 / 본문 URL / DM 유도(스팸 판정 위험)
CTA_POOL = [
    "내 띠는 어떤 날인지, 프로필에 무료로 열어놨다 🔮",
    "띠별 흐름은 프로필에 있다",
    "나머지 띠는 프로필에서 무료로 본다 🔮",
    "내 띠 궁금하면 프로필 링크",
    "12띠 전체는 프로필에 정리해 뒀다 🔮",
    "내 띠 확인은 프로필에서",
    "생년월일만 있으면 프로필에서 바로 본다",
    "오늘 내 사주 흐름, 프로필에서 무료로 볼 수 있다 🔮",
    "궁금한 사람만 프로필로",
    "내 띠 안 나왔으면 프로필에서 찾아보면 된다",
    "프로필에 오늘 운세 전부 올려놨다",
    "무료니까 부담 없이 보고 가도 된다 🔮",
    "내 사주도 같은 식으로 본다. 프로필에 있다",
    "띠만 알면 되니까 어렵지 않다. 프로필 참고",
    "오늘 흐름 정도는 알고 시작하는 게 낫다 🔮",
    "프로필에서 무료로 확인 가능",
    "자세한 건 프로필에 적어놨다",
    "내 띠 순위 궁금하면 프로필 한 번 보고 가라",
    "매일 아침 올린다. 프로필에 쌓아두는 중 🔮",
    "생년월일 넣으면 내 사주도 무료로 나온다. 프로필에",
]

# 금지어 — 발행 직전 자동 검사. 걸리면 그 문구를 버리고 기본형으로 간다.
BANNED = ["무조건", "100%", "반드시", "보장", "대박", "확실히", "절대"]


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
    jong = (ord(ch) - 0xAC00) % 28
    # '으로/로'는 예외다 — 받침이 ㄹ(8)이면 '로'를 쓴다.
    # 일진이 늘 '~일'로 끝나서 '병인일으로'가 실제로 나왔다.
    if with_batchim == "으로" and jong == 8:
        return without
    return with_batchim if jong else without


def build_text(date_iso: str) -> str:
    d = dt.date.fromisoformat(date_iso)
    md, wd = _fmt_date(d)
    try:
        ganzhi = day_context(d).get("label") or "오늘의 일진"   # 예: '경자일'
    except Exception:
        ganzhi = "오늘의 일진"
    tpl = TEMPLATES[d.toordinal() % len(TEMPLATES)]
    top = _top_signs(date_iso)
    # 매 글이 광고가 되지 않도록 reach/bridge/conversion 단계를 날짜별로 배분한다.
    cta = conv.cta("ghost", date_iso, top)
    if any(b in cta for b in BANNED):
        cta = conv.cta("ghost", date_iso, top)
    return tpl.format(md=md, wd=wd, ganzhi=ganzhi, top=top, cta=cta,
                      이가=_josa(top, "이", "가"),
                      은는=_josa(top, "은", "는"),
                      을를=_josa(top, "을", "를"),
                      한테=_josa(top, "한테", "한테"),
                      으로=_josa(ganzhi, "으로", "로"))


def publish_ghost(text: str, date_iso: str) -> str:
    import requests
    tok = os.environ["THREADS_ACCESS_TOKEN"]
    uid = os.environ["THREADS_USER_ID"]
    base = f"{GRAPH}/{uid}"

    payload = {"media_type": "TEXT", "text": text,
               "is_ghost_post": "true", "access_token": tok,
               "topic_tag": conv.topic_tag("ghost", date_iso)}
    j = requests.post(f"{base}/threads", timeout=30, data=payload).json()
    cid = j.get("id")
    if not cid:
        # topic_tag가 계정/지역/주제 사전에서 거절돼도 게시 자체는 살린다.
        payload.pop("topic_tag", None)
        j = requests.post(f"{base}/threads", timeout=30, data=payload).json()
        cid = j.get("id")
    if not cid:
        # Ghost 기능 자체가 계정/지역/API 상태 때문에 거절될 수 있다.
        # 그 경우 그날 게시물을 0편으로 만들지 말고 일반 TEXT 게시물로 최종 폴백한다.
        # 동일 main() 멱등 마커를 쓰므로 성공 후 재실행 중복은 없다.
        fallback = {"media_type": "TEXT", "text": text, "access_token": tok}
        j = requests.post(f"{base}/threads", timeout=30, data=fallback).json()
        cid = j.get("id")
    if not cid:
        raise SystemExit(f"[FAIL] ghost/text container: {j}")
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

    pid = publish_ghost(text, date_iso)
    print(f"[OK] ghost post: {pid}")
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({"post_id": pid, "text": text}, ensure_ascii=False),
                      encoding="utf-8")


if __name__ == "__main__":
    main()
