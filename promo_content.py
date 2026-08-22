"""대박운세 정통명리엔진 홍보 콘텐츠.

띠별운세(매일)와 완전히 분리된 홍보 라인이다. 매일 도는 파이프라인에 홍보물이 섞이면
스팸으로 잡히므로, 발행은 **주 1회(토요일 오전)** 로만 돌린다.

2026-08-22 기준, 하루·1주일·30일 무제한 이용권은 종료됐다. 모든 홍보물에서 해당
혜택·가격·구독 비교를 제거한다. 대신 정통명리엔진의 실제 처리 흐름(만세력 계산,
일간·오행·십신·용신·대운·세운 해석)과 무료 십성 유형, 1,000원 개인 풀이를 설명한다.

표현 규칙 (표시광고법 안전):
  · "가장 정확한", "차원이 다르다", "100%", "반드시" 같은 우월·단정 표현을 쓰지 않는다.
  · 생성형 AI를 비방하지 않고, "생성형 문장 조합만으로 끝내지 않는다"처럼 제품의
    구현 방식을 설명한다.
  · 사주명리 해석은 참고용이며 미래 결과를 보장하지 않는다는 점을 캡션에 밝힌다.

TTS 대본 규칙: 숫자는 한글로, 기호는 말로 풀어서, 한 줄 50자 이내, 한자 없음.
"""
from __future__ import annotations

# 카드 공통 톤 — 기존 띠별운세 카드와 통일한다.
STYLE = (
    "Korean traditional-modern editorial card, deep navy (#1a2340) background, "
    "soft gold and warm ivory accents, subtle traditional Korean pattern at edges, "
    "clean minimal composition, generous margins, no human faces, no logos, "
    "high text readability, 4:5 portrait"
)

CTA_TEXT = "정통명리엔진 풀이 · 프로필 링크"


def _card(file: str, headline: str, sub: str, extra: str = "") -> dict:
    """카드 1장 = 큰 제목 + 보조 문구. 프롬프트는 Topview(GPT Image 2)에 그대로 들어간다."""
    body = f'Korean headline text "{headline}" in large bold letters, ' \
           f'smaller Korean subtext "{sub}"'
    if extra:
        body += f", {extra}"
    return {"file": file, "headline": headline, "sub": sub,
            "prompt": f"{STYLE}. {body}."}


# ── 정통명리엔진: 새 홍보 기본 세트 ────────────────────────────────
SET_ENGINE = {
    "key": "engine",
    "title": "내 십성 유형, 무료로 확인",
    "caption": (
        "나는 사주에서 어떤 십성 유형일까요?\n\n"
        "대박운세의 정통명리엔진은 생년월일시를 바탕으로 만세력에서 명식을 세운 뒤,\n"
        "일간·오행·십신·용신과 대운·세운의 관계를 순서대로 계산합니다.\n"
        "내 십성 유형 확인은 무료입니다.\n"
        "더 깊이 묻고 싶다면 1,000원으로 내 사주를 바탕으로 한 AI 상담 3회를 바로 이어갈 수 있습니다.\n\n"
        "내 사주의 구조와 흐름을 정통명리엔진으로 확인해보세요.\n"
        "※ 전통 사주명리학을 바탕으로 한 참고용 해석이며 미래를 보장하지 않습니다."
    ),
    "cards": [
        _card("01_표지", "내 십성 유형, 무료로 확인", "내 사주에서 가장 강한 기운은 무엇일까"),
        _card("02_만세력", "만세력으로 사주팔자 계산", "생년월일시에서 천간과 지지까지"),
        _card("03_구조", "일간 · 오행 · 십신", "타고난 명리 구조를 읽습니다"),
        _card("04_유형", "열 가지 십성 유형", "살림꾼 · 해결사 · 재주꾼, 나는 어디에 가까울까"),
        _card("05_차이", "계산한 근거 위에서 해석", "생성형 문장 조합만으로 끝내지 않습니다"),
        _card("06_CTA", "내 사주 AI 상담 3회", "1,000원 · 프로필 링크"),
    ],
    "narration": [
        "내 사주에서 가장 강한 십성은 무엇일까요?",
        "대박운세는 먼저 만세력으로 사주팔자를 계산합니다.",
        "일간과 오행, 십신으로 내 명리 구조를 읽습니다.",
        "열 가지 십성 유형 중 나와 가까운 유형을 무료로 확인해 보세요.",
        "계산한 근거 위에서 해석합니다. 생성형 문장 조합만으로 끝내지 않습니다.",
        "더 깊이 묻고 싶다면 내 사주 AI 상담 세 회를 천 원으로 이어가세요.",
    ],
}

# ── 네이버 블로그 삽화 (월 1회 · 일요일 07시) ────────────────────
# 카드와 달리 글자를 넣지 않는다. 본문을 읽는 흐름을 끊지 않는 순수 삽화다.
BLOG_STYLE = (
    "Korean traditional ink-wash painting blended with soft modern illustration, "
    "muted indigo and warm ivory palette, delicate gold line accents, "
    "serene and dignified mood, generous negative space, no text, no letters, "
    "no watermark, no human faces in close-up, 4:3 landscape"
)

BLOG_IMAGES = [
    {
        "file": "blog_01_dawn",
        "alt": "새벽 산사에 해가 드는 풍경",
        "prompt": f"{BLOG_STYLE}. Dawn light spreading over a quiet Korean mountain "
                  f"temple, pine trees in mist, a single lantern still lit, "
                  f"the first sun touching tiled roofs.",
    },
    {
        "file": "blog_02_manseryeok",
        "alt": "만세력 서책과 붓, 먹",
        "prompt": f"{BLOG_STYLE}. An old Korean almanac book opened on a low wooden desk, "
                  f"brush and ink stone beside it, faint grid of celestial stems and branches "
                  f"on the page, warm afternoon light from a paper window.",
    },
    {
        "file": "blog_03_evening",
        "alt": "저녁 창가에서 하루를 돌아보는 자리",
        "prompt": f"{BLOG_STYLE}. A quiet evening scene by a traditional paper window, "
                  f"a cup of tea and a small notebook on the floor desk, "
                  f"moonlight and soft shadow, sense of looking back on the day calmly.",
    },
]

SETS = [SET_ENGINE]
BY_KEY = {s["key"]: s for s in SETS}


def pick_set(week_index: int) -> dict:
    """주차로 3세트를 순환한다. 같은 소재가 연속으로 나가지 않는다."""
    return SETS[week_index % len(SETS)]
