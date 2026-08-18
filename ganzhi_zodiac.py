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


# ── 출생연도 → 년주(年柱) 간지 + 색깔 띠 (서기 4년=갑자년 기준 60갑자 순환) ──
# 교차검증(역사적으로 널리 알려진 해): 1984=갑자·2020=경자(2020 "하얀 쥐의 해")·
# 1990=경오(90년생 "백말띠" 속설의 근거가 된 해)·2024=갑진("청룡의 해")·1966=병오.
# 전부 코드로 재검산 완료(OK) — 임의 추정치 아님.
_HANJA_COLOR = {"목": "청", "화": "적", "토": "황", "금": "백", "수": "흑"}


def year_pillar(year: int) -> str:
    """출생연도의 2글자 년주 간지 (예: 1990 → '경오')."""
    idx = (year - 4) % 60
    return STEMS[idx % 10] + BRANCHES[idx % 12]


def year_color_zodiac(year: int) -> dict | None:
    """출생연도 → 색깔 띠 재료(예: 1990년생 → 백/말/금). 라벨 조합은 호출부에서
    (toss_free의 동물 한글 표기와 통일하기 위해 animal 필드는 참고용)."""
    if not (1900 <= year <= 2100):
        return None
    yp = year_pillar(year)
    stem, branch = yp[0], yp[1]
    elem = STEM_ELEM[stem]
    return {
        "year": year,
        "year_pillar": yp,
        "stem": stem, "branch": branch,
        "elem": elem, "elem_ko": ELEM_KO[elem],
        "hanja_color": _HANJA_COLOR[elem],      # "백" — "OO띠" 라벨용
        "color_desc": ELEM_COLOR[elem],          # "흰색" — 서술형 문장용
        "animal": BRANCH_ANIMAL[branch],
    }


# ── 십이운성(十二運星) — 일간이 특정 지지에서 갖는 생명력 12단계 ──
# 장생지 표는 8-codes.com 만세력 강의 표로 교차검증(갑=해 장생·을=오 장생 등 전부 확인).
_UNSEONG_START = {"갑": "해", "을": "오", "병": "인", "정": "유", "무": "인",
                  "기": "유", "경": "사", "신": "자", "임": "신", "계": "묘"}
_YANG_STEMS = set("갑병무경임")  # 순행. 나머지(음간)는 역행.
_UNSEONG_NAMES = ["장생", "목욕", "관대", "건록", "제왕", "쇠", "병", "사", "묘", "절", "태", "양"]
_UNSEONG_INFO = {
    "장생": {"title": "새로운 시작", "desc": "새로운 인연이나 기회의 씨앗이 심기는 때예요. 작은 시작을 두려워하지 마세요.", "tip": "새 인연에 마음 열어두기"},
    "목욕": {"title": "설렘·불안정", "desc": "감정의 파도가 일렁이는 때예요. 성급한 결정보다는 한 박자 쉬어가는 게 좋아요.", "tip": "감정 앞선 결정은 하루 미루기"},
    "관대": {"title": "성장·준비", "desc": "실력을 갖춰가는 시기예요. 배움과 준비에 공들이면 곧 빛을 봅니다.", "tip": "배움에 시간 투자하기"},
    "건록": {"title": "자립·안정", "desc": "스스로의 힘으로 자리를 잡는 때예요. 그동안의 노력이 결실로 이어집니다.", "tip": "하던 대로 꾸준히 이어가기"},
    "제왕": {"title": "절정·왕성", "desc": "기운이 가장 왕성한 정점의 시기예요. 자신감을 갖고 나아가도 좋을 때입니다.", "tip": "자신감 있게 나아가기"},
    "쇠": {"title": "한 박자 쉬어가기", "desc": "무리하게 밀어붙이기보다 한 걸음 물러나 정리하기 좋은 때예요.", "tip": "속도를 조금 늦추기"},
    "병": {"title": "컨디션 관리", "desc": "몸과 마음이 지치기 쉬운 시기예요. 무리한 일정은 하나만 내려놓으세요.", "tip": "일정 하나 덜어내기"},
    "사": {"title": "멈춤·정리", "desc": "한 시절을 정리하고 매듭짓기 좋은 때예요. 미뤄둔 일을 마무리해보세요.", "tip": "미뤄둔 일 마무리하기"},
    "묘": {"title": "내실 다지기", "desc": "겉으로 드러내기보다 안으로 힘을 모으는 시기예요. 조용히 내실을 다지세요.", "tip": "조용히 내실 다지기"},
    "절": {"title": "단절·전환", "desc": "기존 흐름을 끊고 새로운 길을 모색하기 좋은 시점이에요. 결단이 필요한 날일 수 있어요.", "tip": "전환점 결정에 길"},
    "태": {"title": "구상·계획", "desc": "새로운 계획이 마음속에서 싹트는 때예요. 아직은 드러내지 말고 다듬어보세요.", "tip": "계획은 마음속에서 다듬기"},
    "양": {"title": "다듬기·준비", "desc": "본격적인 시작 전, 힘을 기르고 다듬는 시기예요. 서두르지 않아도 됩니다.", "tip": "서두르지 않고 다듬기"},
}


