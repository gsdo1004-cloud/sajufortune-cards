"""띠별운세 이미지 프롬프트 '다양성' 엔진 — v2 (2026-07-17 5장 체제).

핵심 철학 (한밝님 2026-07-17): 매일 다른 화풍·배경·컨셉·색감·소품이라야
독자가 질리지 않고 재미있게 본다. 여러 축을 서로 다른 주기로 순환시켜
조합을 폭발시킨다(사실상 매일 유니크). 결정론적(날짜 기반) = 재현 가능.

v2 변경 (한밝님 지시):
  - 하루 5장: 표지(섬네일) 1장 + 띠별 4장(각 3띠) — 전부 9:16, GPT Image 2 1K
  - 각 장에 simple(단순화) 폴백 프롬프트 동봉 — 생성 실패 시 재시도용
    (텍스트는 동일하게 유지하고 장식 요소만 줄여 성공률을 높인다)
  - 띠별 장: 띠 3줄 × (한 줄 운세 + 별점 4항목 전체/금전/연애/건강)
"""
from __future__ import annotations
import datetime as dt

# ─────────────────────────────────────────────────────────────
# 다양성 축 — 각 축이 독립 순환하여 조합 폭발
# ─────────────────────────────────────────────────────────────

ART_STYLES = [
    ("수채화",     "soft watercolor illustration, gentle wet-on-wet washes, dreamy translucent tones"),
    ("3D 클레이",  "cute 3D clay-render style, Pixar-like rounded forms, soft studio lighting"),
    ("수묵화",     "traditional Korean ink-wash painting (수묵화), elegant flowing brushstrokes, misty negative space"),
    ("반실사",     "semi-realistic detailed digital painting, rich soft fur texture, shallow depth of field"),
    ("시네마틱",   "cinematic key-lit illustration, golden-hour glow, filmic color grade, gentle bokeh"),
    ("유화",       "classical oil-painting look, visible impasto brushwork, warm chiaroscuro depth"),
    ("민화",       "Korean folk-art (민화) style, vivid symbolic colors, decorative flat composition"),
    ("파스텔 애니","soft pastel anime style, kawaii big-eyed charm, gentle gradient shading"),
    ("판타지 매직","magical fantasy illustration, glowing particles, ethereal luminous atmosphere"),
    ("색연필",     "warm colored-pencil storybook style, hand-drawn hatching, cozy paper grain"),
    ("종이공예",   "layered cut-paper craft collage, papercut shadow depth, tactile texture"),
    ("빈티지",     "retro vintage poster art, subtle halftone texture, nostalgic warm palette"),
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
]

CONCEPTS = [
    ("한복",       "each animal wearing colorful traditional hanbok"),
    ("신선 도사",  "as cute mystical mountain-sage characters"),
    ("아기 동물",  "as adorable chibi baby animals"),
    ("왕과 신하",  "as charming royal-court characters with small crowns and robes"),
    ("계절 나들이","in cheerful seasonal outing outfits"),
    ("복 요정",    "as tiny winged fortune fairies carrying luck"),
    ("전통 놀이",  "cheerfully enjoying traditional Korean folk play"),
    ("명절 한복",  "in festive holiday hanbok with ornaments"),
]

PALETTES = [
    ("황금 길상",  "auspicious gold, red and warm lucky palette"),
    ("오방색",     "traditional Korean five-direction obangsaek colors"),
    ("파스텔 몽환","soft dreamy pastel palette"),
    ("무지개 밝음","bright cheerful rainbow palette"),
    ("청록 신비",  "mystic teal, indigo and violet palette"),
    ("노을 따뜻",  "warm amber sunset palette"),
]

PROPS = [
    "gold lucky pouch (복주머니)", "shiny old coins (엽전)", "four-leaf clovers",
    "a lucky talisman (부적)", "a blooming lotus", "brush and scroll",
    "a glowing lantern", "a bright full moon", "an elegant crane", "auspicious clouds",
    "a peach of longevity", "a small treasure chest",
]

WEEKDAY_KR = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]

# 12지신 (표준 순서) — 하루 4장 = 3띠씩
ZODIAC12 = ["쥐띠", "소띠", "호랑이띠", "토끼띠", "용띠", "뱀띠",
            "말띠", "양띠", "원숭이띠", "닭띠", "개띠", "돼지띠"]
ZODIAC_EN = {
    "쥐띠": "rat", "소띠": "ox", "호랑이띠": "tiger", "토끼띠": "rabbit",
    "용띠": "dragon", "뱀띠": "snake", "말띠": "horse", "양띠": "sheep",
    "원숭이띠": "monkey", "닭띠": "rooster", "개띠": "dog", "돼지띠": "pig",
}
GROUP_NAMES = ["띠별A", "띠별B", "띠별C", "띠별D"]
GROUPS = [ZODIAC12[i * 3:(i + 1) * 3] for i in range(4)]   # 3띠 × 4장


