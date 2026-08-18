# -*- coding: utf-8 -*-
"""zodiac_month.py — 12띠 월간 운세 엔진 (2026-07-25)

일일 운세가 '일진(日辰)'과 띠의 관계로 기조를 정하듯, 월간은 '월건(月建)'과의 관계로 정한다.
관계 판정 로직(충·육합·삼합·형·파·해·오행)은 ganzhi_zodiac.zodiac_relation을 그대로 재사용한다.

일일판보다 세분화한 지점
  - 총운 외에 재물·애정·건강·직업 4분야를 따로 낸다
  - 그 달의 상순/중순/하순 일진을 실제로 계산해 평균 점수를 내고,
    가장 좋은 순 / 조심할 순을 뽑는다 (명리 근거가 있는 시기 구분)
  - 길일 3개를 실제 일진 관계 점수 상위에서 고른다

전부 결정론적이다. LLM 호출 0, 외부 의존 0 — 같은 (띠, 연월)이면 항상 같은 결과.
"""
from __future__ import annotations

import datetime as _dt
import hashlib

from ganzhi_zodiac import (
    BRANCHES, STEMS, day_pillar, to_branch, zodiac_relation,
)

# ── 월지(月支): 절기 기준 근사. 입춘(2월)=인월 … 입추(8월)=신월 ──
#    양력 m월 → BRANCHES[m % 12]  (1월=축, 2월=인, 8월=신, 12월=자)
def month_branch(month: int) -> str:
    return BRANCHES[month % 12]


def year_stem_index(year: int) -> int:
    return (year - 4) % 10


def month_pillar(year: int, month: int) -> str:
    """월건 2글자. 천간은 오호둔(五虎遁)으로 년간에서 유도한다.

    갑기년→병인월 / 을경년→무인월 / 병신년→경인월 / 정임년→임인월 / 무계년→갑인월
    → 인월 천간 index = (년간 % 5) * 2 + 2
    1월(축월)은 절기상 전년도에 속하므로 전년 년간을 쓴다.
    """
    y = year - 1 if month == 1 else year
    tiger_stem = (year_stem_index(y) % 5) * 2 + 2          # 인월 천간
    stem = (tiger_stem + (month - 2)) % 10                  # 인월부터 월마다 +1
    return STEMS[stem] + month_branch(month)


_BRANCH_KO = {"자": "자", "축": "축", "인": "인", "묘": "묘", "진": "진", "사": "사",
              "오": "오", "미": "미", "신": "신", "유": "유", "술": "술", "해": "해"}
_BRANCH_HANJA = {"자": "子", "축": "丑", "인": "寅", "묘": "卯", "진": "辰", "사": "巳",
                 "오": "午", "미": "未", "신": "申", "유": "酉", "술": "戌", "해": "亥"}


def month_label(year: int, month: int) -> str:
    """화면 표기용 월건 라벨.

    월건 전체(천간+지지)를 그대로 쓰면 달에 따라 읽기 곤란한 조합이 나온다
    (2026년 8월 = 丙申 → '병신'). 띠와의 관계 판정은 월지만으로 이뤄지므로
    표시에는 월지만 쓴다. 명리적으로도 어긋나지 않는다.
    """
    b = month_branch(month)
    return f"{_BRANCH_KO[b]}({_BRANCH_HANJA[b]})월"


def _seed(*parts) -> int:
    return int(hashlib.sha256("|".join(map(str, parts)).encode("utf-8")).hexdigest()[:8], 16)


def _pick(pool: list, *seed_parts):
    return pool[_seed(*seed_parts) % len(pool)]


def _days_in_month(year: int, month: int) -> int:
    nxt = _dt.date(year + (month == 12), (month % 12) + 1, 1)
    return (nxt - _dt.date(year, month, 1)).days


def _score_of(tone: str, seed: int) -> int:
    lo, hi = {"상승": (82, 93), "능동": (74, 85), "평온": (70, 80),
              "신중": (62, 73), "주의": (58, 69)}[tone]
    return lo + seed % (hi - lo + 1)


