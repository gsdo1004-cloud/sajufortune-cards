# -*- coding: utf-8 -*-
"""Threads 공개 사주풀이 이벤트 글 발행.

운영
- 예정 발행은 그대로 유지: 화 09:00 / 목 20:00 / 일 20:00 (KST)
- 사용자가 직접 지시할 때는 workflow_dispatch 로 즉시 발행 가능
- 공개 댓글에 생년월일시/성별/질문을 자발적으로 남긴 사람만 공개풀이
- 비공개 DM 유도는 현재 보류
- 답글에서 원문 생년월일시는 다시 적지 않는다

10개 유도문은 Threads 공식 성장 팁(대화 유도, 원본성, 주말 참여, 2~5+회/주)
및 실제 사주 계정의 '띠/연도+질문' 훅을 참고해 만들었다.
"""
from __future__ import annotations

import argparse
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

# 스하리는 풀이의 대가/조건으로 강제하지 않는다.
# '마음에 들면' 수준의 선택형 표현만 일부 샘플에 넣는다.
OPTIONAL_TIP = "복채는 선택이야. 풀이가 마음에 들면 스하리 해주면 고맙고 :)"

SPECIAL_TEMPLATES = {
    "holiday_mid": {
        "name": "연휴중간_즉시형",
        "text": (
            "연휴 중간인데 사주 한번 풀어볼까 🔥\n\n"
            "요즘 제일 답답한 거 딱 하나만 물어봐.\n"
            "생일시 + 성별 + 고민 1개\n"
            "구체적으로 적을수록 더 정확하게 봐줄게.\n\n"
            "재물 / 사업 / 이직 / 연애 / 재회 다 괜찮아.\n"
            "공개해도 괜찮은 사람만 댓글 남겨줘.\n\n"
            + OPTIONAL_TIP
        ),
    },
}

TEMPLATES = {
    1: {
        "name": "10명_정밀형",
        "text": (
            "오늘 공개 사주 10명만 제대로 봐줄게 🔮\n\n"
            "좋은 말만 한두 줄 적는 풀이 말고,\n"
            "묻는 한 가지를 중심으로 지금 흐름과 가까운 시기까지 자세히 볼게.\n\n"
            "공개해도 괜찮은 사람만 댓글에\n"
            "① 양력/음력 ② 생년월일 ③ 태어난 시간 ④ 성별\n"
            "⑤ 재물·직장·사업·연애 중 딱 1가지 고민\n\n"
            "답글에는 생년월일시는 다시 적지 않고 풀이만 남길게.\n"
            ""
        ),
    },
    2: {
        "name": "결정앞둔사람",
        "text": (
            "지금 이직·사업·연애에서 결정을 앞둔 사람 있어?\n"
            "오늘은 사주로 '지금 움직일 때인지, 조금 더 볼 때인지' 공개로 봐줄게.\n\n"
            "댓글: 양/음력 · 생년월일 · 태어난 시간 · 성별 · 고민 1개\n"
            "공개 가능한 사람만 남겨줘.\n"
            "묻는 것만 잡아서 지금 흐름과 시기를 중심으로 자세히 풀어줄게.\n"
            "생년정보는 답글에서 다시 반복하지 않아."
        ),
    },
    3: {
        "name": "재물직장집중",
        "text": (
            "돈 때문에 답답하거나 직장을 옮길까 고민 중이면 오늘 들어와.\n\n"
            "재물운은 '돈 들어온다' 한마디보다\n"
            "언제 움직이고, 뭘 조심하고, 사람운이 어떻게 붙는지가 더 중요해.\n\n"
            "양/음력 · 생년월일 · 태어난 시간 · 성별 + 재물/직장 고민 1개 남겨줘.\n"
            "공개해도 괜찮은 사람만. 묻는 분야의 흐름과 시기만 집중해서 봐줄게."
        ),
    },
    4: {
        "name": "좋은말만안함",
        "text": (
            "오늘은 좋은 말만 해주는 사주풀이 안 할게.\n"
            "좋은 흐름은 좋은 흐름대로, 조심할 시기는 조심하라고 말해줄게.\n\n"
            "공개풀이 원하는 사람은\n"
            "양력/음력 · 생년월일 · 태어난 시간 · 성별 · 궁금한 것 1개.\n\n"
            "짧은 띠풀이가 아니라 실제 생년월일 기준으로 묻는 것만 자세히 볼게.\n"
            "답글에는 개인정보를 다시 옮겨 적지 않아."
        ),
    },
    5: {
        "name": "올해남은기간",
        "text": (
            "올해 남은 기간, 내 운에서 뭐가 제일 크게 움직일까?\n"
            "재물 · 직장 · 사업 · 인연 중 하나만 골라줘.\n\n"
            "양/음력 · 생년월일 · 태어난 시간 · 성별 + 질문 1개를 댓글에 남기면\n"
            "다른 얘기 섞지 않고 '지금부터 가까운 시기'를 중심으로 그 질문만 볼게.\n"
            "공개 가능한 사람만 참여해줘. 생년정보는 답글에 반복하지 않아."
        ),
    },
    6: {
        "name": "딱한가지질문",
        "text": (
            "사주는 질문이 구체적일수록 답도 구체적으로 나와.\n"
            "오늘은 '딱 한 가지'만 물어봐줘.\n\n"
            "예) 이직해도 될까 / 사업 방향 바꿔도 될까 / 재물 흐름 언제 풀릴까 / 인연운은?\n\n"
            "양/음력 · 생년월일 · 태어난 시간 · 성별 · 질문 1개.\n"
            "공개 가능한 사람만 댓글로. 질문 분야와 시기까지 묶어서 풀어줄게."
        ),
    },
    7: {
        "name": "사주샘플상담",
        "text": (
            "무료사주인데 '운이 좋아요' 한 줄이면 나라도 안 볼 것 같아.\n"
            "그래서 오늘은 공개 미니상담처럼 풀어볼게.\n\n"
            "질문한 한 가지를 기준으로 지금 흐름 · 시기 · 조심할 점\n"
            "이것만 구체적으로 답할게.\n\n"
            "양/음력 · 생년월일 · 태어난 시간 · 성별 · 고민 1개 남겨줘.\n"
            "공개 가능한 사람만 참여."
        ),
    },
    8: {
        "name": "사업이직기회",
        "text": (
            "요즘 '이 자리에 계속 있어야 하나?' 생각이 자주 들면 남겨봐.\n"
            "오늘은 사업·이직·새로운 자리 흐름만 집중해서 볼게.\n\n"
            "양/음력 · 생년월일 · 태어난 시간 · 성별\n"
            "+ 지금 고민 중인 선택을 한 줄로 적어줘.\n\n"
            "사업·이직 질문만 보고, 움직임이 강해지는 시점까지 공개로 답할게."
        ),
    },
    9: {
        "name": "연애인연",
        "text": (
            "연애운은 '인연이 와요'보다 어떤 관계를 조심해야 하는지가 더 중요해.\n"
            "오늘은 인연·재회·결혼 고민 위주로 공개풀이할게.\n\n"
            "양/음력 · 생년월일 · 태어난 시간 · 성별 + 질문 1개.\n"
            "공개 가능한 사람만 댓글로 남겨줘.\n"
            "인연 질문만 보고, 관계 흐름과 가까운 시기를 구체적으로 답할게. 생년정보는 답글에 다시 적지 않아."
        ),
    },
    10: {
        "name": "복채선택형",
        "text": (
            "오늘 공개 사주풀이 열어둘게 🔮\n"
            "짧은 띠운세 말고 생년월일 기준으로 묻는 한 가지를 자세히 볼게.\n\n"
            "댓글에 양/음력 · 생년월일 · 태어난 시간 · 성별 · 고민 1개.\n"
            "공개 가능한 사람만 남겨줘.\n"
            "답글에는 생년월일을 다시 쓰지 않을게.\n\n"
            + OPTIONAL_TIP
        ),
    },
}

