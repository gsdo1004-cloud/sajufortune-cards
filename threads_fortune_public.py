# -*- coding: utf-8 -*-
"""Threads 공개 사주풀이 라우터.

운영 원칙
- 이용자가 공개 댓글에 생년월일시를 직접 남기면 공개 간단풀이를 허용한다.
- 답글에서는 생년월일/출생시간을 다시 복사하지 않는다.
- 비공개 DM 풀이는 현재 보류한다. 공개 생년월일 입력만 정밀 공개풀이한다.
- 원문 생년정보는 상태 파일에 저장하지 않는다.
"""
from __future__ import annotations

import datetime as dt
import html
import re
from typing import Any

import requests
import zodiac_seo as zs

PREVIEW_URL = "https://sajufortune.kr/preview"

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
POLITE = ("요", "니다", "까요", "세요", "인가요", "합니다")

_DATE4 = re.compile(r"(?<!\d)((?:19|20)\d{2})[./-](\d{1,2})[./-](\d{1,2})(?!\d)")
_TIME_AMPM = re.compile(r"(오전|오후)\s*(\d{1,2})(?:\s*[:시]\s*(\d{1,2}))?\s*분?")
_TIME24 = re.compile(r"(?<!\d)([01]?\d|2[0-3])\s*:\s*([0-5]\d)(?!\d)")
_SIJIN_HOUR = {
    "자시": 0, "축시": 2, "인시": 4, "묘시": 6, "진시": 8, "사시": 10,
    "오시": 12, "미시": 14, "신시": 16, "유시": 18, "술시": 20, "해시": 22,
}


def has_birth_detail(text: str) -> bool:
    t = str(text or "")
    return bool(_DATE4.search(t) or "생년월일" in t or "출생시간" in t or "태어난 시간" in t)


def zodiac_slug(text: str) -> str | None:
    t = str(text or "").replace(" ", "")
    for slug, aliases in ZODIAC:
        for a in sorted(aliases, key=len, reverse=True):
            if a in t:
                return slug
    m = re.search(r"(?<!\d)((?:19|20)\d{2})(?!\d)", t)
    if m:
        year = int(m.group(1))
        return SLUGS[(year - 4) % 12]
    return None


def parse_birth_input(text: str) -> dict[str, Any] | None:
    """공개 댓글에서 계산에 필요한 값만 메모리에서 추출한다. 저장하지 않는다."""
    t = str(text or "")
    m = _DATE4.search(t)
    if not m:
        return None
    year, month, day = map(int, m.groups())
    try:
        dt.date(year, month, day)
    except ValueError:
        return None

    hour = minute = None
    ma = _TIME_AMPM.search(t)
    if ma:
        ap, hh, mm = ma.groups()
        hour = int(hh)
        minute = int(mm or 0)
        if not (1 <= hour <= 12 and 0 <= minute <= 59):
            hour = minute = None
        else:
            if ap == "오전":
                hour = 0 if hour == 12 else hour
            else:
                hour = 12 if hour == 12 else hour + 12
    if hour is None:
        mt = _TIME24.search(t)
        if mt:
            hour, minute = map(int, mt.groups())
    if hour is None:
        compact = t.replace(" ", "")
        for label, h in _SIJIN_HOUR.items():
            if label in compact:
                hour, minute = h, 0
                break

    cal = "leap" if "윤달" in t else ("lunar" if "음력" in t else "solar")
    return {
        "birth_date": f"{year:04d}-{month:02d}-{day:02d}",
        "birth_time": f"{hour:02d}:{minute:02d}" if hour is not None else "12:00",
        "time_known": hour is not None,
        "cal": cal,
    }


def _intent(text: str) -> tuple[str, str]:
    t = str(text or "")
    if any(k in t for k in ("재물", "금전", "돈", "수입", "사업", "사업운")):
        return "money", "재물·일"
    if any(k in t for k in ("연애", "궁합", "결혼", "재회", "인연")):
        return "love", "인연·가족"
    if any(k in t for k in ("건강", "몸", "컨디션")):
        return "health", "건강"
    if any(k in t for k in ("직장", "이직", "취업", "승진", "직업")):
        return "career", "직장"
    return "overall", "전체"


