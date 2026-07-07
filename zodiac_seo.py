"""12띠 일일 운세 SEO 콘텐츠 생성기.

결정론적(sign+date seed)으로 매일 다른 운세 본문 생성.
외부 API 호출 없음 — 빠르고 무료, 영구 캐시 가능.

사용처:
  - /zodiac/<sign>/<date> SEO 페이지
  - sitemap.xml 동적 URL
  - 카드뉴스·쓰레드 자동 발행 본문
"""
from __future__ import annotations
import hashlib
import datetime as dt
from dataclasses import dataclass
from typing import List

ZODIAC = [
    ("rat",    "쥐띠", "子", ["1924","1936","1948","1960","1972","1984","1996","2008","2020"]),
    ("ox",     "소띠", "丑", ["1925","1937","1949","1961","1973","1985","1997","2009","2021"]),
    ("tiger",  "호랑이띠", "寅", ["1926","1938","1950","1962","1974","1986","1998","2010","2022"]),
    ("rabbit", "토끼띠", "卯", ["1927","1939","1951","1963","1975","1987","1999","2011","2023"]),
    ("dragon", "용띠", "辰", ["1928","1940","1952","1964","1976","1988","2000","2012","2024"]),
    ("snake",  "뱀띠", "巳", ["1929","1941","1953","1965","1977","1989","2001","2013","2025"]),
    ("horse",  "말띠", "午", ["1930","1942","1954","1966","1978","1990","2002","2014","2026"]),
    ("goat",   "양띠", "未", ["1931","1943","1955","1967","1979","1991","2003","2015"]),
    ("monkey", "원숭이띠", "申", ["1932","1944","1956","1968","1980","1992","2004","2016"]),
    ("rooster","닭띠", "酉", ["1933","1945","1957","1969","1981","1993","2005","2017"]),
    ("dog",    "개띠", "戌", ["1934","1946","1958","1970","1982","1994","2006","2018"]),
    ("pig",    "돼지띠", "亥", ["1935","1947","1959","1971","1983","1995","2007","2019"]),
]

SLUG_TO_INFO = {z[0]: z for z in ZODIAC}
KO_TO_SLUG = {z[1]: z[0] for z in ZODIAC}

SIGN_EMOJI = {
    "rat": "🐭", "ox": "🐮", "tiger": "🐯", "rabbit": "🐰",
    "dragon": "🐲", "snake": "🐍", "horse": "🐴", "goat": "🐑",
    "monkey": "🐵", "rooster": "🐔", "dog": "🐶", "pig": "🐷",
}

OVERALL_POOL = [
    "오늘은 묵은 일이 자연스레 정리되는 흐름입니다. 서두르지 마시고 한 가지씩 매듭지으시면 큰 결실이 옵니다.",
    "오늘은 작은 변화가 큰 기회로 이어지는 날입니다. 평소와 다른 길을 한번 걸어보십시오.",
    "오늘은 인간관계에서 귀한 인연이 들어옵니다. 오랜만에 연락 오는 분이 있다면 반갑게 맞으십시오.",
    "오늘은 마음의 평정을 지키는 것이 가장 큰 운입니다. 화를 다스리시면 재물도 자연스레 따릅니다.",
    "오늘은 결단력이 빛나는 날입니다. 미뤄두었던 결정을 내리시기 좋은 흐름입니다.",
    "오늘은 가족·자녀와의 대화가 큰 힘이 됩니다. 함께 식사하시면 운이 두 배로 자랍니다.",
    "오늘은 건강 관리에 작은 시간이라도 투자하시면 큰 복으로 돌아옵니다.",
    "오늘은 평소의 노력이 드디어 인정받는 날입니다. 자신감을 잃지 마십시오.",
    "오늘은 뜻밖의 도움이 들어오는 흐름입니다. 받는 일에 부끄러워하지 마십시오.",
    "오늘은 정리와 청소가 가장 큰 개운법입니다. 묵은 짐을 비우시면 새 기운이 들어옵니다.",
    "오늘은 서두르지 않을수록 일이 술술 풀리는 흐름입니다. 한 박자 늦추면 좋은 결과가 따릅니다.",
    "오늘은 오래 준비한 일에 기분 좋은 소식이 드는 날입니다. 자신을 믿고 나아가십시오.",
    "오늘은 주변을 살피는 따뜻한 마음이 큰 복을 부릅니다. 먼저 안부를 전해 보십시오.",
    "오늘은 작은 지출도 한 번 더 살피면 재물이 새지 않는 날입니다.",
    "오늘은 몸을 부지런히 움직일수록 기운이 살아나는 흐름입니다. 가벼운 걸음이 약이 됩니다.",
    "오늘은 말 한마디를 아끼면 오히려 신뢰가 쌓이는 날입니다.",
    "오늘은 오래된 약속이나 인연을 다시 챙기면 뜻밖의 기쁨이 옵니다.",
    "오늘은 익숙한 길보다 새로운 시도가 좋은 운을 부르는 날입니다.",
    "오늘은 마음을 비우고 하나에 집중하면 막힌 일이 풀립니다.",
    "오늘은 웃는 얼굴이 가장 큰 재산이 되는 날입니다. 여유를 잃지 마십시오.",
    "오늘은 도움을 청하는 것이 부끄러운 일이 아닙니다. 손 내밀면 귀인이 나타납니다.",
    "오늘은 자녀나 후배의 말에 귀 기울이면 값진 깨달음을 얻습니다.",
    "오늘은 미뤄둔 건강 관리를 시작하기에 더없이 좋은 날입니다.",
    "오늘은 욕심을 조금 내려놓으면 마음도 재물도 넉넉해지는 흐름입니다.",
    "오늘은 정성껏 차린 한 끼가 몸과 마음을 크게 북돋아 줍니다.",
    "오늘은 오래 고민하던 결정을 내리기에 알맞은 기운이 흐릅니다.",
    "오늘은 감사의 마음을 표현할수록 좋은 인연이 늘어나는 날입니다.",
    "오늘은 조용히 자기 자리를 지키는 것이 가장 큰 힘이 되는 날입니다.",
    "오늘은 뜻밖의 장소에서 반가운 소식이나 인연을 만나는 흐름입니다.",
    "오늘은 하루를 일찍 시작하면 그만큼 운의 문이 넓게 열립니다.",
]

