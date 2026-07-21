# -*- coding: utf-8 -*-
"""스레드/인스타 첫댓글 훅 엔진 — 그날 일진 풀이 + 사주 흥미 이야기 (2026-07-16).

배경: 스레드는 '외부링크 댓글'을 스팸 신호로 보고 도달(노출)을 낮춘다.
그래서 사주포춘 링크는 '주 1회(일요일)'만 걸고, 월~토는 링크 없이
'그날 일진 풀이 + 사주 상식'으로 재미와 유익을 준다 → 댓글 참여↑ → 도달 유지.

핵심: 매일 일진(day_context)이 바뀌므로 같은 요일이어도 내용이 매일 다르다.
데이터는 전부 ganzhi_zodiac(KASI 만세력 교차검증)에서 나온 명리 사실.

톤: 전 연령(30대~시니어) 존댓말, 따뜻하고 품위 있게. 단정·과장 금지.
"""
from __future__ import annotations

import datetime as _dt

from ganzhi_zodiac import (
    BRANCH_ANIMAL, ELEM_COLOR, ELEM_DIR, ELEM_KO, ELEM_NUM,
    STEM_ELEM, BRANCH_ELEM, day_context, day_pillar, zodiac_day,
)

SITE = "sajufortune.kr"
ORDER = ["rat", "ox", "tiger", "rabbit", "dragon", "snake",
         "horse", "goat", "monkey", "rooster", "pig", "dog"]

# 한자 병기 (일진 풀이용)
STEM_HANJA = {"갑": "甲", "을": "乙", "병": "丙", "정": "丁", "무": "戊",
              "기": "己", "경": "庚", "신": "辛", "임": "壬", "계": "癸"}
BRANCH_HANJA = {"자": "子", "축": "丑", "인": "寅", "묘": "卯", "진": "辰", "사": "巳",
                "오": "午", "미": "未", "신": "申", "유": "酉", "술": "戌", "해": "亥"}

# 사주 재미 상식 풀 (금요일 — 주차로 순환)
FUN_FACTS = [
    ("'일진(日辰)'이 뭔가요? 🤔", "그날 하루의 간지예요. 같은 띠라도 날마다 운이 다른 건, 매일 일진이 바뀌기 때문이랍니다."),
    ("'삼합(三合)' 이야기 🍀", "신·자·진(원숭이·쥐·용)이 만나면 '물의 기운'으로 뭉쳐요. 서로 밀고 끌어주는 최고의 인연이라는 뜻이죠."),
    ("'충(沖)'은 나쁜 걸까요? ⚡", "충은 부딪힘이지만 '변화의 신호'이기도 해요. 자오충·묘유충처럼, 정면으로 만난 날엔 큰 결정을 하루 미루면 오히려 득이 됩니다."),
    ("십이지 순서의 유래 🐭", "옥황상제가 연 경주에서 부지런한 소 등에 몰래 탄 쥐가 결승선 직전 뛰어내려 1등을 했대요. 그래서 자·축·인… 쥐가 맨 앞이랍니다."),
    ("오행 상생 이야기 🌱", "나무는 불을 낳고(木生火), 불은 흙을, 흙은 쇠를, 쇠는 물을, 물은 다시 나무를 살려요. 세상이 서로 살려주며 돈다는 옛사람의 지혜죠."),
    ("'육합(六合)'이란 💞", "자축·인해처럼 두 지지가 다정하게 손잡는 관계예요. 이 기운의 날엔 협력·인연에서 반가운 일이 잘 생깁니다."),
    ("띠는 언제 바뀔까요? 🌸", "설날이 아니라 '입춘(2월 4일경)' 기준이에요. 명리에서 한 해의 시작은 봄이 열리는 입춘이거든요."),
    ("'삼재(三災)'가 궁금하다면 🌀", "12년마다 3년씩 드는 액운의 시기예요. 다만 '드는 해·머무는 해·나가는 해'가 다르고, 미리 알고 조심하면 무탈히 넘긴답니다."),
]


def _elem_of_day(ctx: dict) -> str:
    """그날의 대표 오행 — 지지(계절 기운) 기준."""
    return ctx["branch_elem"]


def _signs_by_tone(d: _dt.date) -> dict:
    """그날 일진 기준 12띠를 기조(tone)별로 분류 → {tone: [동물명...]}."""
    out = {}
    for slug in ORDER:
        r = zodiac_day(slug, d)
        if r:
            out.setdefault(r["tone"], []).append(r["animal"])
    return out


def _pillar_full(ctx: dict) -> str:
    """일진 한글+한자 (예: '정해일(丁亥日)')."""
    ds, db = ctx["day_stem"], ctx["day_branch"]
    return f"{ds}{db}일({STEM_HANJA[ds]}{BRANCH_HANJA[db]}日)"


# ───────── 요일별 훅 빌더 (월=0 … 토=5) ─────────

def _mon_iljin(ctx, d):
    """월: 오늘 일진 풀이."""
    se, be = ELEM_KO[ctx["stem_elem"]], ELEM_KO[ctx["branch_elem"]]
    return (f"오늘은 {_pillar_full(ctx)} 🔮\n"
            f"하늘 기운은 {se}({ctx['stem_elem']}), 땅 기운은 {be}({ctx['branch_elem']})가 자리한 날이에요.\n"
            f"두 기운의 결이 오늘 하루의 바탕이 됩니다. 서두르기보다 결을 따라가 보세요.\n"
            f"#오늘의일진 #사주 #띠별운세")