def twelve_stage(stem: str, branch: str) -> dict:
    """일간(stem)이 지지(branch)에서 갖는 십이운성 1단계."""
    start_idx = BRANCHES.index(_UNSEONG_START[stem])
    branch_idx = BRANCHES.index(branch)
    offset = (branch_idx - start_idx) % 12 if stem in _YANG_STEMS else (start_idx - branch_idx) % 12
    name = _UNSEONG_NAMES[offset]
    return {"name": name, **_UNSEONG_INFO[name]}


def today_twelve_stage(sign, dt: _dt.date | None = None) -> dict | None:
    """띠 + 날짜 → 오늘 일간 기준 십이운성. 사주 입력 불필요(무료 훅 용도)."""
    zb = to_branch(sign)
    if zb is None:
        return None
    d = dt or _dt.date.today()
    dp = day_pillar(d)
    stage = twelve_stage(dp[0], zb)
    stage["day_pillar"] = dp
    return stage


# ── 지지 관계 분류(재사용 전용) ──
# zodiac_relation()은 이미 배포되어 실사용 중이라 그대로 두고, "올해의 흐름"·"시진 가이드"는
# 같은 우선순위 규칙을 별도 함수로 재구현해 기존 로직에 전혀 영향을 주지 않는다.
# 반환 13종: 동일·자형(진오유해 자기형벌)·충·육합·삼합·형·파·해·비화·생(도움받음)·
#            설(내가 베풂)·극(내가 주도)·피극(눌림, fallback)
def _relation_kind(a: str, b: str) -> str:
    a_el, b_el = BRANCH_ELEM[a], BRANCH_ELEM[b]
    if b == a:
        return "자형" if b in JA_HYUNG else "동일"
    if CHUNG[a] == b:
        return "충"
    if YUKHAP[a] == b:
        return "육합"
    for g in SAMHAP:
        if a in g and b in g:
            return "삼합"
    if any(a in g and b in g for g in HYUNG_GROUPS) or {a, b} == SANG_HYUNG:
        return "형"
    if PA[a] == b:
        return "파"
    if HAE[a] == b:
        return "해"
    if b_el == a_el:
        return "비화"
    if SAENG[a_el] == b_el:
        return "생"
    if SAENG[b_el] == a_el:
        return "설"
    if GEUK[b_el] == a_el:
        return "극"
    return "피극"


