# -*- coding: utf-8 -*-
"""Threads 공개 띠풀이 라우터.

공개 댓글에는 띠/출생연도 + 고민만 받아 짧은 띠풀이를 돌려준다.
생년월일/출생시간이 보이면 절대 되풀이하지 않고 비공개 DM 입력으로 유도한다.
개인 사주 정밀풀이용 입력은 이 모듈에서 저장하지 않는다.
"""
from __future__ import annotations

import datetime as dt
import re

import zodiac_seo as zs

ZODIAC = [
    ("rat", ("쥐띠", "쥐")),
    ("ox", ("소띠", "소")),
    ("tiger", ("호랑이띠", "범띠", "호랑이", "범")),
    ("rabbit", ("토끼띠", "토끼")),
    ("dragon", ("용띠", "용")),
    ("snake", ("뱀띠", "뱀")),
    ("horse", ("말띠", "말")),
    ("goat", ("양띠", "양")),
    ("monkey", ("원숭이띠", "원숭이")),
    ("rooster", ("닭띠", "닭")),
    ("dog", ("개띠", "개")),
    ("pig", ("돼지띠", "돼지")),
]
SLUGS = [x[0] for x in ZODIAC]

PRIVATE_BIRTH_PATTERNS = (
    r"\b(?:19|20)\d{2}[./-]\d{1,2}[./-]\d{1,2}\b",
    r"\b\d{2}[./-]\d{1,2}[./-]\d{1,2}\b",
    r"\b\d{6}\b",
    r"생년\s*월일",
    r"출생\s*시간",
    r"태어난\s*시간",
    r"(?:오전|오후)\s*\d{1,2}(?::\d{1,2})?",
)
POLITE = ("요", "니다", "까요", "세요", "인가요", "합니다")


def has_private_birth_data(text: str) -> bool:
    t = str(text or "")
    return any(re.search(p, t, re.I) for p in PRIVATE_BIRTH_PATTERNS)


def zodiac_slug(text: str) -> str | None:
    t = str(text or "").replace(" ", "")
    # 긴 별칭부터 매칭해 단일 글자 오탐을 줄인다.
    for slug, aliases in ZODIAC:
        for a in sorted(aliases, key=len, reverse=True):
            if a in t:
                return slug
    # 연도만 적은 댓글도 띠로 연결. 날짜 전체가 있어도 연도만 계산에 쓰고 공개로 되풀이하지 않는다.
    m = re.search(r"(?<!\d)((?:19|20)\d{2})(?!\d)", t)
    if m:
        year = int(m.group(1))
        return SLUGS[(year - 4) % 12]
    return None


def _intent(text: str) -> tuple[str, str]:
    t = str(text or "")
    if any(k in t for k in ("재물", "금전", "돈", "수입", "사업", "사업운")):
        return "money", "재물"
    if any(k in t for k in ("연애", "궁합", "결혼", "재회", "인연")):
        return "love", "연애"
    if any(k in t for k in ("건강", "몸", "컨디션")):
        return "health", "건강"
    if any(k in t for k in ("직장", "이직", "취업", "승진", "직업")):
        return "overall", "직장"
    return "overall", "전체"


def _short(s: str, limit: int = 58) -> str:
    t = re.sub(r"\s+", " ", str(s or "")).strip()
    if not t:
        return "지금은 큰 결정보다 흐름을 한 번 더 확인하는 쪽이 좋아."
    first = re.split(r"(?<=[.!?요다])\s+", t)[0].strip()
    if len(first) > limit:
        first = first[:limit].rstrip(" ,·") + "…"
    return first


def _polite(text: str) -> bool:
    t = str(text or "").strip()
    return any(x in t for x in POLITE)


def public_reply(comment: str, date_iso: str | None = None) -> str | None:
    """띠/연도 댓글이면 공개용 짧은 풀이를 반환. 일반 댓글은 None."""
    slug = zodiac_slug(comment)
    private = has_private_birth_data(comment)
    if not slug and not private:
        return None

    polite = _polite(comment)
    if private and not slug:
        return (
            "생년월일·출생시간은 공개 댓글에 남기지 마세요. 인스타 DM으로 보내주시면 비공개로 볼게요."
            if polite else
            "생년월일·출생시간은 공개 댓글에 쓰지 마. 인스타 DM으로 보내면 비공개로 볼게."
        )

    d = date_iso or dt.date.today().isoformat()
    try:
        r = zs.make_reading(slug, d)
        field, label = _intent(comment)
        body = _short(getattr(r, field, r.overall))
        sign = r.sign_ko
    except Exception:
        sign = next((aliases[0] for s, aliases in ZODIAC if s == slug), "해당 띠")
        label = _intent(comment)[1]
        body = "지금은 서두르기보다 한 번 더 확인하고 움직이는 흐름이 좋아."

    if private:
        if polite:
            return f"{sign} {label} 흐름은 {body} 생년월일시는 공개하지 말고 인스타 DM으로 보내주세요."
        return f"{sign} {label} 흐름은 {body} 생년월일시는 공개 말고 인스타 DM으로 보내줘."

    if polite:
        return f"{sign} {label} 흐름은 {body} 개인 생년월일시는 인스타 DM으로 보내주세요."
    return f"{sign} {label} 흐름은 {body} 개인 생년월일시는 인스타 DM으로 보내줘."
