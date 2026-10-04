# -*- coding: utf-8 -*-
"""Threads 공개 사주풀이 이벤트 글 발행.

주 3회(화 오전, 목·일 저녁) 공개 댓글 참여용 글을 올린다.
- 공개풀이를 원하는 이용자는 댓글에 생년월일시/성별/질문을 자발적으로 남길 수 있다.
- 개인정보 공개가 부담되면 Instagram DM을 안내한다.
- 실제 댓글 풀이는 threads_growth.py + threads_fortune_public.py가 처리한다.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import time
from pathlib import Path

import requests

GRAPH = "https://graph.threads.net/v1.0"
BASE = Path(__file__).resolve().parent
OUT = BASE / "public_saju_events"
KST = dt.timezone(dt.timedelta(hours=9))

THEMES = {
    1: ("재물·직장", "재물운·직장운·이직운 중 지금 가장 궁금한 것 1개"),
    4: ("사업·변화", "사업운·이직운·새로운 기회 중 지금 가장 궁금한 것 1개"),
    0: ("연애·종합", "연애운·인연운·재물운·직장운 중 지금 가장 궁금한 것 1개"),
}


def kst_today() -> dt.date:
    return dt.datetime.now(KST).date()


def build_text(day: dt.date) -> str:
    title, question = THEMES.get(day.weekday(), ("오늘의 사주", "지금 가장 궁금한 것 1개"))
    return (
        f"오늘 공개 사주풀이 받습니다 🔮 · {title}\n\n"
        "공개풀이를 원하시면 댓글에\n"
        "① 양력/음력 ② 생년월일 ③ 태어난 시간 ④ 성별\n"
        f"⑤ {question}\n\n"
        "공개해도 괜찮은 분만 댓글로 남겨주세요.\n"
        "개인정보 공개가 부담되면 인스타 DM으로 보내주세요.\n"
        "답글에서는 생년월일시는 다시 적지 않고 풀이만 드립니다.\n"
        "※ 전통 명리학을 바탕으로 한 참고용 간단풀이입니다."
    )


def marker(day: dt.date) -> Path:
    return OUT / f"{day.isoformat()}.json"


def publish(text: str) -> str:
    from zodiac_cardnews import _threads_uid

    tok = os.environ["THREADS_ACCESS_TOKEN"]
    uid = _threads_uid(tok)
    base = f"{GRAPH}/{uid}"
    j = requests.post(
        f"{base}/threads",
        timeout=30,
        data={"media_type": "TEXT", "text": text, "access_token": tok},
    ).json()
    cid = j.get("id")
    if not cid:
        raise SystemExit(f"[FAIL] public-saju container: {j}")
    time.sleep(3)
    j = requests.post(
        f"{base}/threads_publish",
        timeout=30,
        data={"creation_id": cid, "access_token": tok},
    ).json()
    pid = j.get("id")
    if not pid:
        raise SystemExit(f"[FAIL] public-saju publish: {j}")
    return str(pid)


def main() -> int:
    day = kst_today()
    OUT.mkdir(parents=True, exist_ok=True)
    mk = marker(day)
    if mk.exists():
        print(f"[SKIP] {day} 공개 사주 이벤트 이미 발행됨")
        return 0

    text = build_text(day)
    print(text)
    if os.environ.get("PUBLIC_SAJU_DRY_RUN", "") == "1":
        print("[DRY] 발행하지 않음")
        return 0

    pid = publish(text)
    tmp = mk.with_suffix(".tmp")
    tmp.write_text(
        json.dumps({"date": day.isoformat(), "post_id": pid, "kind": "public_saju_event"},
                   ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    tmp.replace(mk)
    print(f"[OK] 공개 사주 이벤트 발행: {pid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
