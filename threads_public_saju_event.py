# -*- coding: utf-8 -*-
"""Threads 공개 사주풀이 이벤트 글 발행.

운영
- 예정 발행은 그대로 유지: 화 09:00 / 목 20:00 / 일 20:00 (KST)
- 사용자가 직접 지시할 때는 workflow_dispatch 로 즉시 발행 가능
- 공개 댓글은 질문 주제만 요청하며 개인 출생정보는 공개 요청하지 않는다
- 비공개 DM 유도는 현재 보류
- 답글에서 원문 생년월일시는 다시 적지 않는다

기존 예약 슬롯에서만 일반형/질문형 훅 실험을 진행한다. 추가 발행 및 자동 답글은 없다.
"""
from __future__ import annotations

import argparse
import hashlib
import unicodedata
from difflib import SequenceMatcher
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

PRIVACY_NOTICE = "공개 댓글에는 생년월일·출생시간·성별·전화번호·주소 등 개인정보 기재 금지."

SPECIAL_TEMPLATES = {'holiday_mid': {'name': '연휴중간_개인정보보호형',
                 'text': '연휴 중에 사주가 궁금한 사람이 있어?\n'
                         '\n'
                         '재물·직업·인연 가운데 궁금한 주제만 댓글로 이야기해 줘. 개인적인 풀이는 프로필 신청 페이지에서 선택할 수 있어.'}}

TEMPLATES = {1: {'name': '재물운_개인정보보호형',
     'text': '재물운은 재성만 보면 충분할까?\n'
             '\n'
             '명리학에서는 재성의 역할과 대운의 흐름을 함께 살펴봐. 실제 재정 판단은 수입과 지출을 기준으로 하는 게 좋아.\n'
             '\n'
             '돈을 버는 것과 지키는 것 중 어느 쪽이 더 고민이야?\n'
             '무료 사주풀이에 관심 있다면 궁금한 주제만 이야기해 줘. 개인 출생정보는 공개하지 않는 게 좋아.'},
 2: {'name': '직업_개인정보보호형',
     'text': '직업운을 살펴볼 때 참고할 점이 있어.\n'
             '\n'
             '명리학에서는 관성과 식상의 역할을 함께 해석해. 실제 이직은 근무 조건과 생활 여건도 고려해야 해.\n'
             '\n'
             '일할 때 안정과 성장 중 무엇이 더 중요해?\n'
             '무료 사주풀이에 관심 있다면 궁금한 주제만 이야기해 줘. 개인 출생정보는 공개하지 않는 게 좋아.'},
 3: {'name': '관계_개인정보보호형',
     'text': '인연운은 만나는 시기만 중요할까?\n'
             '\n'
             '명리학에서는 배우자궁과 전체 흐름을 함께 봐. 현실에서는 대화와 존중이 중요해.\n'
             '\n'
             '관계에서 가장 소중하게 여기는 건 뭐야?\n'
             '무료 사주풀이에 관심 있다면 궁금한 주제만 이야기해 줘. 개인 출생정보는 공개하지 않는 게 좋아.'},
 4: {'name': '대운_개인정보보호형',
     'text': '대운의 의미를 정리해 볼게.\n'
             '\n'
             '명리학에서 대운은 장기적인 흐름을 해석하는 틀이야. 실제 변화는 상황과 선택에 따라 달라.\n'
             '\n'
             '최근에 바꿔 보고 싶은 생활 습관이 있어?\n'
             '무료 사주풀이에 관심 있다면 궁금한 주제만 이야기해 줘. 개인 출생정보는 공개하지 않는 게 좋아.'},
 5: {'name': '띠_개인정보보호형',
     'text': '열두 띠를 해석하는 기준이 있어.\n'
             '\n'
             '명리학에서는 태어난 해 외에도 월과 일, 시를 함께 해석해. 이런 해석은 가볍게 참고하는 것이 좋아.\n'
             '\n'
             '열두 띠 이야기에서 어떤 주제를 자주 읽어?\n'
             '무료 사주풀이에 관심 있다면 궁금한 주제만 이야기해 줘. 개인 출생정보는 공개하지 않는 게 좋아.'},
 6: {'name': '궁합_개인정보보호형',
     'text': '궁합을 해석할 때 살펴보는 점이 있어.\n'
             '\n'
             '명리학에서는 서로의 명식을 함께 살펴봐. 평소에는 서로의 말을 충분히 듣는 태도도 중요해.\n'
             '\n'
             '함께 지내며 중요하다고 느낀 태도는 뭐야?\n'
             '무료 사주풀이에 관심 있다면 궁금한 주제만 이야기해 줘. 개인 출생정보는 공개하지 않는 게 좋아.'},
 7: {'name': '신년_개인정보보호형',
     'text': '신년운세를 읽고 어떤 계획부터 세우면 좋을까?\n'
             '\n'
             '명리학의 세운은 한 해를 돌아보는 참고 틀이야. 현실적인 목표와 실행 계획을 함께 세워 보는 것도 좋아.\n'
             '\n'
             '새해에 가장 먼저 정리하고 싶은 일은 뭐야?\n'
             '무료 사주풀이에 관심 있다면 궁금한 주제만 이야기해 줘. 개인 출생정보는 공개하지 않는 게 좋아.'},
 8: {'name': '오행_개인정보보호형',
     'text': '오행이 골고루 있으면 좋은 명식일까?\n'
             '\n'
             '명리학에서는 오행의 개수보다 계절과 각 기운의 역할을 함께 해석해. 단순한 숫자로 사람을 평가할 수는 없어.\n'
             '\n'
             '오행을 공부할 때 어떤 부분이 가장 어렵게 느껴져?\n'
             '무료 사주풀이에 관심 있다면 궁금한 주제만 이야기해 줘. 개인 출생정보는 공개하지 않는 게 좋아.'},
 9: {'name': '일간_개인정보보호형',
     'text': '일간은 명리학의 출발점이야.\n'
             '\n'
             '일간은 명식의 중심으로 읽는 기준이지만 주변 글자와의 관계에 따라 해석이 달라져.\n'
             '\n'
             '자신의 성향을 돌아보는 데 어떤 기준이 도움이 돼?\n'
             '무료 사주풀이에 관심 있다면 궁금한 주제만 이야기해 줘. 개인 출생정보는 공개하지 않는 게 좋아.'},
 10: {'name': '식상_개인정보보호형',
      'text': '식상은 말솜씨만 뜻하는 걸까?\n'
              '\n'
              '명리학에서는 표현과 창작, 생각을 구체화하는 과정도 식상에 빗대어 해석해. 실제 역량은 경험과 연습으로 키울 수 있어.\n'
              '\n'
              '새롭게 배우고 싶은 표현이나 창작 활동이 있어?\n'
              '무료 사주풀이에 관심 있다면 궁금한 주제만 이야기해 줘. 개인 출생정보는 공개하지 않는 게 좋아.'}}