MONEY_POOL = [
    "재물운은 안정적입니다. 작은 절약이 큰 액수로 자라는 시기입니다.",
    "재물운이 서서히 상승합니다. 부동산·저축 관련 결정이 길합니다.",
    "재물운은 인연을 통해 들어옵니다. 신뢰할 수 있는 분의 조언을 듣는 것이 좋습니다.",
    "재물운은 본업에 집중하실 때 가장 강합니다. 무리한 투자는 미루십시오.",
    "재물운에 큰 변화의 신호가 있습니다. 정리할 것은 정리하시는 것이 길합니다.",
    "재물운은 천천히 그러나 확실히 자라는 흐름입니다. 조급함을 버리십시오.",
]

LOVE_POOL = [
    "가족·인연의 운이 따뜻한 흐름입니다. 작은 안부 한 마디가 큰 다리가 됩니다.",
    "오래된 갈등이 자연스레 풀리는 날입니다. 먼저 손 내미시는 분이 복을 받습니다.",
    "자녀·후배와의 대화가 큰 기쁨을 줍니다. 듣는 자리에 머무르시면 더 좋습니다.",
    "묵은 인연이 다시 연결되는 흐름입니다. 옛 친구의 안부 전화에 반갑게 답하십시오.",
    "배우자·연인과의 신뢰가 깊어지는 시기입니다. 함께 보내는 시간이 가장 큰 약이 됩니다.",
    "외로움이 자연스레 풀리는 날입니다. 모임·산책 한 번이 큰 인연을 부릅니다.",
]

HEALTH_POOL = [
    "건강은 무리만 하지 않으면 평탄합니다. 따뜻한 차 한 잔이 큰 약이 됩니다.",
    "허리·무릎 관리가 필요한 시기입니다. 가벼운 산책을 거르지 마십시오.",
    "수면이 가장 큰 보약입니다. 일찍 잠자리에 드시면 다음날이 가볍습니다.",
    "소화기 관리에 신경 쓰시면 좋습니다. 따뜻한 음식이 가장 좋은 약입니다.",
    "마음의 안정이 곧 건강입니다. 잠깐의 명상·기도가 큰 힘이 됩니다.",
    "정기 검진을 미루셨다면 이번 주 안에 받으시는 것이 길합니다.",
]

TIP_POOL = [
    "오늘의 행운 색: 푸른색 / 행운 방향: 동쪽",
    "오늘의 행운 색: 붉은색 / 행운 방향: 남쪽",
    "오늘의 행운 색: 노란색 / 행운 방향: 중앙",
    "오늘의 행운 색: 흰색 / 행운 방향: 서쪽",
    "오늘의 행운 색: 검은색 / 행운 방향: 북쪽",
    "오늘의 행운 색: 보라색 / 행운 방향: 남서쪽",
]

LUCKY_NUMS = ["3, 17", "5, 21", "7, 29", "9, 33", "2, 14", "6, 24", "8, 38", "4, 18"]