def _plain(s: str) -> str:
    t = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"\s+", " ", html.unescape(t)).strip()


def _short(s: str, limit: int = 56) -> str:
    t = re.sub(r"\s+", " ", str(s or "")).strip()
    if not t:
        return "지금은 서두르기보다 흐름을 한 번 더 확인하는 쪽이 좋아요."
    first = re.split(r"(?<=[.!?요다])\s+", t)[0].strip()
    if len(first) > limit:
        first = first[:limit].rstrip(" ,·") + "…"
    return first


def _preview_sections(birth: dict[str, Any]) -> dict[str, str]:
    """sajufortune.kr 정본 미리보기 엔진을 읽어 공개 간단풀이 재료만 가져온다."""
    r = requests.post(
        PREVIEW_URL,
        data={
            "name": "Threads",
            "birth_date": birth["birth_date"],
            "birth_time": birth["birth_time"],
            "cal": birth["cal"],
        },
        timeout=12,
        headers={"User-Agent": "sajufortune-threads-public/1.0"},
    )
    r.raise_for_status()
    page = r.text
    rows = re.findall(
        r'<div class="sec-title">\s*·\s*(.*?)\s*·\s*</div>\s*<p class="sec-text">(.*?)</p>',
        page,
        flags=re.S,
    )
    out = {_plain(k): _plain(v) for k, v in rows}
    day = re.search(r'<div class="day-pillar">(.*?)</div>', page, flags=re.S)
    if day:
        out["_day_pillar"] = _plain(day.group(1))
    return out


def _polite(text: str) -> bool:
    t = str(text or "").strip()
    return any(x in t for x in POLITE)


def _full_birth_reply(comment: str, birth: dict[str, Any]) -> str | None:
    """생년월일 공개 입력은 6줄 미니상담으로 답한다. 원문 개인정보는 재노출하지 않는다."""
    key, label = _intent(comment)
    try:
        sections = _preview_sections(birth)
    except Exception:
        return None

    nature = _short(sections.get("타고난 성품", ""), 72)
    now = _short(sections.get("2026년 흐름", ""), 72)
    money = _short(sections.get("재물·일", ""), 72)
    relation = _short(sections.get("인연·가족", ""), 68)
    action = _short(sections.get("개운법 한 가지", ""), 68)

    focused = {
        "money": money,
        "career": now or money,
        "love": relation,
        "health": action,
        "overall": now or nature,
    }.get(key, now or nature)

    time_line = (
        "• 출생시간까지 반영한 공개 미니풀이예요."
        if birth.get("time_known")
        else "• 출생시간 미입력이라 정오 기준 간단풀이예요."
    )
    lines = [
        "🔮 공개 미니사주",
        f"• 기본결: {nature}",
        f"• 지금흐름: {now}",
        f"• {label}: {focused}",
        f"• 관계/주변: {relation}",
        f"• 조언: {action}",
        time_line,
    ]
    # Threads 본문 한도 안에서 읽기 좋은 6~7줄을 유지한다.
    out = "\n".join(x for x in lines if x and not x.endswith(": "))
    return out[:470].rstrip()


def public_reply(comment: str, date_iso: str | None = None) -> str | None:
    """공개 댓글용 간단풀이. 생년정보는 답글에 재노출하지 않는다."""
    birth = parse_birth_input(comment)
    if birth:
        full = _full_birth_reply(comment, birth)
        if full:
            return full

    slug = zodiac_slug(comment)
    if not slug:
        return None

    d = date_iso or dt.date.today().isoformat()
    try:
        r = zs.make_reading(slug, d)
        field, label = _intent(comment)
        zfield = {"money": "money", "love": "love", "health": "health"}.get(field, "overall")
        body = _short(getattr(r, zfield, r.overall), 60)
        sign = r.sign_ko
    except Exception:
        sign = next((aliases[0] for s, aliases in ZODIAC if s == slug), "해당 띠")
        label = _intent(comment)[1]
        body = "지금은 서두르기보다 한 번 더 확인하고 움직이는 흐름이 좋아요."

    if _polite(comment):
        return f"{sign} {label} 흐름은 {body}"[:118].rstrip()
    return f"{sign} {label} 흐름은 {body}".replace("좋아요", "좋아")[:118].rstrip()
