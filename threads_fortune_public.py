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
MINI_API_URL = "https://sajufortune.kr/api/public-saju-mini"

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
_DATE2 = re.compile(r"(?<!\d)(\d{2})[./-](\d{1,2})[./-](\d{1,2})(?!\d)")
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
    if m:
        year, month, day = map(int, m.groups())
    else:
        m2 = _DATE2.search(t)
        if not m2:
            return None
        yy, month, day = map(int, m2.groups())
        year = 2000 + yy if yy <= (dt.date.today().year % 100) else 1900 + yy
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
    compact = t.replace(" ", "").lower()
    gender = "F" if any(x in compact for x in ("여자", "여성", "female")) else "M"
    if any(x in compact for x in ("남자", "남성", "male")):
        gender = "M"
    return {
        "birth_date": f"{year:04d}-{month:02d}-{day:02d}",
        "birth_time": f"{hour:02d}:{minute:02d}" if hour is not None else "12:00",
        "time_known": hour is not None,
        "cal": cal,
        "gender": gender,
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


def _structured_facts(birth: dict[str, Any]) -> dict[str, Any]:
    """정본 사주엔진의 구조화 계산 결과. 실패하면 상위에서 기존 preview로 폴백한다."""
    r = requests.post(
        MINI_API_URL,
        json={
            "birth_date": birth["birth_date"],
            "birth_time": birth["birth_time"],
            "time_known": birth["time_known"],
            "cal": birth["cal"],
            "gender": birth.get("gender", "M"),
        },
        timeout=15,
        headers={"User-Agent": "sajufortune-threads-public/2.0"},
    )
    r.raise_for_status()
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError("mini api returned not-ok")
    return data


TEN_GOD_MEANING = {
    "비견": "자기주도·동료·경쟁",
    "겁재": "경쟁·분배·지출",
    "식신": "실무·생산·꾸준한 성과",
    "상관": "표현·변화·기존 틀 재조정",
    "편재": "사업·거래·유동 재물",
    "정재": "고정수입·계약·재정관리",
    "편관": "책임·압박·직무 변화",
    "정관": "직위·조직·규정·문서",
    "편인": "전문성·비정형 학습·전환",
    "정인": "문서·자격·지원·학습",
}

INTERACTION_KO = {
    "chung": "충",
    "hap": "합",
    "yukhap": "육합",
    "samhap": "삼합",
    "banhap": "반합",
    "hyeong": "형",
    "pa": "파",
    "hae": "해",
}


def _fmt_gods(rows: list[dict[str, Any]]) -> str:
    out = []
    for row in rows[:2]:
        name = str(row.get("name") or "")
        if name:
            out.append(name)
    return "·".join(out)


def _year_line(label: str, y: dict[str, Any] | None) -> str:
    if not y:
        return ""
    gj = str(y.get("ko") or y.get("ganji") or "")
    sg = str(y.get("stem_ten_god") or "")
    bg = str(y.get("branch_ten_god") or "")
    gods = "·".join(x for x in (sg, bg) if x)
    meaning = TEN_GOD_MEANING.get(sg, "")
    interactions = [
        INTERACTION_KO.get(str(x), str(x))
        for x in (y.get("interaction_kinds") or [])
    ]
    tail = f", 원국과 {'·'.join(interactions)} 작용" if interactions else ""
    mid = f"{gods}({meaning})" if gods and meaning else gods
    return f"• {label}: {gj} — {mid}{tail}".rstrip(" —")


def _specific_reply(comment: str, birth: dict[str, Any], facts: dict[str, Any]) -> str:
    key, label = _intent(comment)
    chart = facts.get("chart") or {}
    adv = facts.get("advanced") or {}
    dw = facts.get("current_daewoon") or {}
    wealth = facts.get("wealth") or {}
    love = facts.get("love") or {}

    pillars = " ".join(
        x for x in (chart.get("year"), chart.get("month"), chart.get("day"), chart.get("hour")) if x
    )
    dm = f"{chart.get('day_master','')}{chart.get('day_master_element','')}"
    strength = str(adv.get("strength") or "")
    ratio = adv.get("strength_ratio")
    strength_s = f"{strength} {ratio:.0f}%" if isinstance(ratio, (int, float)) else strength
    top = _fmt_gods(adv.get("top_ten_gods") or [])

    lines = [
        "🔮 공개 사주 정밀풀이",
        f"• 명식: {pillars} / 일간 {dm}" + (f" / {strength_s}" if strength_s else ""),
    ]
    if top:
        lines.append(f"• 핵심십성: {top} — 원국에서 반복해서 작동하는 성향입니다.")

    if dw:
        dw_name = str(dw.get("ko") or dw.get("ganji") or "")
        y1, y2 = dw.get("year_from"), dw.get("year_to")
        lines.append(f"• 현재대운: {dw_name}" + (f" ({y1}~{y2})" if y1 and y2 else ""))

    cy = _year_line("2026 세운", facts.get("current_year"))
    ny = _year_line("2027 세운", facts.get("next_year"))
    if cy:
        lines.append(cy)

    # 질문별로 실제 계산값을 한 줄 더 붙인다.
    if key == "money":
        wc = int(wealth.get("chart_count") or 0)
        we = str(wealth.get("wealth_element") or "")
        yrs = [str(x.get("year")) for x in (wealth.get("sewoon_years") or []) if x.get("year")]
        lines.append(
            f"• 재물근거: 원국 재성 {wc}곳" + (f", 재성 오행은 {we}" if we else "")
            + (f"; 재성이 다시 강해지는 해 {', '.join(yrs[:3])}" if yrs else "")
        )
    elif key == "love":
        dohwa = str(love.get("dohwa") or "")
        ch = "·".join(str(x) for x in (love.get("cheonul") or []))
        hap = str(love.get("hap") or "")
        chung = str(love.get("chung") or "")
        bits = []
        if dohwa: bits.append(f"도화 {dohwa}")
        if ch: bits.append(f"천을귀인 {ch}")
        if hap: bits.append(f"일지합 {hap}")
        if chung: bits.append(f"일지충 {chung}")
        if bits:
            lines.append("• 인연근거: " + " / ".join(bits))
    elif key == "career":
        cyg = (facts.get("current_year") or {}).get("stem_ten_god") or ""
        meaning = TEN_GOD_MEANING.get(str(cyg), "")
        if cyg:
            lines.append(f"• 직장포인트: 올해 천간 십성은 {cyg} — {meaning} 이슈가 전면에 옵니다.")
    elif key == "health":
        lines.append("• 건강질문은 질병 예측 대신 생활리듬·과로 여부 참고 수준으로만 봅니다.")

    if ny:
        lines.append(ny)

    if not birth.get("time_known"):
        lines.append("• 출생시간이 없어 시주를 뺀 부분풀이입니다. 시간까지 알면 정확도가 더 올라갑니다.")

    lines.append("※ 명리 계산 근거를 보여드리는 참고용 풀이이며 결과를 단정하지 않습니다.")
    return "\n".join(lines)[:470].rstrip()


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
    """생년월일 공개 입력은 명식·십성·대운·세운 근거를 보여주는 정밀 공개풀이."""
    try:
        facts = _structured_facts(birth)
        return _specific_reply(comment, birth, facts)
    except Exception:
        pass

    # 배포 전/일시 장애에는 기존 preview 엔진으로 폴백하되, 두루뭉실함을 숨기지 않는다.
    key, label = _intent(comment)
    try:
        sections = _preview_sections(birth)
    except Exception:
        return None
    day = sections.get("_day_pillar", "")
    focused = {
        "money": sections.get("재물·일", ""),
        "career": sections.get("2026년 흐름", "") or sections.get("재물·일", ""),
        "love": sections.get("인연·가족", ""),
        "health": sections.get("개운법 한 가지", ""),
        "overall": sections.get("2026년 흐름", "") or sections.get("타고난 성품", ""),
    }.get(key, "")
    nature = sections.get("타고난 성품", "")
    lines = [
        "🔮 공개 사주 간단풀이",
        f"• 일주: {day}" if day else "",
        f"• 기본결: {_short(nature, 78)}" if nature else "",
        f"• {label}: {_short(focused, 92)}" if focused else "",
    ]
    if not birth.get("time_known"):
        lines.append("• 출생시간이 없어 시주 제외 부분풀이입니다.")
    lines.append("※ 정밀엔진 연결 전에는 단정하지 않고 확인 가능한 범위만 풀이합니다.")
    return "\n".join(x for x in lines if x)[:470].rstrip()

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