# 예약 실행은 주차/요일을 섞어 10종을 순환한다.
def scheduled_template_id(day: dt.date) -> int:
    return ((day.isocalendar().week * 3 + day.weekday()) % len(TEMPLATES)) + 1


def kst_now() -> dt.datetime:
    return dt.datetime.now(KST)


def kst_today() -> dt.date:
    return kst_now().date()


def build_text(day: dt.date, template_id: int | None = None, occasion: str = "") -> str:
    if occasion:
        item = SPECIAL_TEMPLATES.get(occasion)
        if not item:
            raise ValueError(f"unknown occasion: {occasion}")
        return item["text"]
    tid = template_id or scheduled_template_id(day)
    if tid not in TEMPLATES:
        raise ValueError(f"template_id must be 1..{len(TEMPLATES)}")
    return TEMPLATES[tid]["text"]


def marker(day: dt.date, *, manual: bool, template_id: int, occasion: str = "") -> Path:
    if manual:
        stamp = kst_now().strftime("%Y-%m-%d_%H%M%S")
        suffix = f"_{occasion}" if occasion else f"_t{template_id}"
        return OUT / f"{stamp}_manual{suffix}.json"
    return OUT / f"{day.isoformat()}_scheduled.json"


def publish(text: str) -> str:
    from zodiac_cardnews import _threads_uid

    tok = os.environ["THREADS_ACCESS_TOKEN"]
    uid = _threads_uid(tok)
    base = f"{GRAPH}/{uid}"
    payload = {
        "media_type": "TEXT",
        "text": text,
        "access_token": tok,
        "topic_tag": "사주",
    }
    j = requests.post(f"{base}/threads", timeout=30, data=payload).json()
    cid = j.get("id")
    if not cid:
        # topic_tag 미지원/오류면 본문만으로 재시도
        payload.pop("topic_tag", None)
        j = requests.post(f"{base}/threads", timeout=30, data=payload).json()
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


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--template", type=int, default=0, help="1..10; 0이면 예약 로테이션")
    ap.add_argument("--manual", action="store_true", help="즉시 지시 실행. 예약 중복마커와 분리")
    ap.add_argument("--occasion", default="", help="수동 상황형 문구. 예: holiday_mid")
    return ap.parse_args()


def main() -> int:
    a = parse_args()
    day = kst_today()
    tid = a.template or scheduled_template_id(day)
    if tid not in TEMPLATES:
        raise SystemExit("template must be 1..10")

    OUT.mkdir(parents=True, exist_ok=True)
    mk = marker(day, manual=a.manual, template_id=tid, occasion=a.occasion)
    if not a.manual and mk.exists():
        print(f"[SKIP] {day} 예약 공개 사주 이벤트 이미 발행됨")
        return 0

    text = build_text(day, tid, a.occasion)
    template_name = SPECIAL_TEMPLATES[a.occasion]["name"] if a.occasion else TEMPLATES[tid]["name"]
    print(f"[TEMPLATE] {a.occasion or tid} {template_name}")
    print(text)
    if os.environ.get("PUBLIC_SAJU_DRY_RUN", "") == "1":
        print("[DRY] 발행하지 않음")
        return 0

    pid = publish(text)
    tmp = mk.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(
            {
                "date": day.isoformat(),
                "post_id": pid,
                "kind": "public_saju_event",
                "manual": bool(a.manual),
                "template_id": tid,
                "occasion": a.occasion,
                "template_name": template_name,
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    tmp.replace(mk)
    print(f"[OK] 공개 사주 이벤트 발행: {pid} / template={tid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
