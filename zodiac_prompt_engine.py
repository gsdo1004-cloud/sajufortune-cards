"""띠별운세 이미지 프롬프트 '다양성' 엔진 — v2 (2026-08-10 4장 체제).

핵심 철학 (한밝님 2026-07-17): 매일 다른 화풍·배경·컨셉·색감·소품이라야
독자가 질리지 않고 재미있게 본다. 여러 축을 서로 다른 주기로 순환시켜
조합을 폭발시킨다(사실상 매일 유니크). 결정론적(날짜 기반) = 재현 가능.

v2 변경 (한밝님 지시):
  - 하루 기본 4장: 띠별 3장(각 4띠) + 12띠요약 1장 — 전부 9:16, GPT Image 2 1K
  - 각 장에 simple(단순화) 폴백 프롬프트 동봉 — 생성 실패 시 재시도용
    (텍스트는 동일하게 유지하고 장식 요소만 줄여 성공률을 높인다)
  - 띠별 장: 띠 4줄 × (한 줄 운세 + 별점 4항목 전체/금전/연애/건강)
"""
from __future__ import annotations
import datetime as dt

# ─────────────────────────────────────────────────────────────
# 다양성 축 — 각 축이 독립 순환하여 조합 폭발
# ─────────────────────────────────────────────────────────────

ART_STYLES = [
    ("수채화",     "clean 2D watercolor illustration, crisp outlines, gentle warm washes"),
    ("민화 평면",  "clean 2D Korean folk-art illustration, vivid symbolic colors, crisp decorative shapes"),
    ("수묵 담채",  "clean 2D Korean ink-and-light-wash illustration, elegant brushstrokes, warm accents"),
    ("동화책",     "clean 2D storybook illustration, soft hand-drawn lines, friendly rounded shapes"),
    ("따뜻한 선화", "clean 2D line-art illustration, warm golden palette, soft flat shading"),
    ("파스텔",     "clean 2D pastel illustration, gentle gradients, charming rounded details"),
    ("민화 색감",  "clean 2D Korean folk-art illustration, bright obangsaek-inspired colors, neat shapes"),
    ("파스텔 애니","clean 2D pastel animation illustration, cute expressive eyes, gentle shading"),
    ("판타지 동화","clean 2D fantasy storybook illustration, soft glow, warm magical accents"),
    ("색연필",     "clean 2D colored-pencil storybook illustration, cozy paper texture, crisp silhouettes"),
    ("종이공예",   "clean 2D paper-cut illustration, clear layered shapes, soft warm shadows"),
    ("빈티지 평면", "clean 2D vintage poster illustration, warm nostalgic palette, crisp simple forms"),
]

BACKGROUNDS = [
    ("전통 산수",  "traditional Korean mountain landscape with pine trees and drifting mist"),
    ("우주 별자리","cosmic starry night sky with constellations and a softly glowing galaxy"),
    ("봄 벚꽃",    "spring cherry-blossom garden with drifting pink petals"),
    ("여름 바다",  "bright summer seaside with gentle turquoise waves and a warm sun"),
    ("가을 단풍",  "autumn maple grove glowing with red and gold foliage"),
    ("겨울 설경",  "serene winter snowscape with soft falling snow and warm light"),
    ("황금 궁전",  "ornate auspicious golden palace setting, grand and lucky"),
    ("천상 구름",  "heavenly sea of clouds with a rainbow and celestial light rays"),
    ("한옥 마을",  "cozy traditional hanok village with tiled roofs and paper lanterns"),
    ("꽃밭 정원",  "blooming flower garden with fluttering butterflies"),
    ("등불 축제",  "warm night lantern festival with floating glowing lanterns"),
    ("연꽃 연못",  "tranquil lotus pond at dawn with lily pads and soft ripples"),
    # 2026-07-25 +1 — 길이를 13으로 만들어 스타일(12)과 서로소가 되게 한다. 아래 주석 참고.
    ("대나무 숲",  "quiet green bamboo grove with dappled sunlight and drifting leaves"),
]

# ⚠️ 축 길이는 서로 서로소로 유지할 것 (2026-07-25)
# 문제: 스타일·배경이 둘 다 길이 12라 stride를 줘도 짝이 고정됐다.
#       종이공예→봄벚꽃, 빈티지→천상구름 … 이 짝이 영원히 유지되고 12일마다 같은 그림이 나왔다.
#       ("매일 똑같은 그림이 반복된다"는 피드백의 실제 원인)
# 해결: 길이를 12·13·11·7·13·5 로 벌렸다. 최소공배수가 6만 일을 넘어 사실상 반복이 없다.
#       축을 늘리거나 줄일 때 길이가 서로 나누어떨어지지 않는지 꼭 확인할 것.

