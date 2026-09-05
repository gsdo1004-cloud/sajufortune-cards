# -*- coding: utf-8 -*-
"""Threads -> 프로필 -> 사주홈페이지 전환 문구 제어.

매 게시물이 광고처럼 보이면 대화/추천 도달이 죽는다. 그래서 채널+날짜를 고정 seed로
70% reach / 20% bridge / 10% conversion으로 배분한다. URL/DM 유도는 하지 않는다.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import re

PROFILE_RE = re.compile(r"^.*(?:프로필|무료로 볼 수|무료로 확인|사주 기준 흐름).*$", re.M)

BRIDGE = [
    "띠는 공통 흐름이고, 내 생년월일까지 넣으면 해석이 달라져. 궁금하면 프로필 첫 버튼에서 무료로 확인해봐.",
    "같은 띠라도 생년월일에 따라 결이 달라. 내 기준이 궁금하면 프로필에서 무료로 이어서 볼 수 있어.",
    "여기까지는 띠 기준. 내 사주 기준으로 이어서 보고 싶으면 프로필 첫 화면에서 무료로 확인해봐.",
]
CONVERT = [
    "방금 내용은 띠의 공통 흐름이야. 프로필에서 내 생년월일 기준 사주를 무료로 먼저 보고, 더 깊게 필요할 때만 1,000원 심층을 선택할 수 있어.",
    "내 사주로 보면 어디서 운이 풀리는지가 더 구체적이야. 프로필에서 무료 확인부터 하고, 필요할 때만 오늘 심층 1,000원을 보면 돼.",
]
REACH = [
    "너는 오늘 밀어붙이는 쪽이야, 한 번 지켜보는 쪽이야?",
    "오늘은 무엇을 먼저 챙길 건지 한마디만 남겨봐.",
    "비슷하게 느끼는 사람 있어, 아니면 전혀 다르게 느껴져?",
    "오늘 이 흐름에서 제일 신경 쓰이는 건 돈, 관계, 컨디션 중 뭐야?",
]


CHANNELS = ("ghost", "signal", "carousel")

def _h(text: str) -> int:
    return int(hashlib.sha256(text.encode()).hexdigest()[:8], 16)

def stage(channel: str, date_iso: str) -> str:
    """하루 3개 주요 게시물 중 정확히 1개만 프로필 유도를 넣는다.

    선택된 1개는 2/3 확률 bridge, 1/3 conversion이라 장기 평균은
    reach 66.7% / bridge 22.2% / conversion 11.1%다. 같은 날 광고 CTA가 겹치지 않는다.
    """
    chosen = CHANNELS[_h("promo|" + date_iso) % len(CHANNELS)]
    if channel != chosen:
        return "reach"
    return "conversion" if _h("stage|" + date_iso) % 3 == 0 else "bridge"

def cta(channel: str, date_iso: str, sign: str = "", focus: str = "") -> str:
    st=stage(channel,date_iso)
    seed=int(hashlib.sha256(f"{channel}|{date_iso}|{sign}|{focus}".encode()).hexdigest()[:8],16)
    pool=CONVERT if st=="conversion" else BRIDGE if st=="bridge" else REACH
    return pool[seed % len(pool)]


def apply(text: str, channel: str, date_iso: str, sign: str = "", focus: str = "") -> str:
    """기존 반복 프로필 문구를 제거하고 해당 날짜의 퍼널 단계 CTA 하나만 붙인다."""
    clean=PROFILE_RE.sub("", text or "")
    clean=re.sub(r"\n{3,}","\n\n",clean).strip()
    line=cta(channel,date_iso,sign,focus)
    # reach 글이 이미 질문으로 끝나면 질문 중복을 피한다.
    if stage(channel,date_iso)=="reach" and clean.endswith("?"):
        return clean
    return f"{clean}\n\n{line}".strip()

TOPIC_TAGS = {
    "ghost": ("오늘의 운세", "사주"),
    "signal": ("띠별 운세", "사주"),
    "carousel": ("오늘의 운세", "띠별 운세", "사주"),
}

def topic_tag(channel: str, date_iso: str) -> str:
    """Threads 공식 topic_tag용 주제. API가 거절하면 발행 코드가 무태그로 재시도한다."""
    pool = TOPIC_TAGS.get(channel) or ("사주",)
    return pool[_h(f"topic|{channel}|{date_iso}") % len(pool)]
