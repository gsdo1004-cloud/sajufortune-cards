"""띠별 일일운세용 간지(일진) 계산 + 12띠 관계·기조 판정 (2026-07-11).

문제: zodiac_seo(웹 카드뉴스/SEO)·toss_free(토스 무료훅)의 띠별운세가 그날 간지와
무관하게 sha256 해시로 문장 풀에서 랜덤 추출 → "쥐띠 오늘의 운세"가 명리 근거 없음.
해법: 그날 일진 지지를 계산하고, 각 띠와의 전통 관계(충·합·삼합·형·파·해·오행 상생상극)로
'기조(tone)'를 판정 → 운세 문장 풀 분기 + 점수 편향 + 행운요소를 오행에서 도출.

일진 계산은 율리우스적일(JDN) 산술 공식 — 외부 의존성 0, KASI 만세력과 교차검증 완료
(2026-07-12=정해일, 2024-01-01=갑자일, 2000-01-01=무오일). toss_unse는 sajupy로
개인 사주에 일진을 대입하지만, 여기는 LLM 없는 풀 기반이라 지지 관계만으로 충분하다.

기조(tone) 5종: 상승 / 능동 / 평온 / 신중 / 주의
"""
from __future__ import annotations

import datetime as _dt

BRANCHES = "자축인묘진사오미신유술해"
BRANCH_ANIMAL = {"자": "쥐", "축": "소", "인": "호랑이", "묘": "토끼", "진": "용", "사": "뱀",
                 "오": "말", "미": "양", "신": "원숭이", "유": "닭", "술": "개", "해": "돼지"}
BRANCH_ELEM = {"자": "수", "축": "토", "인": "목", "묘": "목", "진": "토", "사": "화",
               "오": "화", "미": "토", "신": "금", "유": "금", "술": "토", "해": "수"}
STEMS = "갑을병정무기경신임계"
STEM_ELEM = {"갑": "목", "을": "목", "병": "화", "정": "화", "무": "토",
             "기": "토", "경": "금", "신": "금", "임": "수", "계": "수"}

SAENG = {"목": "화", "화": "토", "토": "금", "금": "수", "수": "목"}  # A생B
GEUK = {"목": "토", "토": "수", "수": "화", "화": "금", "금": "목"}    # A극B

# slug(영문)·한글 → 지지
SLUG_TO_BRANCH = {"rat": "자", "ox": "축", "tiger": "인", "rabbit": "묘", "dragon": "진",
                  "snake": "사", "horse": "오", "goat": "미", "monkey": "신",
                  "rooster": "유", "dog": "술", "pig": "해"}
KO_TO_BRANCH = {v: k for k, v in {b: BRANCH_ANIMAL[b] for b in BRANCHES}.items()}

# 지지 관계표
CHUNG = {"자": "오", "오": "자", "축": "미", "미": "축", "인": "신", "신": "인",
         "묘": "유", "유": "묘", "진": "술", "술": "진", "사": "해", "해": "사"}
YUKHAP = {"자": "축", "축": "자", "인": "해", "해": "인", "묘": "술", "술": "묘",
          "진": "유", "유": "진", "사": "신", "신": "사", "오": "미", "미": "오"}
SAMHAP = [set("신자진"), set("사유축"), set("인오술"), set("해묘미")]
HYUNG_GROUPS = [set("인사신"), set("축술미")]
SANG_HYUNG = {"자", "묘"}
JA_HYUNG = set("진오유해")
PA = {"자": "유", "유": "자", "축": "진", "진": "축", "인": "해", "해": "인",
      "묘": "오", "오": "묘", "사": "신", "신": "사", "술": "미", "미": "술"}
HAE = {"자": "미", "미": "자", "축": "오", "오": "축", "인": "사", "사": "인",
       "묘": "진", "진": "묘", "신": "해", "해": "신", "유": "술", "술": "유"}

# 오행 → 행운요소 (하도수·오방색·오방위)
ELEM_NUM = {"수": "1, 6", "화": "2, 7", "목": "3, 8", "금": "4, 9", "토": "5, 10"}
ELEM_COLOR = {"목": "초록·청색", "화": "붉은색", "토": "노란색", "금": "흰색", "수": "남색"}
ELEM_DIR = {"목": "동쪽", "화": "남쪽", "토": "중앙", "금": "서쪽", "수": "북쪽"}
ELEM_KO = {"목": "나무", "화": "불", "토": "흙", "금": "쇠", "수": "물"}

# 기조 → 점수 범위(0~100) · 별점(1~5)
TONE_SCORE = {
    "상승": (82, 93), "능동": (74, 85), "평온": (70, 80), "신중": (62, 73), "주의": (58, 69),
}
TONE_STARS = {"상승": 5, "능동": 4, "평온": 4, "신중": 3, "주의": 3}


def _jdn(y: int, m: int, d: int) -> int:
    a = (14 - m) // 12
    yy = y + 4800 - a
    mm = m + 12 * a - 3
    return d + (153 * mm + 2) // 5 + 365 * yy + yy // 4 - yy // 100 + yy // 400 - 32045


def day_pillar(dt: _dt.date) -> str:
    """일진 2글자 (예: '정해'). JDN 산술 — 의존성 0."""
    i = (_jdn(dt.year, dt.month, dt.day) + 49) % 60
    return STEMS[i % 10] + BRANCHES[i % 12]


def _generator_elem(elem: str) -> str:
    """elem을 낳아주는(생하는) 오행 — 부족한 기운 보충용."""
    return next(k for k, v in SAENG.items() if v == elem)


