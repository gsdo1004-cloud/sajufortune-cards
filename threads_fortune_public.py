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


def _natural_year_note(y: dict[str, Any] | None) -> tuple[str, str, list[str]]:
    if not y:
        return "", "", []
    ko = str(y.get("ko") or y.get("ganji") or "")
    sg = str(y.get("stem_ten_god") or "")
    bg = str(y.get("branch_ten_god") or "")
    kinds = [INTERACTION_KO.get(str(x), str(x)) for x in (y.get("interaction_kinds") or [])]
    return ko, "·".join(x for x in (sg, bg) if x), kinds


def _specific_reply(comment: str, birth: dict[str, Any], facts: dict[str, Any]) -> str:
    """질문한 한 분야만, 사람 상담처럼 자연스럽고 구체적으로 답한다."""
    key, _label = _intent(comment)
    chart = facts.get("chart") or {}
    adv = facts.get("advanced") or {}
    dw = facts.get("current_daewoon") or {}
    wealth = facts.get("wealth") or {}
    love = facts.get("love") or {}
    precise = bool(birth.get("time_known"))

    cy_ko, cy_gods, cy_kinds = _natural_year_note(facts.get("current_year"))
    ny_ko, ny_gods, ny_kinds = _natural_year_note(facts.get("next_year"))
    dw_name = str(dw.get("ko") or dw.get("ganji") or "")
    y1, y2 = dw.get("year_from"), dw.get("year_to")

    parts: list[str] = []

    if key == "money":
        wc = int(wealth.get("chart_count") or 0)
        yrs = [str(x.get("year")) for x in (wealth.get("sewoon_years") or []) if x.get("year")]
        if precise:
            parts.append(
                f"재물운만 보면, 원국에 재성이 {wc}곳 잡혀 있어서 돈 흐름이 아예 약한 사주는 아니에요."
                if wc > 0 else
                "재물운만 보면, 원국에서 재성이 전면에 드러나는 구조는 아니라 돈은 한 번에 크게 잡기보다 흐름을 만들어가는 쪽이 맞아요."
            )
        else:
            parts.append("재물운만 볼게요. 출생시간이 없어서 시주는 빼고, 연·월·일 기준으로 돈 흐름만 보겠습니다.")
        if cy_gods:
            meaning = TEN_GOD_MEANING.get(str((facts.get("current_year") or {}).get("stem_ten_god") or ""), "")
            action = "수입·계약·현금흐름을 실제 숫자로 챙길수록 유리해요" if "정재" in cy_gods else (
                "사업·거래·새로운 돈길은 생기지만 지출도 같이 커질 수 있어요" if "편재" in cy_gods else
                "돈 자체보다 일의 변화가 먼저 움직이고 그 뒤에 수입이 따라오는 흐름이에요"
            )
            parts.append(f"올해 {cy_ko}에는 {cy_gods}가 들어와서 {meaning or '재물 쪽 움직임'}이 두드러지고, {action}.")
        if yrs:
            future = [y for y in yrs if y not in {"2026"}]
            if future:
                parts.append(f"특히 다음 재성 흐름은 {', '.join(future[:2])}년에 다시 잡히니, 지금은 무리하게 크게 벌리기보다 그때까지 돈 되는 구조를 만들어두는 게 좋아요.")

    elif key == "career":
        parts.append("직장운만 보면, 지금은 버티는 것보다 자리와 역할을 다시 고르는 흐름이 더 강합니다.")
        if dw_name:
            span = f" {y1}~{y2}년" if y1 and y2 else ""
            parts.append(f"현재 {dw_name} 대운{span}이라 직업 방향을 바꾸거나 일의 성격이 달라지는 변화가 한 번 크게 들어올 수 있어요.")
        if cy_gods:
            meaning = TEN_GOD_MEANING.get(str((facts.get("current_year") or {}).get("stem_ten_god") or ""), "")
            inter = f" 여기에 원국과 {'·'.join(cy_kinds)} 작용까지 있어서" if cy_kinds else ""
            parts.append(f"올해 {cy_ko}에는 {cy_gods}가 잡혀 {meaning or '직장·조직 문제'}가 전면에 나오고,{inter} 제안이 오면 조건만 보지 말고 자리의 지속성까지 같이 보는 게 맞아요.")
        if ny_gods:
            parts.append(f"내년 {ny_ko}는 {ny_gods}로 흐름이 바뀌니, 올해 안에 이동할지 남을지 윤곽이 잡히는 편입니다.")

    elif key == "love":
        dohwa = str(love.get("dohwa") or "")
        cheonul = "·".join(str(x) for x in (love.get("cheonul") or []))
        hap = str(love.get("hap") or "")
        chung = str(love.get("chung") or "")
        parts.append("인연운만 보면, 그냥 '사람이 들어온다'보다 관계가 들어오는 방식이 분명한 편이에요.")
        bits = []
        if dohwa:
            bits.append(f"도화가 {dohwa}로 잡혀 사람 눈에 띄는 시기가 오면 인연이 빨리 붙는 편")
        if cheonul:
            bits.append(f"천을귀인이 {cheonul}이라 소개나 주변 사람을 통한 연결이 잘 맞는 편")
        if bits:
            parts.append("그리고 " + ", ".join(bits) + "이에요.")
        if hap or chung:
            txt = []
            if hap: txt.append(f"{hap} 쪽 합이 들어올 때는 관계가 가까워지고")
            if chung: txt.append(f"{chung} 쪽 충이 강해질 때는 감정이 급하게 흔들릴 수 있어요")
            parts.append("반대로 " + ", ".join(txt) + ".")
        yrs = [str(x.get("year")) for x in (love.get("sewoon_years") or []) if x.get("year")]
        if yrs:
            parts.append(f"시기로 보면 {', '.join(yrs[:3])}년이 인연 변화가 크게 잡히는 해라, 그때 들어오는 사람이나 관계 변화는 그냥 지나치지 않는 게 좋아요.")

    elif key == "health":
        parts.append("건강운만 보면, 병을 찍는 식으로 보지는 않고 과로가 몰리는 시기와 생활리듬이 흔들리는 때만 보겠습니다.")
        if cy_gods:
            pressure = "책임과 압박이 늘어 몸이 먼저 지치기 쉬운 해" if any(x in cy_gods for x in ("편관", "정관")) else (
                "활동량이 늘고 쉬는 타이밍을 놓치기 쉬운 해" if any(x in cy_gods for x in ("식신", "상관")) else
                "생활패턴이 들쑥날쑥해지기 쉬운 해"
            )
            parts.append(f"올해 {cy_ko} 흐름은 {pressure}라 수면과 식사 시간을 무너뜨리지 않는 게 가장 중요해요.")
        if ny_gods:
            parts.append(f"내년 {ny_ko}에는 흐름이 한 번 바뀌니, 올해부터 무리하는 습관만 줄여도 체감 차이가 꽤 납니다.")

    else:
        dm = f"{chart.get('day_master','')}{chart.get('day_master_element','')}"
        top = _fmt_gods(adv.get("top_ten_gods") or []) if precise else ""
        parts.append(f"전체운으로 보면 {dm} 일간이고" + (f", {top} 기운이 강하게 잡혀" if top else "") + " 한 번 방향을 잡으면 밀고 가는 힘이 있는 편이에요.")
        if dw_name:
            parts.append(f"지금 {dw_name} 대운에 들어와 있어서 예전 방식 그대로 버티기보다 일·돈·관계 중 하나는 구조를 바꾸는 흐름이 강합니다.")
        if cy_ko:
            inter = f" 원국과 {'·'.join(cy_kinds)}가 걸려" if cy_kinds else ""
            parts.append(f"올해 {cy_ko}는{inter} 선택을 미루기보다 정리하고 방향을 잡는 쪽이 낫고, 내년 {ny_ko or '다음 해'}에는 그 선택의 결과가 더 선명해지는 흐름이에요.")

    if not precise and key not in {"money"}:
        parts.append("태어난 시간을 알면 시주까지 넣어서 시기를 더 좁혀볼 수 있어요.")

    # Threads 댓글처럼 짧은 문단 2~4개만. 기술 라벨·불릿·면책문구는 넣지 않는다.
    return "\n\n".join(p.strip() for p in parts if p.strip())[:470].rstrip()



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
    """생년월일 공개 입력은 질문한 분야만 자연스러운 Threads 문장으로 상세풀이."""
    try:
        facts = _structured_facts(birth)
        return _specific_reply(comment, birth, facts)
    except Exception:
        pass

    # 정밀엔진이 잠시 안 될 때도 질문한 분야만 자연스럽게 답한다.
    key, label = _intent(comment)
    try:
        sections = _preview_sections(birth)
    except Exception:
        return None
    focused = {
        "money": sections.get("재물·일", ""),
        "career": sections.get("2026년 흐름", "") or sections.get("재물·일", ""),
        "love": sections.get("인연·가족", ""),
        "health": sections.get("개운법 한 가지", ""),
        "overall": sections.get("2026년 흐름", "") or sections.get("타고난 성품", ""),
    }.get(key, "")
    body = _short(focused, 210)
    if not body:
        return None
    prefix = {
        "money": "재물운만 보면, ",
        "career": "직장운만 보면, ",
        "love": "인연운만 보면, ",
        "health": "건강 흐름만 보면, ",
        "overall": "",
    }.get(key, "")
    suffix = "" if birth.get("time_known") else " 태어난 시간이 없어서 시주는 빼고 봤어요."
    return (prefix + body + suffix)[:470].rstrip()

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