def _pick(date: dt.date, axis: list, period: int = 1):
    """날짜 기반 결정론적 선택. period=순환 주기(클수록 천천히 바뀜)."""
    idx = (date.toordinal() // period) % len(axis)
    return axis[idx]


def daily_theme(date: dt.date) -> dict:
    """오늘의 다양성 조합. 각 축을 다른 주기로 돌려 반복을 최대한 늦춘다."""
    o = date.toordinal()
    return {
        "style":   _pick(date, ART_STYLES, 1),   # 매일 바뀜
        "bg":      _pick(date, BACKGROUNDS, 1),   # 매일 바뀜(화풍과 다른 배열이라 어긋나며 순환)
        "concept": _pick(date, CONCEPTS, 2),      # 2일마다
        "palette": _pick(date, PALETTES, 1),      # 매일
        "props":   [PROPS[(o * 5 + i * 7) % len(PROPS)] for i in range(2)],
        "weekday": WEEKDAY_KR[date.weekday()],
        "date_kr": f"{date.month}월 {date.day}일",
    }


_SNAKE_GUARD = "The snake must be drawn cute, round and friendly, never realistic or scary."
_NEG = ("No watermark, no logo, crisp clean readable Korean typography. "
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
    deco = (f"Background: {t['bg'][1]}. Lucky props scattered: {', '.join(t['props'])}. "
            if not simple else
            "Background: soft plain auspicious gradient with gentle light rays. ")
    return (
        f"Vertical 9:16 Korean daily fortune COVER poster. "
        f"Large bold clean Korean title '오늘의 운세' at top center, "
        f"date '{t['date_kr']} {t['weekday']}' clearly just below. "
        f"All twelve cute Korean zodiac animals (rat, ox, tiger, rabbit, dragon, snake, "
        f"horse, sheep, monkey, rooster, dog, pig), {t['concept'][1]}, arranged cheerfully and friendly. "
        f"{deco}"
        f"{t['palette'][1]}. Art style: {t['style'][1]}. "
        f"{_SNAKE_GUARD} Warm auspicious festive lucky mood. {_NEG}"
    )


def group_prompt(date: dt.date, rows: list[dict], theme: dict | None = None,
                 simple: bool = False) -> str:
    """띠별 3띠 프롬프트. rows = [{ko, line, stars:{전체,금전,연애,건강}}] 3개."""
    t = theme or daily_theme(date)
    animals = ", ".join(ZODIAC_EN.get(r["ko"], r["ko"]) for r in rows)
    secs = ""
    for i, r in enumerate(rows, 1):
        en = ZODIAC_EN.get(r["ko"], "animal")
        secs += (f"Section {i} — Korean heading '{r['ko']}' with a cute {en} character: "
                 f"fortune text '{r['line']}', star line '{stars_line(r['stars'])}'. ")
    deco = (f"Background: {t['bg'][1]}. " if not simple else
            "Background: soft plain auspicious gradient. ")
    guard = _SNAKE_GUARD + " " if any(r["ko"] == "뱀띠" for r in rows) else ""
    return (
        f"Vertical 9:16 Korean zodiac fortune card, clean readable layout. "
        f"Top title '오늘의 띠별운세' bold clean Korean, small date '{t['date_kr']} {t['weekday']}'. "
        f"Three stacked horizontal sections, each = one cute zodiac animal ({animals}, in order) "
        f"on the left + its Korean text block on the right. "
        f"{secs}"
        f"Characters {t['concept'][1]}. {deco}"
        f"{t['palette'][1]}. Art style: {t['style'][1]}. "
        f"{guard}{_NEG}"
    )


def daily_set(date: dt.date, rows_by_ko: dict[str, dict]) -> dict:
    """하루 5장 프롬프트 전체.

    rows_by_ko = {띠: {"line": 한줄운세, "stars": {전체,금전,연애,건강}}} 12개.
    반환: {theme, images: [{name, file, signs, prompt, simple_prompt} × 5]}
    """
    t = daily_theme(date)
    images = [{
        "name": "표지", "file": "01_표지", "signs": list(ZODIAC12),
        "prompt": cover_prompt(date, t),
        "simple_prompt": cover_prompt(date, t, simple=True),
    }]
    for gi, group in enumerate(GROUPS):
        rows = []
        for ko in group:
            r = rows_by_ko.get(ko) or {"line": "좋은 기운이 함께하는 날", "stars": {"전체": 4, "금전": 4, "연애": 4, "건강": 4}}
            rows.append({"ko": ko, "line": r["line"], "stars": r["stars"]})
        images.append({
            "name": GROUP_NAMES[gi], "file": f"{gi + 2:02d}_{GROUP_NAMES[gi]}",
            "signs": list(group),
            "prompt": group_prompt(date, rows, t),
            "simple_prompt": group_prompt(date, rows, t, simple=True),
        })
    return {"theme": t, "images": images}


if __name__ == "__main__":
    import sys, io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    base = dt.date(2026, 7, 18)
    print("=== 7일간 다양성 조합 ===\n")
    for i in range(7):
        d = base + dt.timedelta(days=i)
        t = daily_theme(d)
        print(f"{d} {t['weekday']}: [{t['style'][0]}] · 배경={t['bg'][0]} · 컨셉={t['concept'][0]} · "
              f"색={t['palette'][0]} · 소품={t['props'][0].split('(')[0].strip()}")
    demo_rows = {ko: {"line": "운이 활짝 열리는 날", "stars": {"전체": 4, "금전": 3, "연애": 5, "건강": 4}}
                 for ko in ZODIAC12}
    s = daily_set(base, demo_rows)
    print(f"\n=== {base} 이미지 5장 ===")
    for im in s["images"]:
        print(f"\n[{im['file']}] ({', '.join(im['signs'][:3])}{'...' if len(im['signs']) > 3 else ''})")
        print(im["prompt"][:300], "...")