CONCEPTS = [
    ("한복 여성",  "the woman remains in elegant hanbok while every zodiac mascot stays a natural animal"),
    ("전통 정원",  "in a bright traditional Korean garden with flowers and soft sunlight"),
    ("산뜻한 나들이","in a cheerful outdoor Korean spring setting with clear warm light"),
    ("등불 한옥",  "with warm hanok lanterns, auspicious clouds, and a welcoming glow"),
    ("꽃바구니",   "with flowers and a small lucky pouch as gentle Korean scene accents"),
    ("연꽃 연못",  "beside a tranquil lotus pond with soft ripples and warm dawn light"),
    ("전통 놀이",  "in a bright Korean courtyard with simple folk-play props in the background"),
    ("명절 풍경",  "near a festive hanok courtyard with flowers and clean Korean decorative accents"),
    # 2026-07-25 +3 → 길이 11 (소수)
    ("차 한잔",    "near a cozy traditional tea table, with the animals remaining separate natural animals"),
    ("달구경",     "in a quiet moonlit hanok garden with soft flowers and gentle wonder"),
    ("악사·풍류",  "near small traditional folk instruments used only as background decoration"),
]

PALETTES = [
    ("황금 길상",  "auspicious gold, red and warm lucky palette"),
    ("오방색",     "traditional Korean five-direction obangsaek colors"),
    ("파스텔 몽환","soft dreamy pastel palette"),
    ("무지개 밝음","bright cheerful rainbow palette"),
    ("청록 신비",  "mystic teal, indigo and violet palette"),
    ("노을 따뜻",  "warm amber sunset palette"),
    ("먹빛 담채",  "restrained ink-and-light-wash palette with subtle color accents"),  # +1 → 7
]

PROPS = [
    "gold lucky pouch (복주머니)", "shiny old coins (엽전)", "four-leaf clovers",
    "a lucky talisman (부적)", "a blooming lotus", "brush and scroll",
    "a glowing lantern", "a bright full moon", "an elegant crane", "auspicious clouds",
    "a peach of longevity", "a small treasure chest",
    "a decorated folding fan (부채)",                                   # +1 → 13
]

# 그룹(띠별 3장) 구도 축 — 2026-07-20 추가.
# 근거: G:\내 드라이브\01클로드\작업폴더\집PC이관_PNGTuber_2026-07-20\
#       2026-07-20_12지신운세_이미지프롬프트_개선가이드_v1.md
# TTS가 운세를 전부 읽어주므로 화면이 정보를 도식적으로 재전달할 필요가 없다(redundancy
# effect) → group_prompt의 "표 형태(동물 좌/텍스트 우, 3단 나열)"를 무드 비주얼로 교체.
GROUP_COMPOSITIONS = [
    ("디오라마 병치", "arranged as a diorama of small independent vignette scenes placed "
                    "side by side, each animal fully absorbed in its own tiny setting"),
    ("원형 배치",     "arranged gently around a soft circular formation, each animal "
                    "occupying its own graceful position along the circle"),
    ("부채꼴 배열",   "fanned out like an open folding fan, each animal in its own "
                    "elegant position across the gentle arc"),
    # 2026-07-25 +2 → 길이 5. 3개일 땐 같은 배치가 4~5일씩 이어져 지루했다.
    ("층층 계단식",   "placed on gentle stepped tiers at different heights, like a "
                    "traditional stone stairway, each animal on its own level"),
    ("중앙 집합",     "gathered warmly toward a glowing center point, leaning in "
                    "together as if sharing one lantern"),
]

WEEKDAY_KR = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]

# 12지신 (표준 순서) — 하루 4장 = 4띠씩 3그룹 + 12띠요약
ZODIAC12 = ["쥐띠", "소띠", "호랑이띠", "토끼띠", "용띠", "뱀띠",
            "말띠", "양띠", "원숭이띠", "닭띠", "개띠", "돼지띠"]
ZODIAC_EN = {
    "쥐띠": "rat", "소띠": "ox", "호랑이띠": "tiger", "토끼띠": "rabbit",
    "용띠": "dragon", "뱀띠": "snake", "말띠": "horse", "양띠": "sheep",
    "원숭이띠": "monkey", "닭띠": "rooster", "개띠": "dog", "돼지띠": "pig",
}