# 생년별 한 줄 운세 풀 (시니어 친화 조언·격려 톤)
YEAR_POOL = [
    "건강을 먼저 챙기시면 만사가 순조롭습니다.",
    "오랜 노력이 결실을 맺으니 기대하셔도 좋습니다.",
    "가족과의 대화에서 뜻밖의 위로를 얻습니다.",
    "재물운이 서서히 열리니 작은 기회를 살피세요.",
    "서두르지 않으면 막혔던 일이 자연히 풀립니다.",
    "주변의 조언이 큰 도움이 되는 날입니다.",
    "마음의 여유가 행운을 부릅니다.",
    "옛 인연에게서 반가운 소식이 올 수 있습니다.",
    "작은 베풂이 큰 복으로 돌아옵니다.",
    "활동을 조금 줄이고 휴식하면 활력이 살아납니다.",
    "신중한 결정이 좋은 결과로 이어집니다.",
    "긍정적인 마음가짐이 하루를 빛나게 합니다.",
    "금전 거래는 한 번 더 살펴보면 탈이 없습니다.",
    "먼저 손 내미는 분에게 복이 따릅니다.",
]


@dataclass
class ZodiacReading:
    sign_slug: str
    sign_ko: str
    branch: str
    years: List[str]
    date_iso: str          # 2026-05-16
    date_ko: str           # 2026년 5월 16일
    overall: str
    money: str
    love: str
    health: str
    tip: str
    lucky_num: str
    title: str
    description: str
    emoji: str
    overall_score: int
    money_score: int
    love_score: int
    health_score: int
    year_list: List[dict]


def _seed(sign_slug: str, date_iso: str) -> int:
    h = hashlib.sha256(f"{sign_slug}|{date_iso}".encode()).hexdigest()
    return int(h[:8], 16)


def _pick(pool: list, seed: int, offset: int) -> str:
    return pool[(seed + offset) % len(pool)]


def _score(seed: int, offset: int) -> int:
    # 3~5 긍정 편향 (결정론적). 시니어 시청자 기분 좋게.
    return 3 + ((seed >> (offset * 4)) % 3)


def make_reading(sign_slug: str, date_iso: str | None = None) -> ZodiacReading:
    if sign_slug not in SLUG_TO_INFO:
        raise ValueError(f"unknown sign: {sign_slug}")
    if not date_iso:
        date_iso = dt.date.today().isoformat()
    _, sign_ko, branch, years = SLUG_TO_INFO[sign_slug]
    d = dt.date.fromisoformat(date_iso)
    date_ko = f"{d.year}년 {d.month}월 {d.day}일"
    seed = _seed(sign_slug, date_iso)

    overall = _pick(OVERALL_POOL, seed, 0)
    money = _pick(MONEY_POOL, seed, 1)
    love = _pick(LOVE_POOL, seed, 2)
    health = _pick(HEALTH_POOL, seed, 3)
    tip = _pick(TIP_POOL, seed, 4)
    lucky_num = _pick(LUCKY_NUMS, seed, 5)

    emoji = SIGN_EMOJI.get(sign_slug, "🔮")
    money_score = _score(seed, 1)
    love_score = _score(seed, 2)
    health_score = _score(seed, 3)
    overall_score = round((money_score + love_score + health_score) / 3)

    year_list = []
    for y in years:
        # 1920·1930년대생(고령) + 2020년대생(영유아) 제외.
        # 두자리 표기(예: 26년생) 1926/2026 혼동 방지.
        if int(y) < 1940 or int(y) >= 2020:
            continue
        ys = _seed(f"{sign_slug}{y}", date_iso)
        year_list.append({"year": y, "yy": y[2:], "text": _pick(YEAR_POOL, ys, 0)})

    title = f"{date_ko} {sign_ko} 오늘의 운세 — 재물·연애·건강 총정리"
    description = f"{date_ko} {sign_ko} 운세: {overall[:60]}…"

    return ZodiacReading(
        sign_slug=sign_slug,
        sign_ko=sign_ko,
        branch=branch,
        years=years,
        date_iso=date_iso,
        date_ko=date_ko,
        overall=overall,
        money=money,
        love=love,
        health=health,
        tip=tip,
        lucky_num=lucky_num,
        title=title,
        description=description,
        emoji=emoji,
        overall_score=overall_score,
        money_score=money_score,
        love_score=love_score,
        health_score=health_score,
        year_list=year_list,
    )


def all_signs() -> list:
    return [{"slug": z[0], "ko": z[1], "branch": z[2], "years": z[3]} for z in ZODIAC]


def today_iso() -> str:
    # KST(UTC+9) 기준. Render 서버는 UTC라 한국 새벽에 전날로 어긋나는 것 방지.
    return (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=9)).date().isoformat()