# ── 올해의 흐름 — 연간지 × 띠 관계 (교차검증: 2026=병오, 오/자=충 → "변화·전환·유연성") ──
_YEAR_FLOW = {
    "동일": {"tone": "상승", "summary": "올해는 자신의 기운이 강하게 발현되는 해입니다. 존재감이 커지고 하려는 일에 힘이 실릴 수 있어요.", "tags": ["존재감", "추진력", "주도"]},
    "자형": {"tone": "주의", "summary": "올해는 스스로를 다그치기 쉬운 해입니다. 여유를 갖고 무리한 욕심은 내려놓는 편이 이롭습니다.", "tags": ["여유", "조절", "휴식"]},
    "충": {"tone": "신중", "summary": "올해는 변화와 이동의 기운이 강한 해입니다. 예상치 못한 전환이 있을 수 있지만, 유연하게 대처하면 새로운 가능성이 열릴 수 있어요.", "tags": ["변화", "전환", "유연성"]},
    "육합": {"tone": "상승", "summary": "올해는 인연과 협력이 두드러지는 해입니다. 좋은 사람들과의 만남이 새로운 기회로 이어질 수 있어요.", "tags": ["인연", "협력", "기회"]},
    "삼합": {"tone": "상승", "summary": "올해는 뜻이 맞는 흐름을 타는 해입니다. 계획한 일들이 순조롭게 풀려나갈 가능성이 큽니다.", "tags": ["순조", "결실", "화합"]},
    "형": {"tone": "주의", "summary": "올해는 관계에서 마찰이 생기기 쉬운 해입니다. 말과 행동을 한 번 더 살피면 큰 탈 없이 지나갈 수 있어요.", "tags": ["신중", "배려", "절제"]},
    "파": {"tone": "주의", "summary": "올해는 계획이 예상과 어긋나기 쉬운 해입니다. 중요한 약속과 일정은 여유 있게 잡아두는 편이 안전합니다.", "tags": ["점검", "여유", "준비"]},
    "해": {"tone": "주의", "summary": "올해는 사소한 오해가 쌓이기 쉬운 해입니다. 마음에 담아두지 말고 그때그때 풀어가는 게 좋습니다.", "tags": ["소통", "이해", "화해"]},
    "비화": {"tone": "평온", "summary": "올해는 지금의 흐름을 꾸준히 이어가기 좋은 해입니다. 큰 변화보다 안정 속에서 내실을 다지세요.", "tags": ["안정", "꾸준함", "내실"]},
    "생": {"tone": "상승", "summary": "올해는 주변의 도움과 좋은 기운이 들어오는 해입니다. 뜻밖의 인연이나 기회를 놓치지 마세요.", "tags": ["귀인", "행운", "기회"]},
    "설": {"tone": "평온", "summary": "올해는 그동안 쌓은 것을 베풀고 나누는 해입니다. 나눈 만큼 좋은 인연으로 돌아옵니다.", "tags": ["나눔", "인연", "순환"]},
    "극": {"tone": "능동", "summary": "올해는 주도권을 쥐고 나아가기 좋은 해입니다. 자신감을 갖되 겸손함을 잃지 않으면 결과가 단단해집니다.", "tags": ["도전", "자신감", "성취"]},
    "피극": {"tone": "신중", "summary": "올해는 무리하지 않고 완급을 조절해야 하는 해입니다. 서두르기보다 하나씩 다져가면 무탈하게 지나갑니다.", "tags": ["절제", "인내", "대비"]},
}


def year_flow(sign, year: int | None = None) -> dict | None:
    """띠 + 연도 → 그해 연간지 기준 흐름(서사+태그). 사주 입력 불필요."""
    zb = to_branch(sign)
    if zb is None:
        return None
    y = year or _dt.date.today().year
    yp = year_pillar(y)
    kind = _relation_kind(yp[1], zb)
    info = _YEAR_FLOW[kind]
    return {"year": y, "year_pillar": yp, "animal": BRANCH_ANIMAL[zb], **info}


# ── 오늘의 시진(時辰) 가이드 — 12지지 시간대 × 띠 관계로 길시/흉시 판정 ──
SIJIN = [
    {"name": "자시", "hanja": "子時", "branch": "자", "range": "23:00 - 01:00"},
    {"name": "축시", "hanja": "丑時", "branch": "축", "range": "01:00 - 03:00"},
    {"name": "인시", "hanja": "寅時", "branch": "인", "range": "03:00 - 05:00"},
    {"name": "묘시", "hanja": "卯時", "branch": "묘", "range": "05:00 - 07:00"},
    {"name": "진시", "hanja": "辰時", "branch": "진", "range": "07:00 - 09:00"},
    {"name": "사시", "hanja": "巳時", "branch": "사", "range": "09:00 - 11:00"},
    {"name": "오시", "hanja": "午時", "branch": "오", "range": "11:00 - 13:00"},
    {"name": "미시", "hanja": "未時", "branch": "미", "range": "13:00 - 15:00"},
    {"name": "신시", "hanja": "申時", "branch": "신", "range": "15:00 - 17:00"},
    {"name": "유시", "hanja": "酉時", "branch": "유", "range": "17:00 - 19:00"},
    {"name": "술시", "hanja": "戌時", "branch": "술", "range": "19:00 - 21:00"},
    {"name": "해시", "hanja": "亥時", "branch": "해", "range": "21:00 - 23:00"},
]
_HOUR_GUIDE = {
    "동일": {"tier": "길시", "text": "같은 기운으로 편안하고 흐름이 자연스러워요."},
    "자형": {"tier": "흉시", "text": "같은 기운이 겹쳐 스스로를 몰아세우기 쉬운 시간이에요."},
    "충": {"tier": "흉시", "text": "충 기운으로 충돌·마찰·사고에 주의하세요."},
    "육합": {"tier": "길시", "text": "육합 기운으로 대화·협력·약속에 좋아요."},
    "삼합": {"tier": "길시", "text": "뜻이 맞아떨어져 일이 순조로운 시간이에요."},
    "형": {"tier": "흉시", "text": "말과 행동에 유독 조심이 필요한 시간이에요."},
    "파": {"tier": "흉시", "text": "약속·계획이 어긋나기 쉬우니 한 번 더 확인하세요."},
    "해": {"tier": "흉시", "text": "사소한 오해가 생기기 쉬운 시간이에요."},
    "비화": {"tier": "평시", "text": "무난하게 흘러가는 시간이에요."},
    "생": {"tier": "길시", "text": "뜻밖의 도움이나 좋은 기운이 들어오는 시간이에요."},
    "설": {"tier": "평시", "text": "베푸는 만큼 기운을 쓰는 시간, 무리하지 마세요."},
    "극": {"tier": "길시", "text": "주도권을 쥐기 좋은 시간이에요."},
    "피극": {"tier": "흉시", "text": "무리하지 말고 완급을 조절하세요."},
}