def _tue_best(ctx, d):
    """화: 오늘 순풍 탄 띠."""
    by = _signs_by_tone(d)
    good = (by.get("상승", []) + by.get("능동", []))[:4]
    good_s = "·".join(good) if good else "두루 무난한"
    return (f"오늘 순풍 탄 띠 🍀\n"
            f"{_pillar_full(ctx)} 기운과 잘 맞는 띠는 → {good_s}!\n"
            f"이 띠들은 오늘 사람·인연·협력에서 반가운 흐름이 따릅니다.\n"
            f"내 띠는 오늘 어떨까요? 🙂\n#띠별운세 #오늘의운세")


def _wed_care(ctx, d):
    """수: 오늘 살짝 조심할 띠."""
    by = _signs_by_tone(d)
    care = (by.get("주의", []) + by.get("신중", []))[:4]
    care_s = "·".join(care) if care else "특별히 없는 편이라 다행인"
    return (f"오늘 살짝 조심할 띠 🌫\n"
            f"{_pillar_full(ctx)}과 결이 어긋나기 쉬운 띠는 → {care_s}.\n"
            f"큰 결정·다툼은 한 박자 쉬어가고, 말을 아끼면 그것이 곧 복이 됩니다.\n"
            f"#오늘의운세 #사주")


def _thu_luck(ctx, d):
    """목: 오늘의 행운 정보 (오행 기반)."""
    el = _elem_of_day(ctx)
    return (f"오늘의 행운 열쇠 🗝\n"
            f"오늘은 {ELEM_KO[el]}({el})의 기운이 도는 날.\n"
            f"행운색 {ELEM_COLOR[el]} · 행운숫자 {ELEM_NUM[el]} · 행운방위 {ELEM_DIR[el]}!\n"
            f"작은 소품 하나로 하루의 기운을 살짝 바꿔보세요.\n#행운 #오늘의운세")


def _fri_fact(ctx, d):
    """금: 사주 재미 상식 (주차 순환)."""
    idx = d.isocalendar()[1] % len(FUN_FACTS)
    title, body = FUN_FACTS[idx]
    return (f"[사주 상식] {title}\n{body}\n"
            f"오늘도 좋은 기운 가득한 하루 보내세요 🙂\n#사주상식 #오늘의운세")


def _sat_join(ctx, d):
    """토: 가벼운 참여 유도."""
    return (f"오늘 당신의 띠는 어떤 하루일까요? 🔮\n"
            f"{_pillar_full(ctx)}—오늘 기운을 타고 나면 좋은 띠가 있고, 쉬어가면 좋은 띠가 있어요.\n"
            f"댓글에 '내 띠' 살짝 남겨주시면 서로 오늘 기운 나눠봐요 🙂\n#띠별운세")


def _sun_cta(ctx, d, channel):
    """일: '오늘의 운세·무료 사주' 프로필 유도 (URL 없음 — 쓰레드 도달 보호).
    쓰레드는 외부링크를 스팸 신호로 봐 노출을 낮추므로, 직접 URL 대신
    프로필에 걸린 홈페이지로만 유도한다. ('오늘의 운세' 키워드 강세 반영)"""
    if channel == "reels":
        return ("오늘 영상 속 내 띠, 진짜 내 사주로는 몇 점일까요? 🔮\n"
                "생년월일만 넣으면 '오늘의 운세'를 무료로 볼 수 있어요.\n"
                "👉 프로필 링크에서 무료로 확인하세요 🙂")
    return ("오늘 내 사주 점수는 몇 점일까요? 🔮\n"
            "생년월일만 넣으면 '오늘의 운세'를 무료로 볼 수 있어요.\n"
            "👉 프로필 링크에서 무료로 확인하세요 🙂")


def _sun_reels_nolink(ctx, d):
    """일요일 릴스: 주 1회 링크는 캐러셀에 양보 → 링크 없는 일진 훅."""
    return (f"오늘은 {_pillar_full(ctx)} 🔮\n"
            f"영상 속 12띠 흐름 중, 당신 띠는 어떤 하루인가요?\n"
            f"오늘도 결 따라 편안히 흘러가시길 바랍니다 🙂\n#띠별운세 #오늘의운세")


_WEEKDAY = [_mon_iljin, _tue_best, _wed_care, _thu_luck, _fri_fact, _sat_join]


def build_first_comment(date_iso: str, channel: str = "carousel") -> str:
    """그날 첫댓글 텍스트. 일요일=사주포춘 링크, 월~토=일진 풀이·사주 상식(링크 없음)."""
    d = _dt.date.fromisoformat(date_iso)
    ctx = day_context(d)
    wd = d.weekday()  # 0=월 … 6=일
    if wd == 6:
        # 주 1회 링크는 '캐러셀 일요일'에만. 릴스는 같은 날 링크 없이 일진 훅.
        return _sun_cta(ctx, d, channel) if channel == "carousel" else _sun_reels_nolink(ctx, d)
    return _WEEKDAY[wd](ctx, d)


if __name__ == "__main__":
    # 이번 주 7일치 미리보기
    import sys
    base = _dt.date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else _dt.date.today()
    monday = base - _dt.timedelta(days=base.weekday())
    names = ["월", "화", "수", "목", "금", "토", "일"]
    for i in range(7):
        day = monday + _dt.timedelta(days=i)
        print(f"\n===== {names[i]}요일 {day.isoformat()} ({day_pillar(day)}일) =====")
        print(build_first_comment(day.isoformat(), "carousel"))
