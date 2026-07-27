# -*- coding: utf-8 -*-
"""표형 12띠 운세 카드 로컬 렌더 (1080x1920, 2026-07-26 신설).

왜 로컬 렌더인가 — 이 레이아웃은 셀 12개 × 각 3~4줄이라 글자 밀도가 매우 높다.
Topview(GPT Image 2)로 뽑으면 그 밀도에서 한글이 자주 깨진다(zodiac_prompt_engine
summary12_prompt 주석: "오타 한두 개는 감수"). 표 형태는 오타가 바로 티가 나므로
PIL로 직접 그린다. 부수 효과로 Topview 크레딧 0, 생성 실패율 0, 재현성 100%.

동물은 컬러 이모지(Segoe UI Emoji, embedded_color)로 찍는다 — 별도 에셋 없이
12지신이 다 있고 시니어 눈에도 또렷하다.

단독 실행: python zodiac_table_card.py [YYYY-MM-DD]
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

import zodiac_prompt_engine as zpe  # noqa: E402

W, H = 1080, 1920

# ── 색 (밝고 따뜻한 톤 — 타겟 30대~시니어, 대비 우선) ─────────
C_BG_TOP = (255, 214, 150)
C_BG_BOT = (255, 246, 232)
C_CARD = (255, 255, 255)
C_LINE = (238, 226, 210)
C_INK = (38, 34, 30)
C_SUB = (92, 84, 76)
C_TITLE = (150, 40, 40)
C_LUCKY_BG = (255, 249, 235)
# 띠명 색 — 12개를 다 다르게 하면 산만하다. 오행 계열 5색을 돌린다.
C_NAMES = [(196, 78, 58), (46, 122, 92), (52, 96, 168), (168, 108, 30), (110, 76, 156)]

EMOJI = {
    "쥐띠": "🐭", "소띠": "🐮", "호랑이띠": "🐯", "토끼띠": "🐰",
    "용띠": "🐲", "뱀띠": "🐍", "말띠": "🐴", "양띠": "🐑",
    "원숭이띠": "🐵", "닭띠": "🐔", "개띠": "🐶", "돼지띠": "🐷",
}

FONT_DIRS = [
    Path(r"G:\내 드라이브\01클로드\에셋라이브러리\폰트"),
    Path(r"C:\Windows\Fonts"),
]
_BOLD = ["GmarketSansTTFBold.ttf", "malgunbd.ttf", "malgun.ttf"]
_REG = ["GmarketSansTTFMedium.ttf", "malgun.ttf", "malgunbd.ttf"]
EMOJI_FONT = Path(r"C:\Windows\Fonts\seguiemj.ttf")

# 행운 아이템 — 날짜·띠 시드로 결정론 선택(재실행해도 같은 값). 재미·참고용.
LUCKY_ITEMS = [
    "따뜻한 차", "손수건", "작은 메모", "우산", "지갑 정리", "가벼운 산책",
    "아침 인사", "제철 과일", "밝은 양말", "책 한 쪽", "화분 물주기", "짧은 통화",
    "정리된 책상", "새 볼펜", "달콤한 간식", "이른 취침",
]


def _font(names: list[str], size: int):
    for d in FONT_DIRS:
        for n in names:
            p = d / n
            if p.exists():
                try:
                    return ImageFont.truetype(str(p), size)
                except OSError:
                    continue
    return ImageFont.load_default()


def bold(size: int):
    return _font(_BOLD, size)


def reg(size: int):
    return _font(_REG, size)


def _emoji_font(size: int):
    # Segoe UI Emoji는 109px 비트맵 스트라이크만 있어 그 크기로 그린 뒤 축소한다.
    if EMOJI_FONT.exists():
        try:
            return ImageFont.truetype(str(EMOJI_FONT), 109)
        except OSError:
            pass
    return None


def _wrap(draw, text: str, font, max_w: int, max_lines: int = 2) -> list[str]:
    """공백 기준 줄바꿈. 마지막 줄이 넘치면 말줄임."""
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = f"{cur} {w}".strip()
        if draw.textlength(t, font=font) <= max_w or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
            if len(lines) == max_lines:
                break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    if len(lines) == max_lines and words:
        joined = " ".join(lines)
        if len(joined) < len(text):
            last = lines[-1]
            while last and draw.textlength(last + "…", font=font) > max_w:
                last = last[:-1]
            lines[-1] = last + "…"
    return lines


def _seed(date: dt.date, ko: str) -> int:
    return (date.toordinal() * 31 + sum(ord(c) for c in ko) * 17) % 100003


def _bg(im: Image.Image):
    """위→아래 세로 그라데이션."""
    top = Image.new("RGB", (1, H))
    px = top.load()
    for y in range(H):
        r = y / (H - 1)
        px[0, y] = tuple(int(a + (b - a) * r) for a, b in zip(C_BG_TOP, C_BG_BOT))
    im.paste(top.resize((W, H)), (0, 0))


def _emoji(im: Image.Image, ch: str, cx: int, cy: int, size: int):
    ef = _emoji_font(size)
    if ef is None:
        return
    tile = Image.new("RGBA", (140, 140), (0, 0, 0, 0))
    try:
        ImageDraw.Draw(tile).text((70, 70), ch, font=ef, embedded_color=True, anchor="mm")
    except Exception:
        return
    tile = tile.resize((size, size), Image.LANCZOS)
    im.paste(tile, (cx - size // 2, cy - size // 2), tile)


def render(date_iso: str, out: Path, rows_by_ko: dict | None = None) -> Path:
    """표형 12띠 카드 1장 생성. rows_by_ko 없으면 그날 데이터를 직접 만든다."""
    d = dt.date.fromisoformat(date_iso)
    if rows_by_ko is None:
        import zodiac_topview as zt
        rows_by_ko = zt.build_rows(date_iso)

    im = Image.new("RGB", (W, H), C_BG_BOT)
    _bg(im)
    dr = ImageDraw.Draw(im)

    # ── 제목 ────────────────────────────────────────────────
    wd = ["월", "화", "수", "목", "금", "토", "일"][d.weekday()]
    title = "오늘의 띠별 운세"
    sub = f"{d.month}월 {d.day}일 {wd}요일"
    ft, fs = bold(72), bold(40)
    dr.text((W // 2, 96), title, font=ft, fill=C_TITLE, anchor="mm")
    dr.text((W // 2, 162), sub, font=fs, fill=C_SUB, anchor="mm")

    # ── 프로필 유입 CTA (제목과 표 사이) ──────────────────────
    # 쇼츠는 설명란·댓글 링크가 클릭되지 않는다(유튜브 스팸 정책). 유입 통로는 채널
    # 프로필뿐이라 화면에 직접 적어 준다. AI 카드에는 zodiac_shorts.add_cta_band가
    # 나중에 얹지만, 이 카드는 표가 화면을 꽉 채워 얹을 여백이 없다 → 여기서 그린다.
    pad = 22
    cta_box = [pad + 40, 196, W - pad - 40, 252]
    dr.rounded_rectangle(cta_box, radius=28, fill=(138, 30, 62), outline=(255, 248, 235), width=3)
    f_cta = bold(27)
    head, gold = "무료 운세 · ", "이용권 1,000원 · 프로필 링크"
    tw = dr.textlength(head, font=f_cta) + dr.textlength(gold, font=f_cta)
    cx0 = (W - tw) / 2
    dr.text((cx0, 224), head, font=f_cta, fill=(255, 248, 235), anchor="lm")
    dr.text((cx0 + dr.textlength(head, font=f_cta), 224), gold, font=f_cta,
            fill=(255, 205, 90), anchor="lm")

    # ── 12행 표 ─────────────────────────────────────────────
    top, bot = 268, 1866
    rh = (bot - top) // 12
    f_name, f_line, f_lucky_h, f_lucky = bold(42), reg(27), bold(21), reg(23)
    for i, ko in enumerate(zpe.ZODIAC12):
        r = rows_by_ko.get(ko) or {}
        y0 = top + i * rh
        box = [pad, y0 + 4, W - pad, y0 + rh - 4]
        dr.rounded_rectangle(box, radius=18, fill=C_CARD, outline=C_LINE, width=2)

        cy = (box[1] + box[3]) // 2
        _emoji(im, EMOJI.get(ko, "🐾"), pad + 62, cy, 74)

        # 띠명 — 4글자(호랑이띠·원숭이띠)는 폰트를 줄인다. 안 줄이면 본문 컬럼을
        # 침범해 글자가 겹친다(첫 렌더에서 실제로 겹쳤다).
        fn = f_name if len(ko) <= 3 else bold(34)
        dr.text((pad + 120, cy), ko, font=fn,
                fill=C_NAMES[i % len(C_NAMES)], anchor="lm")

        # 운세 2줄 — advice(2~3줄용 긴 문장)를 쓰고 없으면 line으로
        text = r.get("advice") or r.get("line") or "좋은 기운이 함께하는 날"
        tx, tw = pad + 260, W - pad * 2 - 260 - 230
        lines = _wrap(dr, text, f_line, tw, 2)
        ly = cy - (len(lines) * 34) // 2 + 17
        for ln in lines:
            dr.text((tx, ly), ln, font=f_line, fill=C_INK, anchor="lm")
            ly += 34

        # 행운 포인트 (오른쪽 박스) — 색·방향은 그날 일진 오행에서 온 값,
        # 숫자·아이템은 날짜×띠 시드로 고정.
        lb = [W - pad - 220, box[1] + 8, W - pad - 10, box[3] - 8]
        dr.rounded_rectangle(lb, radius=12, fill=C_LUCKY_BG, outline=C_LINE, width=2)
        s = _seed(d, ko)
        lucky = str(r.get("lucky") or "").replace("·", " · ")
        num = s % 9 + 1
        item = LUCKY_ITEMS[s % len(LUCKY_ITEMS)]
        lx, lcy = (lb[0] + lb[2]) // 2, (lb[1] + lb[3]) // 2
        dr.text((lx, lb[1] + 24), "행운 포인트", font=f_lucky_h, fill=C_TITLE, anchor="mm")
        # 일진 오행이 2색인 날("초록·청색·동쪽")은 기본 폰트로 박스를 넘는다 → 자동 축소
        val, inner = f"{lucky} · {num}", (lb[2] - lb[0]) - 18
        fv = f_lucky
        for s2 in range(23, 15, -1):
            fv = reg(s2)
            if dr.textlength(val, font=fv) <= inner:
                break
        dr.text((lx, lcy + 6), val, font=fv, fill=C_INK, anchor="mm")
        dr.text((lx, lb[3] - 22), item, font=f_lucky, fill=C_SUB, anchor="mm")

    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out, quality=95)
    return out


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    di = sys.argv[1] if len(sys.argv) > 1 else dt.date.today().isoformat()
    p = render(di, BASE / "cards" / di / "card_08.png")
    print(f"OK {p} {p.stat().st_size // 1024}KB")