# ── 분야별 문장 (기조별 3종 로테이션) ────────────────────────────
_WEALTH = {
    "상승": ["막혀 있던 돈줄이 트이는 달입니다. 들어올 것을 챙기되 욕심은 한 발 물리세요.",
             "재물에 파란불이 켜집니다. 미뤄둔 정산이나 회수가 순조롭습니다.",
             "노력한 만큼 수입으로 돌아오는 달입니다. 새 수익원도 살펴볼 만합니다."],
    "능동": ["내가 움직인 만큼 벌리는 달입니다. 먼저 제안하면 성과가 따라옵니다.",
             "주도권을 쥐면 돈이 붙습니다. 다만 무리한 확장은 하순으로 미루세요.",
             "협상에서 유리한 달입니다. 조건을 분명히 말해도 좋습니다."],
    "평온": ["큰 기복 없이 흐르는 달입니다. 새로 벌이기보다 지키는 편이 이롭습니다.",
             "수입도 지출도 무난합니다. 이번 달은 가계를 점검하기 좋습니다.",
             "평탄한 흐름입니다. 작게 모으는 습관이 뒤에 큰 힘이 됩니다."],
    "신중": ["지출을 한 번 점검할 때입니다. 충동구매만 참아도 이득입니다.",
             "보증·투자 권유는 한 번 거르십시오. 서두르면 손해가 큽니다.",
             "큰돈이 나갈 일이 생길 수 있습니다. 미리 여유를 두세요."],
    "주의": ["돈 문제로 마음 상할 일이 생기기 쉽습니다. 계약서는 두 번 보십시오.",
             "빌려주는 일은 피하는 게 좋습니다. 정으로 시작해 탈이 납니다.",
             "예상 밖 지출이 있을 수 있습니다. 이번 달은 지키는 것이 버는 것입니다."],
}
_LOVE = {
    "상승": ["마음이 통하는 달입니다. 먼저 연락하면 좋은 흐름이 열립니다.",
             "인연이 가까이 다가옵니다. 모임 자리를 마다하지 마세요.",
             "오래 미룬 한마디를 건네기 좋은 달입니다."],
    "능동": ["망설이던 마음을 정할 때입니다. 분명한 태도가 관계를 앞으로 밀어줍니다.",
             "내가 이끄는 쪽이 잘 풀립니다. 다만 상대의 속도도 살피세요.",
             "표현이 곧 매력이 되는 달입니다."],
    "평온": ["잔잔하고 편안한 달입니다. 익숙함에 고마움을 표현해 보세요.",
             "큰 변화는 없으나 정이 깊어집니다. 함께 보내는 시간을 늘려보세요.",
             "무던한 흐름입니다. 작은 배려가 관계를 키웁니다."],
    "신중": ["서두르면 어긋납니다. 한 박자 천천히, 들어주는 편이 낫습니다.",
             "오해가 생기기 쉬운 달입니다. 말끝을 부드럽게 하세요.",
             "결정은 다음 달로 미루셔도 늦지 않습니다."],
    "주의": ["말 한마디로 멀어질 수 있습니다. 오늘 감정은 오늘 풀어두세요.",
             "지난 일을 다시 꺼내는 것은 이로울 게 없습니다.",
             "거리를 조금 두면 오히려 관계가 회복됩니다."],
}
_HEALTH = {
    "상승": ["컨디션이 가뿐한 달입니다. 미뤄둔 운동을 시작하기 좋습니다.",
             "기운이 도는 달입니다. 활동을 늘려도 무리가 없습니다.",
             "몸이 가벼워집니다. 이 기운을 습관으로 만들어 두세요."],
    "능동": ["활력이 넘칩니다. 다만 과로만 조심하면 탈이 없습니다.",
             "체력을 쓰기 좋은 달입니다. 쉬는 날은 확실히 쉬세요.",
             "몸이 잘 따라줍니다. 무리한 일정 하나만 덜어내세요."],
    "평온": ["큰 이상 없이 지나갑니다. 규칙적인 생활만 지키시면 됩니다.",
             "무난한 달입니다. 잠자는 시간을 일정하게 두세요.",
             "평온합니다. 가벼운 산책을 꾸준히 해보세요."],
    "신중": ["몸이 보내는 신호를 가볍게 넘기지 마십시오.",
             "피로가 쌓이기 쉬운 달입니다. 일정 하나를 줄이세요.",
             "환절기 잔병에 주의하십시오. 따뜻하게 지내시는 게 좋습니다."],
    "주의": ["기복이 큰 달입니다. 몸을 아끼는 것을 최우선으로 하세요.",
             "무리하면 바로 탈이 납니다. 미루셔도 되는 일은 미루세요.",
             "정기 검진을 미뤄두셨다면 이번 달에 받아보십시오."],
}
_WORK = {
    "상승": ["하던 일에 성과가 드러납니다. 한 걸음 더 나가면 결실이 옵니다.",
             "귀인의 도움이 따르는 달입니다. 도움을 청하는 것을 주저 마세요.",
             "새 일을 시작하기 좋은 달입니다."],
    "능동": ["주도권을 쥐고 밀고 나갈 때입니다. 방향만 분명하면 힘이 실립니다.",
             "제안과 발표에서 좋은 반응을 얻습니다.",
             "목표를 하나로 좁히면 성과가 커집니다."],
    "평온": ["하던 대로 꾸준히 가면 되는 달입니다.",
             "큰 변화는 없으나 신뢰가 쌓입니다. 기본을 지키세요.",
             "안정적인 흐름입니다. 내실을 다지기 좋습니다."],
    "신중": ["큰 결정은 한 박자 쉬어가는 편이 낫습니다.",
             "말이 앞서면 손해입니다. 문서로 남겨두세요.",
             "이직·전직은 다음 달 흐름을 보고 정하십시오."],
    "주의": ["구설에 오르기 쉬운 달입니다. 말을 아끼면 그것이 복입니다.",
             "일정이 어긋나기 쉽습니다. 약속은 한 번 더 확인하세요.",
             "책임질 일은 범위를 분명히 해두십시오."],
}
_ADVICE = {
    "상승": "이 달의 기운을 미루지 말고 쓰십시오. 먼저 움직이는 쪽에 복이 옵니다.",
    "능동": "방향을 하나로 좁히면 이 달의 힘이 온전히 실립니다.",
    "평온": "특별할 것 없어 보여도 꾸준함이 쌓이는 달입니다.",
    "신중": "서두르지 않는 것이 이 달의 가장 좋은 전략입니다.",
    "주의": "지키는 것이 곧 얻는 것입니다. 한 달만 몸을 낮추십시오.",
}
_HEADLINE = {
    "상승": ["순풍에 돛 단 달", "기운이 활짝 열리는 달", "결실이 눈에 보이는 달"],
    "능동": ["내가 끌고 가는 달", "주도권을 쥐는 달", "밀고 나가면 되는 달"],
    "평온": ["잔잔하게 흐르는 달", "기본을 다지는 달", "무탈하게 지나가는 달"],
    "신중": ["한 박자 쉬어가는 달", "속도를 줄일 달", "때를 기다리는 달"],
    "주의": ["몸을 낮출 달", "말을 아낄 달", "지키는 것이 이로운 달"],
}
_TEN_KO = {1: "상순", 2: "중순", 3: "하순"}
_TEN_RANGE = {1: "1일~10일", 2: "11일~20일", 3: "21일~말일"}