# 공통 베이스: 한복 여성과 동물의 몸을 분리해 명시하고, 띠별 외형은 변수로 주입한다.
ZODIAC_COMMON_BASE = (
    "A beautiful Korean woman wearing elegant hanbok stands with separate cute and friendly "
    "zodiac animal mascots. The woman has a normal human body; every zodiac mascot has its "
    "own complete natural animal body and unmistakable species features. Adorable mascot style, "
    "strict flat 2D editorial illustration, crisp linework, simple flat shading, "
    "no dimensional rendering, no glossy CGI, bright warm Korean aesthetic, "
    "harmonious composition, charming friendly expressions, anatomically clean and visually appealing."
)
ZODIAC_FEATURES = {
    "쥐띠": "a small nimble rat with round ears, tiny paws, whiskers, and curious bright eyes",
    "소띠": "a sturdy gentle ox with a broad build, soft muzzle, and calm kind eyes",
    "호랑이띠": "a lively tiger with clear black stripes, rounded paws, alert eyes, and a gentle expression",
    "토끼띠": "a lovable rabbit with long ears, round cheeks, fluffy tail, and soft bright eyes",
    "용띠": "a small friendly East Asian dragon with four legs, soft scales, tiny horns, short wings, and a curling tail",
    "뱀띠": "a softly rounded snake with clear scales, gentle bright eyes, and no limbs",
    "말띠": "a bright healthy horse with a clear equine head, flowing mane, four legs, and lively eyes",
    "양띠": "a fluffy gentle sheep with soft wool, small curved horns, rounded face, and kind eyes",
    "원숭이띠": "a clearly animal-shaped clever monkey with brown fur, rounded ears, long curling tail, and playful eyes",
    "닭띠": "a lively rooster with red comb, colorful feathers, wings, two legs, clear beak, and bright eyes",
    "개띠": "a friendly Korean Jindo-style dog with fluffy tail, pointed ears, soft muzzle, and loyal bright eyes",
    "돼지띠": "a round plump adorable pig with pink snout, floppy ears, tiny hooves, and joyful bright eyes",
}
ZODIAC_NEGATIVE_PROMPT = (
    "no anthropomorphic human-animal hybrids, no human body for zodiac animals, no humanized animals, "
    "no humanoid form, no malformed face, no distorted limbs, no extra limbs, no creepy anatomy, "
    "no grotesque features, no fused bodies, no animal face on a human body, no scary or horror features, "
    "no photorealism, no 3D render, no glossy CGI"
)


def _zodiac_feature_guide(signs: list[str]) -> str:
    return "; ".join(
        f"{ZODIAC_EN.get(sign, 'animal')}: {ZODIAC_FEATURES.get(sign, 'a cute natural animal mascot')}"
        for sign in signs
    )


GROUP_NAMES = ["띠별A", "띠별B", "띠별C"]
GROUPS = [ZODIAC12[i * 4:(i + 1) * 4] for i in range(3)]   # 4띠 × 3장