HOOK_EXPERIMENT = {'2026-11-26': {'slot': 1,
                'arm': 'B',
                'text': '재물운은 재성만 보면 충분할까?\n'
                        '\n'
                        '명리학에서는 재성의 역할과 대운의 흐름을 함께 살펴봐. 실제 재정 판단은 수입과 지출을 기준으로 하는 게 좋아.\n'
                        '\n'
                        '돈을 버는 것과 지키는 것 중 어느 쪽이 더 고민이야?\n'
                        '무료 사주풀이에 관심 있다면 궁금한 주제만 이야기해 줘. 개인 출생정보는 공개하지 않는 게 좋아.'},
 '2026-11-29': {'slot': 2,
                'arm': 'A',
                'text': '직업운을 살펴볼 때 참고할 점이 있어.\n'
                        '\n'
                        '명리학에서는 관성과 식상의 역할을 함께 해석해. 실제 이직은 근무 조건과 생활 여건도 고려해야 해.\n'
                        '\n'
                        '일할 때 안정과 성장 중 무엇이 더 중요해?\n'
                        '무료 사주풀이에 관심 있다면 궁금한 주제만 이야기해 줘. 개인 출생정보는 공개하지 않는 게 좋아.'},
 '2026-12-01': {'slot': 3,
                'arm': 'B',
                'text': '인연운은 만나는 시기만 중요할까?\n'
                        '\n'
                        '명리학에서는 배우자궁과 전체 흐름을 함께 봐. 현실에서는 대화와 존중이 중요해.\n'
                        '\n'
                        '관계에서 가장 소중하게 여기는 건 뭐야?\n'
                        '무료 사주풀이에 관심 있다면 궁금한 주제만 이야기해 줘. 개인 출생정보는 공개하지 않는 게 좋아.'},
 '2026-12-03': {'slot': 4,
                'arm': 'A',
                'text': '대운의 의미를 정리해 볼게.\n'
                        '\n'
                        '명리학에서 대운은 장기적인 흐름을 해석하는 틀이야. 실제 변화는 상황과 선택에 따라 달라.\n'
                        '\n'
                        '최근에 바꿔 보고 싶은 생활 습관이 있어?\n'
                        '무료 사주풀이에 관심 있다면 궁금한 주제만 이야기해 줘. 개인 출생정보는 공개하지 않는 게 좋아.'},
 '2026-12-06': {'slot': 5,
                'arm': 'A',
                'text': '열두 띠를 해석하는 기준이 있어.\n'
                        '\n'
                        '명리학에서는 태어난 해 외에도 월과 일, 시를 함께 해석해. 이런 해석은 가볍게 참고하는 것이 좋아.\n'
                        '\n'
                        '열두 띠 이야기에서 어떤 주제를 자주 읽어?\n'
                        '무료 사주풀이에 관심 있다면 궁금한 주제만 이야기해 줘. 개인 출생정보는 공개하지 않는 게 좋아.'},
 '2026-12-08': {'slot': 6,
                'arm': 'A',
                'text': '궁합을 해석할 때 살펴보는 점이 있어.\n'
                        '\n'
                        '명리학에서는 서로의 명식을 함께 살펴봐. 평소에는 서로의 말을 충분히 듣는 태도도 중요해.\n'
                        '\n'
                        '함께 지내며 중요하다고 느낀 태도는 뭐야?\n'
                        '무료 사주풀이에 관심 있다면 궁금한 주제만 이야기해 줘. 개인 출생정보는 공개하지 않는 게 좋아.'},
 '2026-12-10': {'slot': 7,
                'arm': 'B',
                'text': '신년운세를 읽고 어떤 계획부터 세우면 좋을까?\n'
                        '\n'
                        '명리학의 세운은 한 해를 돌아보는 참고 틀이야. 현실적인 목표와 실행 계획을 함께 세워 보는 것도 좋아.\n'
                        '\n'
                        '새해에 가장 먼저 정리하고 싶은 일은 뭐야?\n'
                        '무료 사주풀이에 관심 있다면 궁금한 주제만 이야기해 줘. 개인 출생정보는 공개하지 않는 게 좋아.'},
 '2026-12-13': {'slot': 8,
                'arm': 'B',
                'text': '오행이 골고루 있으면 좋은 명식일까?\n'
                        '\n'
                        '명리학에서는 오행의 개수보다 계절과 각 기운의 역할을 함께 해석해. 단순한 숫자로 사람을 평가할 수는 없어.\n'
                        '\n'
                        '오행을 공부할 때 어떤 부분이 가장 어렵게 느껴져?\n'
                        '무료 사주풀이에 관심 있다면 궁금한 주제만 이야기해 줘. 개인 출생정보는 공개하지 않는 게 좋아.'},
 '2026-12-15': {'slot': 9,
                'arm': 'A',
                'text': '일간은 명리학의 출발점이야.\n'
                        '\n'
                        '일간은 명식의 중심으로 읽는 기준이지만 주변 글자와의 관계에 따라 해석이 달라져.\n'
                        '\n'
                        '자신의 성향을 돌아보는 데 어떤 기준이 도움이 돼?\n'
                        '무료 사주풀이에 관심 있다면 궁금한 주제만 이야기해 줘. 개인 출생정보는 공개하지 않는 게 좋아.'},
 '2026-12-17': {'slot': 10,
                'arm': 'B',
                'text': '식상은 말솜씨만 뜻하는 걸까?\n'
                        '\n'
                        '명리학에서는 표현과 창작, 생각을 구체화하는 과정도 식상에 빗대어 해석해. 실제 역량은 경험과 연습으로 키울 수 있어.\n'
                        '\n'
                        '새롭게 배우고 싶은 표현이나 창작 활동이 있어?\n'
                        '무료 사주풀이에 관심 있다면 궁금한 주제만 이야기해 줘. 개인 출생정보는 공개하지 않는 게 좋아.'},
 '2026-12-20': {'slot': 11,
                'arm': 'B',
                'text': '인성이 있으면 공부가 저절로 잘될까?\n'
                        '\n'
                        '전통 명리에서는 배움과 도움을 받는 관계를 인성으로 설명하기도 해. 현실의 학습은 습관과 환경도 중요해.\n'
                        '\n'
                        '어떤 방식으로 배울 때 내용이 오래 기억돼?\n'
                        '무료 사주풀이에 관심 있다면 궁금한 주제만 이야기해 줘. 개인 출생정보는 공개하지 않는 게 좋아.'},
 '2026-12-22': {'slot': 12,
                'arm': 'A',
                'text': '비겁에 관한 해석을 소개할게.\n'
                        '\n'
                        '명리학에서는 비겁을 나와 비슷한 기운으로 보고 협력과 경쟁의 맥락을 함께 읽어. 실제 관계는 서로의 행동을 살펴야 해.\n'
                        '\n'
                        '혼자 일할 때와 함께 일할 때 어느 쪽이 더 편해?\n'
                        '무료 사주풀이에 관심 있다면 궁금한 주제만 이야기해 줘. 개인 출생정보는 공개하지 않는 게 좋아.'},
 '2026-12-24': {'slot': 13,
                'arm': 'B',
                'text': '태어난 계절은 명리에서 왜 중요할까?\n'
                        '\n'
                        '명리학에서는 월지를 계절의 기운을 살피는 출발점으로 활용해. 다른 글자와의 관계를 함께 해석하지.\n'
                        '\n'
                        '계절마다 생활 리듬이 달라진다고 느껴?\n'
                        '무료 사주풀이에 관심 있다면 궁금한 주제만 이야기해 줘. 개인 출생정보는 공개하지 않는 게 좋아.'},
 '2026-12-27': {'slot': 14,
                'arm': 'A',
                'text': '십신을 공부할 때 참고할 점이 있어.\n'
                        '\n'
                        '명리학에서는 일간과 다른 글자의 관계를 십신이라는 틀로 표현해. 개인의 삶을 단정하는 기준으로 쓰기보다는 해석의 참고로 보는 게 좋아.\n'
                        '\n'
                        '명리 용어 가운데 이해하기 어려웠던 말이 있어?\n'
                        '무료 사주풀이에 관심 있다면 궁금한 주제만 이야기해 줘. 개인 출생정보는 공개하지 않는 게 좋아.'}}

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
        text = item["text"]
    else:
        tid = template_id or scheduled_template_id(day)
        if tid not in TEMPLATES:
            raise ValueError(f"template_id must be 1..{len(TEMPLATES)}")
        text = TEMPLATES[tid]["text"]
    return text.rstrip() + "\n\n" + PRIVACY_NOTICE