def to_branch(sign) -> str | None:
    """slug('rat')·한글('쥐')·지지('자')·출생연도('1990')·인덱스(0~11) → 지지 1글자."""
    s = str(sign).strip()
    if s in BRANCHES:
        return s
    if s in SLUG_TO_BRANCH:
        return SLUG_TO_BRANCH[s]
    if s in KO_TO_BRANCH:
        return KO_TO_BRANCH[s]
    if s.isdigit():
        n = int(s)
        if 0 <= n <= 11:
            return BRANCHES[n]
        if n >= 1900:
            return BRANCHES[(n - 4) % 12]
    return None


def zodiac_relation(day_branch: str, zodiac_branch: str) -> dict:
    """띠 지지와 오늘 일진 지지의 관계 → 기조·리드문장·행운오행.

    우선순위: 동지지 > 충 > 육합 > 삼합 > 형 > 파 > 해 > 오행 상생상극.
    행운오행: 기조가 좋으면(상승) 순응해 자기 오행 강화, 나쁘면(신중·주의) 생조 오행으로 보충.
    """
    d_el, z_el = BRANCH_ELEM[day_branch], BRANCH_ELEM[zodiac_branch]
    boch = _generator_elem(z_el)  # 띠를 생해주는 오행

    if zodiac_branch == day_branch:
        if zodiac_branch in JA_HYUNG:
            return _r("주의", "오늘 기운과 같은 지지라 힘이 몰리는 날 — 스스로를 몰아세우기 쉬우니 여유를", boch)
        return _r("상승", "오늘의 주인공 기운을 타고난 날 — 존재감이 드러나고 하는 일에 힘이 실립니다", z_el)
    if CHUNG[day_branch] == zodiac_branch:
        return _r("신중", "오늘 기운과 정면으로 부딪히는 날 — 큰 결정이나 다툼은 한 박자 쉬어가면 오히려 득", boch)
    if YUKHAP[day_branch] == zodiac_branch:
        return _r("상승", "오늘 기운과 다정하게 손잡는 날 — 사람·인연·협력에서 좋은 일이 따릅니다", z_el)
    for g in SAMHAP:
        if day_branch in g and zodiac_branch in g:
            return _r("상승", "오늘 기운과 뜻이 맞아떨어지는 날 — 순풍에 돛 단 듯 일이 술술 풀립니다", z_el)
    if any(day_branch in g and zodiac_branch in g for g in HYUNG_GROUPS) or \
            {day_branch, zodiac_branch} == SANG_HYUNG:
        return _r("주의", "오늘 기운과 살짝 어긋나 마찰이 생기기 쉬운 날 — 말을 아끼면 그것이 곧 복", boch)
    if PA[day_branch] == zodiac_branch:
        return _r("주의", "계획이 어긋나기 쉬운 날 — 약속·일정을 한 번 더 확인하면 탈이 없습니다", boch)
    if HAE[day_branch] == zodiac_branch:
        return _r("주의", "사소한 오해가 생기기 쉬운 날 — 마음에 걸리는 일은 그날 바로 풀어두십시오", boch)
    if z_el == d_el:
        return _r("평온", f"오늘 기운과 같은 {ELEM_KO[z_el]}의 흐름을 나란히 타는 무난한 날 — 하던 일을 꾸준히", z_el)
    if SAENG[d_el] == z_el:
        return _r("상승", "오늘 기운이 나를 북돋아 주는 날 — 뜻밖의 도움이나 반가운 소식이 들어옵니다", d_el)
    if SAENG[z_el] == d_el:
        return _r("평온", "내가 오늘 기운을 살려주는 날 — 베푼 만큼 돌아오나 기운을 너무 쏟진 마십시오", boch)
    if GEUK[z_el] == d_el:
        return _r("능동", "내가 오늘 기운을 다스리는 날 — 주도권을 쥐되 겸손하면 결과가 더 단단해집니다", z_el)
    return _r("신중", "오늘 기운이 나를 눌러오는 날 — 무리하지 말고 완급을 조절하면 무탈합니다", SAENG[d_el])


def _r(tone: str, lead: str, lucky_elem: str) -> dict:
    return {
        "tone": tone,
        "lead": lead,
        "lucky_elem": lucky_elem,
        "lucky_color": ELEM_COLOR[lucky_elem],
        "lucky_number": ELEM_NUM[lucky_elem],
        "lucky_direction": ELEM_DIR[lucky_elem],
        "score_range": TONE_SCORE[tone],
        "stars": TONE_STARS[tone],
    }


def day_context(dt: _dt.date | None = None) -> dict:
    """그날 일진 요약 — 명리 해설·헤더용."""
    d = dt or _dt.date.today()
    dp = day_pillar(d)
    ds, db = dp[0], dp[1]
    return {
        "date": d.isoformat(),
        "day_pillar": dp,                       # 예: '정해'
        "day_stem": ds, "day_branch": db,
        "stem_elem": STEM_ELEM[ds], "branch_elem": BRANCH_ELEM[db],
        "animal": BRANCH_ANIMAL[db],
        "label": f"{dp}일",                     # 예: '정해일'
    }


def zodiac_day(sign, dt: _dt.date | None = None) -> dict | None:
    """띠 + 날짜 → 그날 일진 기준 관계·기조·행운요소. 두 서비스 공통 진입점."""
    zb = to_branch(sign)
    if zb is None:
        return None
    d = dt or _dt.date.today()
    rel = zodiac_relation(day_pillar(d)[1], zb)
    rel["branch"] = zb
    rel["animal"] = BRANCH_ANIMAL[zb]
    rel["day_pillar"] = day_pillar(d)
    return rel