def _sijin_index(hour: int) -> int:
    return ((hour + 1) // 2) % 12


# ── 오자시결(五鼠遁) — 일간에서 그날 각 시진의 실제 천간을 파생 ──
# 교차검증: 갑기일→갑자시·을경일→병자시·병신일→무자시·정임일→경자시·무계일→임자시
# (한국운명학회 간지정법 자료로 확인). 이후 시진은 지지 순서대로 천간도 순행.
_SIJU_START = {"갑": "갑", "기": "갑", "을": "병", "경": "병", "병": "무", "신": "무",
               "정": "경", "임": "경", "무": "임", "계": "임"}


def hour_pillar_of(day_stem: str, branch_idx: int) -> str:
    """오늘 일간 기준, branch_idx(0=자~11=해)번째 시진의 실제 2글자 간지."""
    start_idx = STEMS.index(_SIJU_START[day_stem])
    return STEMS[(start_idx + branch_idx) % 10] + BRANCHES[branch_idx]


def _hour_relation_kind(hour_stem: str, hour_branch: str, zodiac_branch: str) -> str:
    """시진의 실제 간지(오자시결로 일간에서 파생) vs 띠 지지.
    충·육합·삼합·형·파·해·동일 같은 지지 직접관계는 지지끼리(원래도 그렇게 정의됨),
    그 외(생·극·비화)는 시진의 실제 천간 오행으로 판정 — 그래서 날짜가 바뀌면 이 부분도 바뀐다."""
    a, b = hour_branch, zodiac_branch
    if b == a:
        return "자형" if b in JA_HYUNG else "동일"
    if CHUNG[a] == b:
        return "충"
    if YUKHAP[a] == b:
        return "육합"
    for g in SAMHAP:
        if a in g and b in g:
            return "삼합"
    if any(a in g and b in g for g in HYUNG_GROUPS) or {a, b} == SANG_HYUNG:
        return "형"
    if PA[a] == b:
        return "파"
    if HAE[a] == b:
        return "해"
    h_el, z_el = STEM_ELEM[hour_stem], BRANCH_ELEM[b]
    if h_el == z_el:
        return "비화"
    if SAENG[h_el] == z_el:
        return "생"
    if SAENG[z_el] == h_el:
        return "설"
    if GEUK[z_el] == h_el:
        return "극"
    return "피극"


def hour_guide(sign, now: _dt.datetime | None = None) -> dict | None:
    """띠 + 현재시각 → 12시진 전체 길시/흉시 리스트 + 현재 시진 표시. 사주 입력 불필요.
    오늘 일간에서 오자시결로 각 시진의 실제 간지를 뽑아 판정하므로 날짜마다 결과가 바뀐다."""
    zb = to_branch(sign)
    if zb is None:
        return None
    n = now or _dt.datetime.now()
    dp = day_pillar(n.date())
    day_stem = dp[0]
    current_idx = _sijin_index(n.hour)
    blocks = []
    for i, s in enumerate(SIJIN):
        hp = hour_pillar_of(day_stem, i)
        kind = _hour_relation_kind(hp[0], s["branch"], zb)
        g = _HOUR_GUIDE[kind]
        is_now = i == current_idx
        blocks.append({
            "name": s["name"], "hanja": s["hanja"], "range": s["range"],
            "hour_pillar": hp,
            "tier": ("본인 시각" if (is_now and kind in ("동일", "자형")) else g["tier"]),
            "text": g["text"], "is_now": is_now,
        })
    return {"animal": BRANCH_ANIMAL[zb], "day_pillar": dp, "current_index": current_idx, "blocks": blocks}