def _pick(date: dt.date, axis: list, period: int = 1, stride: int = 1):
    """날짜 기반 결정론적 선택. period=순환 주기(클수록 천천히 바뀜),
    stride=인덱스 보폭(다른 축과 길이가 같아도 stride를 다르게 주면 인덱스가
    어긋나 조합이 겹치지 않는다 — 2026-07-20, 아래 daily_theme 주석 참고)."""
    idx = ((date.toordinal() // period) * stride) % len(axis)
    return axis[idx]


def daily_theme(date: dt.date) -> dict:
    """오늘의 다양성 조합. 각 축을 다른 주기로 돌려 반복을 최대한 늦춘다."""
    o = date.toordinal()
    return {
        "style":       _pick(date, ART_STYLES, 1),           # 매일 바뀜(기준 축)
        # ⚠️2026-07-20 수정: style·bg 둘 다 period=1·길이12라 인덱스가 항상 같았음
        # (idx=o%12 동일) → "화풍과 다른 배열이라 어긋나며 순환"은 잘못된 가정이었고
        # 실제로는 화풍+배경 조합이 12일마다 그대로 반복되고 있었다. stride로 보폭을
        # 어긋나게 해 실제 다른 조합이 나오게 함(palette도 동일 문제라 같이 수정).
        "bg":          _pick(date, BACKGROUNDS, 1, stride=5),  # 매일, 화풍과 다른 보폭(5, 12와 서로소)
        "concept":     _pick(date, CONCEPTS, 2),               # 2일마다
        "palette":     _pick(date, PALETTES, 1, stride=5),     # 매일, 화풍과 다른 보폭(5, 6과도 서로소)
        "props":       [PROPS[(o * 5 + i * 7) % len(PROPS)] for i in range(2)],
        "composition": _pick(date, GROUP_COMPOSITIONS, 5),     # 5일마다(그룹 3장 카드 구도)
        "weekday":     WEEKDAY_KR[date.weekday()],
        "date_kr":     f"{date.month}월 {date.day}일",
    }


_SNAKE_GUARD = "The snake must be a cute natural snake with a softly rounded body and no limbs, never realistic or scary."
_NEG = (f"Negative prompt: {ZODIAC_NEGATIVE_PROMPT}. "
        "No watermark, no logo, crisp clean readable Korean typography. "
        "Render ONLY the Korean strings given above, exactly as written — "
        "do not invent or add any other Korean text.")


def stars_line(s: dict) -> str:
    """별점 4항목 문자열. s = {'전체':4,'금전':3,'연애':5,'건강':4}"""
    def st(n):
        n = max(1, min(5, int(n)))
        return "★" * n + "☆" * (5 - n)
    return "  ".join(f"{k} {st(s[k])}" for k in ("전체", "금전", "연애", "건강"))


def cover_prompt(date: dt.date, theme: dict | None = None, simple: bool = False) -> str:
    """표지(섬네일) 프롬프트: 오늘의 운세 + 날짜 + 12지신."""
    t = theme or daily_theme(date)
    guide = _zodiac_feature_guide(ZODIAC12)
    deco = (f"Background: {t['bg'][1]}. Lucky props scattered: {', '.join(t['props'])}. "
            if not simple else
            "Background: soft plain auspicious gradient with gentle light rays. ")
    return (
        f"Vertical 9:16 Korean daily fortune COVER poster. "
        f"Large bold clean Korean title '오늘의 운세' at top center, "
        f"date '{t['date_kr']} {t['weekday']}' clearly just below. "
        f"{ZODIAC_COMMON_BASE} All twelve cute Korean zodiac animals (rat, ox, tiger, rabbit, dragon, snake, "
        f"horse, sheep, monkey, rooster, dog, pig) are gently arranged in a soft "
        f"circular mandala-wheel formation around the title, each animal in its own graceful "
        f"position along the circle — not a grid, not stacked rows. Species guide: {guide}. "
        f"Scene accents: {t['concept'][1]}. "
        f"{deco}"
        f"{t['palette'][1]}. Art style: {t['style'][1]}. "
        f"{_SNAKE_GUARD} Warm auspicious festive lucky mood. {_NEG}"
    )


def group_prompt(date: dt.date, rows: list[dict], theme: dict | None = None,
                 simple: bool = False) -> str:
    """띠별 4띠 프롬프트. rows = [{ko, line, stars:{전체,금전,연애,건강}}] 4개.

    2026-07-20: "동물 좌/텍스트 우" 3단 표 형태(도식적 나열)를 무드 비주얼 구도로
    교체. 근거·배경은 GROUP_COMPOSITIONS 선언부 주석 참고.
    """
    t = theme or daily_theme(date)
    animals = ", ".join(ZODIAC_EN.get(r["ko"], r["ko"]) for r in rows)
    guide = _zodiac_feature_guide([r["ko"] for r in rows])
    comp = t.get("composition") or GROUP_COMPOSITIONS[0]
    secs = ""
    for i, r in enumerate(rows, 1):
        en = ZODIAC_EN.get(r["ko"], "animal")
        feature = ZODIAC_FEATURES.get(r["ko"], "a cute natural animal mascot")
        secs += (f"Vignette {i} — a cute {en} zodiac mascot ({feature}) labeled '{r['ko']}' in elegant small "
                 f"Korean type, its one-line fortune '{r['line']}' and star line "
                 f"'{stars_line(r['stars'])}' gently placed beside it, not boxed or tabled. ")
    deco = (f"Background: {t['bg'][1]}. " if not simple else
            "Background: soft plain auspicious gradient. ")
    guard = _SNAKE_GUARD + " " if any(r["ko"] == "뱀띠" for r in rows) else ""
    return (
        f"Vertical 9:16 Korean zodiac fortune card, atmospheric mood illustration — "
        f"NOT an infographic, NOT a chart, NOT a table. "
        f"Top title '오늘의 띠별운세' bold clean Korean, small date '{t['date_kr']} {t['weekday']}'. "
        f"{ZODIAC_COMMON_BASE} Four animals ({animals}, in order) {comp[1]}. "
        f"Species guide: {guide}. "
        f"{secs}"
        f"Scene accents: {t['concept'][1]}. {deco}"
        f"{t['palette'][1]}. Art style: {t['style'][1]}. "
        f"{guard}{_NEG}"
    )


def summary12_prompt(date: dt.date, rows_by_ko: dict[str, dict],
                     theme: dict | None = None, simple: bool = False) -> str:
    """12띠 전부를 한 장에 담은 '일시정지해서 읽는' 요약 카드 (A/B 10초판용).

    근거(2026-07-17 경쟁사 실측): 조회수 상위 운세 쇼츠는 전부 6~11초이고, 12띠를
    한 화면에 띄워 시청자가 **일시정지해 자기 띠를 찾게** 만든다 → 완주율이 100%를
    넘어 알고리즘에 유리. 우리 95초판은 자기 띠가 나오면 이탈한다.

    밀도 = 한밝님 레퍼런스 카드(2026-07-17) 구조: 셀마다 띠명 + 2줄 운세 + 행운 +
    운세지수. GPT Image 2가 작은 글씨도 버틴다는 실증. ⚠️ 12셀 밀도에선 글자 결손이
    가끔 나오지만 **한밝님 판단: 오타 한두 개는 문제 없음** — 밀도를 우선한다.

    rows_by_ko[ko] = {line, stars{전체..}, lucky(색·방향), keyword}
    """
    t = theme or daily_theme(date)
    guide = _zodiac_feature_guide(ZODIAC12)
    rows = ""
    for i in range(0, 12, 3):
        cells = []
        for ko in ZODIAC12[i:i + 3]:
            r = rows_by_ko.get(ko) or {}
            n = max(1, min(5, int((r.get("stars") or {}).get("전체", 4))))
            cells.append(
                f"[{ko}: fortune text '{r.get('advice') or r.get('line', '')}' / "
                f"'행운 {r.get('lucky', '')}' / '운세지수 {'★' * n}{'☆' * (5 - n)}']")
        rows += f"Row{i // 3 + 1}: " + "  ".join(cells) + "\n"
    deco = (f"Background: {t['bg'][1]}. " if not simple else
            "Background: soft plain auspicious gradient. ")
    return (
        f"Vertical 9:16 Korean daily zodiac fortune SUMMARY card showing ALL TWELVE "
        f"zodiac signs at once, designed to be paused and read. "
        f"Top title '오늘의 띠별운세' bold, with date badge '{t['date_kr']} ({t['weekday']})' below it. "
        f"Then a clean 3-column x 4-row grid of twelve rounded cells. In EACH cell: a small cute "
        f"zodiac animal on the left; on the right its Korean name in bold color, below it the "
        f"fortune sentence in SMALL but crisp readable Korean (wrap to 2-3 short lines), and at "
        f"the cell bottom a thin divider with '행운' keywords on the left and '운세지수' stars on "
        f"the right. Exact contents:\n{rows}"
        f"{ZODIAC_COMMON_BASE} All twelve animals are cute and friendly. Species guide: {guide}. "
        f"Scene accents: {t['concept'][1]}. {_SNAKE_GUARD} "
        f"{deco}Bright clean editorial layout, generous padding, soft card shadows, "
        f"{t['palette'][1]}. Every Korean line must be sharp and legible on a phone. "
        f"Art style: {t['style'][1]}. {_NEG}"
    )


# ── 소수 지목형 카드 (2026-07-26) ────────────────────────────
# 근거: 벤치마크 채널 `별빛 운세 정원` 실측 — 12띠를 다 보여준 13초 영상 7,579뷰 vs
# 출생년을 **소수만 지목**한 19초 영상 13,247뷰(구독 1,170 대비 11.3배, 좋아요율 7.0%).
# 이긴 쪽은 길이가 더 길다 → 변수는 길이가 아니라 "내가 해당되나?"였다.
# 12띠를 한 화면에 다 띄우면 시청자는 자기 띠만 보고 이탈한다(평균 1/12 지점).
# 3띠만 담으면 셀이 커져 글씨도 커진다 = "글자를 못 읽는다"(7/25 시청자 피드백)도 같이 해결.
# ⚠️ 화법: 벤치마크 채널의 `운 폭발`류 과장은 쓰지 않는다. 운명과학TV는 허위콘텐츠
#    수익정지 이력이 있어 `오늘 흐름이 좋은 띠` 수준으로 낮춘다.
PICK3_TITLE = "오늘 흐름이 좋은 띠"
PICK3_N = 3

# 주제 로테이션 — "오늘 흐름 좋은 띠" 하나만 매일 반복하면 후크가 닳는다.
# 기간(오늘·이번주·이달)과 축(총운·재물·인연·건강)을 섞어 매번 다른 질문을 던진다.
# scope=week/month는 그 기간의 일별 점수를 **평균**해 뽑는다 → 같은 주·같은 달 안에서는
# 결과가 안정적이라 "이달의 띠"가 날마다 바뀌는 이상한 일이 생기지 않는다.
PICK3_THEMES = [
    {"key": "day_overall", "scope": "day", "axis": "overall",
     "title": "오늘 흐름이 좋은 띠",
     "hook": "오늘 흐름이 좋은 띠, 세 띠만 짚어 드립니다."},
    {"key": "day_money", "scope": "day", "axis": "money",
     "title": "오늘 재물 기운이 좋은 띠",
     "hook": "오늘 재물 쪽으로 기운이 도는 띠가 셋 있습니다."},
    {"key": "week_overall", "scope": "week", "axis": "overall",
     "title": "이번 주 흐름이 좋은 띠",
     "hook": "이번 주 남은 날들을 놓고 보면, 흐름이 좋은 띠가 셋 있습니다."},
    {"key": "day_love", "scope": "day", "axis": "love",
     "title": "오늘 인연 기운이 좋은 띠",
     "hook": "오늘 사람 인연이 반가운 띠, 세 띠입니다."},
    {"key": "month_overall", "scope": "month", "axis": "overall",
     "title": "이달 흐름이 좋은 띠",
     "hook": "이번 달 남은 흐름이 좋은 띠를 뽑아 봤습니다."},
    {"key": "day_health", "scope": "day", "axis": "health",
     "title": "오늘 몸이 가벼운 띠",
     "hook": "오늘 몸과 마음이 가벼운 띠를 짚어 드립니다."},
]
_AXIS_FIELD = {"overall": "overall_score", "money": "money_score",
               "love": "love_score", "health": "health_score"}


def _pick3_reading_text(sign_ko: str, date: dt.date, axis: str) -> str:
    """지목 카드 문구를 사주v6 정본 make_reading에서 가져온다.

    rows_by_ko는 카드 레이아웃용으로 이미 짧아진 값일 수 있다. 지목형은 별도
    문구를 다시 만들지 않고, 반드시 날짜별 간지×띠 관계를 계산한 정본 결과에서
    축(총운·재물·인연·건강)에 맞는 한 문장을 선택한다.
    """
    import zodiac_seo as zs
    from ganzhi_zodiac import zodiac_day

    slug = zs.KO_TO_SLUG[sign_ko]
    reading = zs.make_reading(slug, date.isoformat())
    if axis == "overall":
        ctx = zodiac_day(slug, date)
        prefix = f"오늘은 {ctx['day_pillar']}일, "
        text = (reading.overall[len(prefix):]
                if reading.overall.startswith(prefix) else reading.overall)
    else:
        text = getattr(reading, axis, reading.overall)
    text = " ".join(str(text).split()).strip()
    return (text.split(". ", 1)[0].rstrip(".")
            if text else "오늘의 흐름을 차분히 살펴보세요")


# ── 20초판 포맷 로테이션 (2026-07-26) ────────────────────────
# 한 가지만 매일 반복하면 유튜브 정책 필터에 양산물로 잡히기 쉽다 → 성격이 다른 3종.
#   pick3   = 3띠 지목형   — 완주율용. "내가 해당되나?"로 끝까지 붙잡는다
#   table12 = 표형 12띠    — 일시정지해 읽는 정보형. 로컬 렌더라 한글이 100% 정확
#   ai12    = 기존 AI 12띠 — 그림 카드. 화풍이 매일 바뀌어 비주얼 변주 담당
# 여기(프롬프트 엔진)에 두는 이유: 이미지 생성 단계에서 "오늘 지목 카드가 필요한가"를
# 알아야 필요 없는 날 Topview 크레딧을 안 태운다. zodiac_shorts가 이걸 그대로 쓴다.
SHORTS_FORMATS = ["pick3", "table12", "ai12"]


def shorts_format(date_iso: str) -> str:
    """그날 20초판 포맷. 날짜 결정론 — 재조립해도 같은 포맷이 나온다."""
    import os
    forced = os.environ.get("ZODIAC_SHORTS_FORMAT")
    if forced in SHORTS_FORMATS:
        return forced
    return SHORTS_FORMATS[dt.date.fromisoformat(date_iso).toordinal() % len(SHORTS_FORMATS)]


def pick3_theme(date: dt.date) -> dict:
    """그날 지목형 주제. 날짜 결정론 — 카드(D+2에 생성)와 영상·제목이 어긋나면 안 된다."""
    import os
    forced = os.environ.get("ZODIAC_PICK3_THEME")
    for t in PICK3_THEMES:
        if t["key"] == forced:
            return t
    t = PICK3_THEMES[date.toordinal() % len(PICK3_THEMES)]
    # 월말·주말엔 기간이 며칠 안 남아 "이달 흐름"이 사실상 하루가 된다(7/31 실측:
    # 3띠 모두 "특히 7월 31일 무렵" — 말이 안 된다). 4일 미만이면 오늘 총운으로 뺀다.
    if t["scope"] != "day" and len(_theme_days(date, t["scope"])) < 4:
        return PICK3_THEMES[0]
    return t


def _theme_days(date: dt.date, scope: str) -> list[dt.date]:
    """기간형 주제의 대상 날짜 = **오늘부터 기간 끝까지**(지난 날은 뺀다).

    지난 날을 넣으면 7월 31일 영상이 "이달은 7월 1일 무렵이 좋습니다"라고 말한다
    (실측으로 나왔다). 시청자에게 쓸모 있으려면 남은 기간이어야 한다. 기간 끝날엔
    자연히 그날 하루만 남아 오늘 기준과 같아진다.
    """
    if scope == "week":
        end = date + dt.timedelta(days=6 - date.weekday())
    elif scope == "month":
        s = date.replace(day=1)
        nxt = (s.replace(year=s.year + 1, month=1) if s.month == 12
               else s.replace(month=s.month + 1))
        end = nxt - dt.timedelta(days=1)
    else:
        return [date]
    return [date + dt.timedelta(days=i) for i in range((end - date).days + 1)]


def theme_scores(date: dt.date, theme: dict) -> dict[str, dict]:
    """띠별 {score, best_day}. score=기간 평균, best_day=기간 중 가장 좋은 날."""
    import zodiac_seo as zs
    field = _AXIS_FIELD[theme["axis"]]
    days = _theme_days(date, theme["scope"])
    out: dict[str, dict] = {}
    for ko in ZODIAC12:
        slug = zs.KO_TO_SLUG[ko]
        vals = [(getattr(zs.make_reading(slug, dd.isoformat()), field), dd) for dd in days]
        out[ko] = {"score": sum(v for v, _ in vals) / len(vals),
                   "best_day": max(vals, key=lambda t: (t[0], -t[1].toordinal()))[1]}
    return out


def pick3_signs(rows_by_ko: dict[str, dict] | None = None, n: int = PICK3_N,
                date: dt.date | None = None, theme: dict | None = None) -> list[str]:
    """지목할 띠 상위 n개.

    점수는 날짜 시드로 정해져 있어(zodiac_seo.make_reading) 같은 날 몇 번을 다시
    돌려도 같은 띠가 나온다 = 파이프라인 멱등성 유지. 동점은 12지 표준 순서로 끊는다
    (무작위 금지 — 재실행 때 카드와 내레이션이 어긋난다).

    date를 주면 주제 로테이션(기간·축)을 적용하고, 안 주면 예전처럼 rows_by_ko의
    '전체' 별점으로 오늘 총운 top3를 뽑는다.
    """
    order = {ko: i for i, ko in enumerate(ZODIAC12)}
    if date is not None:
        sc = theme_scores(date, theme or pick3_theme(date))
        return sorted(ZODIAC12, key=lambda ko: (-sc[ko]["score"], order[ko]))[:n]

    rows_by_ko = rows_by_ko or {}

    def key(ko: str):
        st = (rows_by_ko.get(ko) or {}).get("stars") or {}
        return (-int(st.get("전체", 3)), order[ko])

    return sorted(ZODIAC12, key=key)[:n]


def pick3_prompt(date: dt.date, rows_by_ko: dict[str, dict],
                 picks: list[str] | None = None,
                 theme: dict | None = None, simple: bool = False,
                 pick_theme: dict | None = None) -> str:
    """지목된 3띠만 크게 담은 카드 (20초 유튜브판 전용, 표지 없이 이 한 장으로 간다).

    12띠 요약 카드(summary12_prompt)와 반대 설계다. 저쪽은 '일시정지해서 읽는' 밀도,
    이쪽은 '끝까지 보게 하는' 여백 — 셀 3개뿐이라 글씨를 크게 쓸 수 있다.
    """
    t = theme or daily_theme(date)
    pt = pick_theme or pick3_theme(date)
    picks = picks or pick3_signs(rows_by_ko, date=date, theme=pt)
    animals = ", ".join(ZODIAC_EN.get(ko, ko) for ko in picks)
    guide = _zodiac_feature_guide(picks)
    # 기간형 지목은 해당 기간에서 점수가 가장 좋은 날짜의 정본 운세를 카드에도
    # 반영해야 영상(pick3_narration)과 페이지가 서로 다른 말을 하지 않는다.
    period_scores = theme_scores(date, pt) if pt["scope"] != "day" else {}
    cells = ""
    for rank, ko in enumerate(picks, 1):
        r = rows_by_ko.get(ko) or {}
        n = max(1, min(5, int((r.get("stars") or {}).get("전체", 4))))
        target = period_scores.get(ko, {}).get("best_day") or date
        try:
            reading_text = _pick3_reading_text(ko, target, pt.get("axis", "overall"))
        except Exception:
            # 정본 엔진을 우선 사용하되, 환경이 일시적으로 불완전한 경우 기존
            # build_rows 결과로 이미지 생성 자체가 멈추지 않게 한다.
            reading_text = r.get("advice") or r.get("line", "좋은 기운이 함께하는 날")
        feature = ZODIAC_FEATURES.get(ko, "a cute natural animal mascot")
        cells += (f"Card {rank} — a big cute {ZODIAC_EN.get(ko, 'animal')} zodiac mascot ({feature}) on the left; "
                  f"on the right the name '{ko}' in LARGE bold Korean, below it "
                  f"'{reading_text}' in clearly readable Korean "
                  f"(2 short lines), then '행운 {r.get('lucky', '')}' and "
                  f"'운세지수 {'★' * n}{'☆' * (5 - n)}'. ")
    deco = (f"Background: {t['bg'][1]}. " if not simple else
            "Background: soft plain auspicious gradient. ")
    guard = _SNAKE_GUARD + " " if any(ko == "뱀띠" for ko in picks) else ""
    return (
        f"Vertical 9:16 Korean daily fortune card featuring ONLY THREE zodiac signs "
        f"({animals}) — exactly three, no other animals anywhere in the image. "
        f"{ZODIAC_COMMON_BASE} Species guide: {guide}. "
        # 날짜는 넣지 않는다 — 2026-07-30 실물에서 '7월 30일'이 '7월 30얼'로 깨졌다.
        # 날짜는 영상 제목·설명에 이미 있고, 벤치마크 영상도 카드에 날짜가 없다.
        # 글자를 하나라도 덜 그리게 하는 게 오타 확률을 줄이는 가장 확실한 방법이다.
        f"Top title '{pt['title']}' in large bold Korean, centered, with NO date "
        f"anywhere in the image and no other heading text. "
        f"Then THREE generously spaced rounded cards stacked vertically, one per sign, "
        f"each card filling about a quarter of the height so the Korean text is LARGE "
        f"and easy to read on a phone. Exact contents: {cells}"
        # 쇼츠는 설명란·댓글 링크가 눌리지 않는다 → 유입 통로는 프로필뿐이라 화면에
        # 적어 준다. 12띠 카드처럼 나중에 얹을 여백이 없어 카드 안에 그리게 한다.
        # ⚠️ 금액은 넣지 않는다 — AI가 숫자를 한 자라도 틀리면 가격 오표기가 된다.
        f"At the very bottom, one slim rounded banner in deep wine red with a cream "
        f"border, containing exactly this Korean line in clean bold cream type: "
        f"'무료 오늘의 운세 · 프로필 링크 확인'. "
        f"Scene accents: {t['concept'][1]}. {guard}{deco}"
        f"Bright clean editorial layout, generous padding, soft card shadows, "
        f"{t['palette'][1]}. Art style: {t['style'][1]}. {_NEG}"
    )


def daily_set(date: dt.date, rows_by_ko: dict[str, dict]) -> dict:
    """하루 4장 프롬프트 전체(띠별 3장 + 12띠요약).

    rows_by_ko = {띠: {"line": 한줄운세, "stars": {전체,금전,연애,건강}}} 12개.
    반환: {theme, images: [{name, file, signs, prompt, simple_prompt} × 4]}
    """
    t = daily_theme(date)
    images = []
    for gi, group in enumerate(GROUPS):
        rows = []
        for ko in group:
            r = rows_by_ko.get(ko) or {"line": "좋은 기운이 함께하는 날", "stars": {"전체": 4, "금전": 4, "연애": 4, "건강": 4}}
            rows.append({"ko": ko, "line": r["line"], "stars": r["stars"]})
        images.append({
            "name": GROUP_NAMES[gi], "file": f"{gi + 1:02d}_{GROUP_NAMES[gi]}",
            "signs": list(group),
            "prompt": group_prompt(date, rows, t),
            "simple_prompt": group_prompt(date, rows, t, simple=True),
        })
    # 4번째 = 12띠 요약 1장. 95초판은 1~4를 쓴다.
    images.append({
        "name": "12띠요약", "file": "04_12띠요약", "signs": list(ZODIAC12),
        "prompt": summary12_prompt(date, rows_by_ko, t),
        "simple_prompt": summary12_prompt(date, rows_by_ko, t, simple=True),
    })
    # 5번째 = 소수 지목형 카드 (2026-07-26 신포맷, 20초 유튜브판 전용).
    # optional=True: 이 장이 실패해도 하루 발행을 막지 않는다. 20초판은 6번 카드로
    # 자동 폴백하고 95초판·스레드·틱톡은 애초에 1~4번만 쓴다.
    # 지목형 차례인 날에만 만든다 — 3일에 하루 쓸 카드를 매일 뽑으면 크레딧이 샌다.
    if shorts_format(date.isoformat()) != "pick3":
        return {"theme": t, "images": images, "picks": [], "pick_theme": None}
    pt = pick3_theme(date)
    picks = pick3_signs(rows_by_ko, date=date, theme=pt)
    images.append({
        "name": "지목3띠", "file": "05_지목3띠", "signs": picks, "optional": True,
        "prompt": pick3_prompt(date, rows_by_ko, picks, t, pick_theme=pt),
        "simple_prompt": pick3_prompt(date, rows_by_ko, picks, t, simple=True,
                                      pick_theme=pt),
    })
    return {"theme": t, "images": images, "picks": picks, "pick_theme": pt}


if __name__ == "__main__":
    import sys, io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    base = dt.date(2026, 7, 18)
    print("=== 7일간 다양성 조합 ===\n")
    for i in range(7):
        d = base + dt.timedelta(days=i)
        t = daily_theme(d)
        print(f"{d} {t['weekday']}: [{t['style'][0]}] · 배경={t['bg'][0]} · 컨셉={t['concept'][0]} · "
              f"색={t['palette'][0]} · 구도={t['composition'][0]} · "
              f"소품={t['props'][0].split('(')[0].strip()}")
    demo_rows = {ko: {"line": "운이 활짝 열리는 날", "stars": {"전체": 4, "금전": 3, "연애": 5, "건강": 4}}
                 for ko in ZODIAC12}
    s = daily_set(base, demo_rows)
    print(f"\n=== {base} 이미지 {len(s['images'])}장(기본 4장 + 선택 카드) ===")
    for im in s["images"]:
        print(f"\n[{im['file']}] ({', '.join(im['signs'][:3])}{'...' if len(im['signs']) > 3 else ''})")
        print(im["prompt"][:300], "...")