def marker(day: dt.date, *, manual: bool, template_id: int, occasion: str = "") -> Path:
    if manual:
        stamp = kst_now().strftime("%Y-%m-%d_%H%M%S")
        suffix = f"_{occasion}" if occasion else f"_t{template_id}"
        return OUT / f"{stamp}_manual{suffix}.json"
    return OUT / f"{day.isoformat()}_scheduled.json"


def experiment_copy(day: dt.date, *, manual: bool, template_id: int, occasion: str) -> dict | None:
    # Experiment applies to existing scheduled slots only; manual dispatch stays separate.
    if manual or template_id or occasion:
        return None
    return HOOK_EXPERIMENT.get(day.isoformat())


def _normalized(text: str) -> str:
    return " ".join("".join(c if c.isalnum() else " " for c in unicodedata.normalize("NFKC", text).casefold()).split())


def verify_recent_copy(token: str, text: str) -> None:
    """Read only the verified account's recent posts. Fail closed, without logging tokens."""
    try:
        response = requests.get(
            f"{GRAPH}/me/threads",
            params={"fields": "id,text,timestamp", "limit": 50, "access_token": token},
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
    except Exception:
        raise SystemExit("[HOLD] Threads recent-post verification failed") from None
    if not isinstance(data, dict) or data.get("error") or not isinstance(data.get("data"), list):
        raise SystemExit("[HOLD] Threads recent-post verification unavailable")
    candidate = _normalized(text)
    if not candidate:
        raise SystemExit("[HOLD] empty candidate")
    for row in data["data"]:
        if not isinstance(row, dict) or not row.get("id"):
            raise SystemExit("[HOLD] invalid Threads recent-post record")
        recent = row.get("text")
        if recent is None:
            continue  # media-only post
        if not isinstance(recent, str):
            raise SystemExit("[HOLD] invalid recent-post text")
        norm = _normalized(recent)
        if norm and (norm == candidate or SequenceMatcher(None, candidate, norm).ratio() >= 0.88):
            raise SystemExit("[HOLD] similar recent Threads post already exists")


def publish(text: str) -> str:
    from zodiac_cardnews import _threads_uid

    tok = os.environ["THREADS_ACCESS_TOKEN"]
    uid = _threads_uid(tok)
    verify_recent_copy(tok, text)
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

    experiment = experiment_copy(day, manual=a.manual, template_id=a.template, occasion=a.occasion)
    if experiment:
        text = experiment["text"].rstrip() + "\n\n" + PRIVACY_NOTICE
        template_name = f"hook_experiment_{experiment['slot']}_{experiment['arm']}"
    else:
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
                "experiment_id": "THHOOK-PROMPT-20261126" if experiment else None,
                "experiment_arm": experiment["arm"] if experiment else None,
                "experiment_slot": experiment["slot"] if experiment else None,
                "copy_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
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