def _decade_scores(branch: str, year: int, month: int) -> dict[int, float]:
    """상·중·하순 각 구간의 일진 × 띠 관계 점수 평균. 시기 구분의 명리 근거."""
    last = _days_in_month(year, month)
    buckets: dict[int, list[int]] = {1: [], 2: [], 3: []}
    for day in range(1, last + 1):
        d = _dt.date(year, month, day)
        rel = zodiac_relation(day_pillar(d)[1], branch)
        lo, hi = rel["score_range"]
        buckets[1 if day <= 10 else (2 if day <= 20 else 3)].append((lo + hi) // 2)
    return {k: round(sum(v) / len(v), 1) for k, v in buckets.items() if v}


def lucky_days(branch: str, year: int, month: int) -> list[int]:
    """길일 3개 — 상·중·하순에서 각각 가장 좋은 날 하나씩.

    전체 상위 3개를 그냥 뽑으면 동점이 많아 죄다 1~10일로 몰린다(실제로 그랬다).
    순마다 하나씩 뽑아야 한 달에 고르게 퍼지고, 쓰는 사람에게도 쓸모가 있다.
    """
    last = _days_in_month(year, month)
    best: dict[int, tuple[float, int]] = {}
    for day in range(1, last + 1):
        d = _dt.date(year, month, day)
        lo, hi = zodiac_relation(day_pillar(d)[1], branch)["score_range"]
        ten = 1 if day <= 10 else (2 if day <= 20 else 3)
        s = (lo + hi) / 2
        if ten not in best or s > best[ten][0]:
            best[ten] = (s, day)
    return sorted(v[1] for v in best.values())


def make_month_reading(sign_slug: str, year: int, month: int) -> dict:
    """12띠 중 하나의 월간 운세. 결정론적."""
    branch = to_branch(sign_slug)
    if branch is None:
        raise ValueError(f"unknown sign: {sign_slug}")
    pillar = month_pillar(year, month)
    rel = zodiac_relation(pillar[1], branch)
    tone = rel["tone"]
    sd = _seed(sign_slug, year, month)
    dec = _decade_scores(branch, year, month)
    # 동점이면 max와 min이 같은 순을 가리켜 "상순이 좋고 상순을 주의하라"가 나온다.
    # 점수순으로 세운 뒤 양 끝을 쓰고, 차이가 거의 없으면 시기 구분 자체를 하지 않는다.
    ranked = sorted(dec.items(), key=lambda kv: (-kv[1], kv[0]))
    flat = (ranked[0][1] - ranked[-1][1]) < 1.5      # 1.5점 미만이면 사실상 평탄
    best_k, care_k = ranked[0][0], ranked[-1][0]

    return {
        "sign": sign_slug,
        "year": year,
        "month": month,
        "month_pillar": pillar,
        "tone": tone,
        "score": _score_of(tone, sd),
        "stars": rel["stars"],
        "headline": _pick(_HEADLINE[tone], sign_slug, year, month, "h"),
        "wealth": _pick(_WEALTH[tone], sign_slug, year, month, "w"),
        "love": _pick(_LOVE[tone], sign_slug, year, month, "l"),
        "health": _pick(_HEALTH[tone], sign_slug, year, month, "he"),
        "work": _pick(_WORK[tone], sign_slug, year, month, "wk"),
        "advice": _ADVICE[tone],
        "flat_month": flat,
        "best_period": None if flat else
            {"ten": _TEN_KO[best_k], "range": _TEN_RANGE[best_k], "score": dec[best_k]},
        "care_period": None if flat else
            {"ten": _TEN_KO[care_k], "range": _TEN_RANGE[care_k], "score": dec[care_k]},
        "period_note": "한 달 내내 고른 흐름입니다" if flat else
            f"{_TEN_KO[best_k]}({_TEN_RANGE[best_k]})이 가장 좋고, {_TEN_KO[care_k]}은 한 박자 쉬어가세요",
        "decade_scores": {_TEN_KO[k]: v for k, v in dec.items()},
        "lucky_days": lucky_days(branch, year, month),
        "lucky_color": rel["lucky_color"],
        "lucky_number": rel["lucky_number"],
        "lucky_direction": rel["lucky_direction"],
    }


def all_month_readings(year: int, month: int) -> list[dict]:
    """12띠 전체. 슬러그는 zodiac_seo 기준(KO_TO_SLUG)을 쓴다.

    주의: zodiac_prompt_engine.ZODIAC_EN은 양띠를 'sheep'으로, ganzhi_zodiac·zodiac_seo는
    'goat'로 쓴다. 여기서 zodiac_seo 쪽을 정본으로 삼아 불일치를 흡수한다.
    """
    from zodiac_prompt_engine import ZODIAC12
    from zodiac_seo import KO_TO_SLUG
    out = []
    for ko in ZODIAC12:
        r = make_month_reading(KO_TO_SLUG[ko], year, month)
        r["sign_ko"] = ko
        out.append(r)
    return out


# 실제 조회수·참여도 데이터가 연결되기 전까지는 월간 점수의 극단성으로 개별 영상을 고른다.
# 평온 점수대의 중앙값과의 거리, 그 다음 순·중·하순 점수 변동폭 순으로 결정한다.
FEATURED_NEUTRAL_SCORE = 75


def select_featured_month_readings(year: int, month: int, limit: int = 3) -> list[dict]:
    """개별 월간 쇼츠 후보를 결정론적으로 반환한다.

    기존 월간 엔진의 ``score``와 일진 관계에서 계산한 ``decade_scores``만 쓴다.
    실제 성과 데이터가 연결되면 영상 조립 코드는 바꾸지 않고 순위 입력만 교체할 수 있다.
    """
    if limit <= 0:
        return []

    readings = all_month_readings(year, month)

    def rank_key(reading: dict) -> tuple[int, int, str]:
        extremeness = abs(int(reading["score"]) - FEATURED_NEUTRAL_SCORE)
        values = list(reading["decade_scores"].values())
        spread = max(values) - min(values)
        return (-extremeness, -spread, reading["sign"])

    selected: list[dict] = []
    for rank, reading in enumerate(sorted(readings, key=rank_key)[:limit], start=1):
        item = dict(reading)
        extremeness = abs(int(item["score"]) - FEATURED_NEUTRAL_SCORE)
        values = list(item["decade_scores"].values())
        spread = max(values) - min(values)
        item["featured_selection"] = {
            "rank": rank,
            "method": "deterministic_monthly_score_extremity",
            "neutral_score": FEATURED_NEUTRAL_SCORE,
            "score": item["score"],
            "extremeness": extremeness,
            "period_spread": spread,
            "basis": (
                f"월간 총운 {item['score']}점이 평온 기준 {FEATURED_NEUTRAL_SCORE}점에서 "
                f"{extremeness}점 떨어졌고, 순·중·하순 점수 변동폭은 {spread}점"
            ),
        }
        selected.append(item)
    return selected


if __name__ == "__main__":
    import sys
    y = int(sys.argv[1]) if len(sys.argv) > 1 else 2026
    m = int(sys.argv[2]) if len(sys.argv) > 2 else 8
    print(f"{y}년 {m}월 월건: {month_pillar(y, m)}\n")
    for r in all_month_readings(y, m):
        print(f"[{r['sign_ko']:5}] {r['tone']} {r['score']}점 · {r['headline']}")
        print(f"   {r['period_note']} / 길일 {r['lucky_days']}")
