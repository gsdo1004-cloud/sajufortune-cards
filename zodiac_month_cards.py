# -*- coding: utf-8 -*-
"""zodiac_month_cards.py — 월간 운세 카드 렌더러 (2026-07-25)

산출물 3종을 같은 디자인 언어(대박운세 와인+금색)로 만든다.
  onepage : 한장뉴스 1장 (12띠 전체가 한 화면)      1080x1350
  cardnews: 카드뉴스 6장 (표지 + 3띠×4장 + 마무리)   1080x1350
  shorts  : 쇼츠용 세로 카드                        1080x1920

일일 카드는 Topview AI 이미지를 쓰지만 월간은 12장을 새로 뽑을 이유가 없다.
글자가 핵심인 콘텐츠라 Pillow로 직접 그린다 — 비용 0, 몇 초면 끝나고 매달 재현된다.
"""
from __future__ import annotations

import datetime as _dt
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from zodiac_month import all_month_readings, month_label

BASE = Path(__file__).resolve().parent
FONT_DIR = Path(r"G:\내 드라이브\01클로드\에셋라이브러리\폰트")
_FONTS = [FONT_DIR / "GmarketSansTTFBold.ttf", FONT_DIR / "GmarketSansTTFMedium.ttf",
          Path(r"C:\Windows\Fonts\malgunbd.ttf"), Path(r"C:\Windows\Fonts\malgun.ttf")]

WINE, WINE_D = (107, 31, 55), (52, 12, 27)
CREAM, GOLD, DIM = (255, 248, 235), (240, 196, 96), (206, 178, 190)
# RGB 캔버스에서는 알파가 무시된다. (255,255,255,12)로 반투명을 노리면 그냥 흰 박스가 되고
# 그 위의 크림색 글씨가 사라진다(실제로 그랬다). 불투명한 밝은 와인으로 고정한다.
CARD_BG, CARD_LINE = (88, 27, 49), (152, 92, 112)
TONE_COLOR = {"상승": (126, 217, 87), "능동": (255, 205, 90), "평온": (140, 200, 255),
              "신중": (255, 168, 96), "주의": (255, 130, 130)}
EMOJI = {"쥐띠": "🐭", "소띠": "🐮", "호랑이띠": "🐯", "토끼띠": "🐰", "용띠": "🐲", "뱀띠": "🐍",
         "말띠": "🐴", "양띠": "🐑", "원숭이띠": "🐵", "닭띠": "🐔", "개띠": "🐶", "돼지띠": "🐷"}
# 이모지 폰트가 없는 환경에서도 깨지지 않도록 한자 대체를 준비한다
BRANCH_KO = {"쥐띠": "子", "소띠": "丑", "호랑이띠": "寅", "토끼띠": "卯", "용띠": "辰", "뱀띠": "巳",
             "말띠": "午", "양띠": "未", "원숭이띠": "申", "닭띠": "酉", "개띠": "戌", "돼지띠": "亥"}
_EMOJI_FONT = Path(r"C:\Windows\Fonts\seguiemj.ttf")


def _f(size: int, bold: bool = True):
    order = _FONTS if bold else _FONTS[1:] + _FONTS[:1]
    for p in order:
        try:
            if p.exists():
                return ImageFont.truetype(str(p), size)
        except Exception:
            continue
    return ImageFont.load_default()


def _ef(size: int):
    try:
        if _EMOJI_FONT.exists():
            return ImageFont.truetype(str(_EMOJI_FONT), size)
    except Exception:
        pass
    return None


def _bg(w: int, h: int) -> Image.Image:
    im = Image.new("RGB", (w, h), WINE)
    d = ImageDraw.Draw(im)
    for y in range(h):
        t = y / h
        d.line([(0, y), (w, y)], fill=tuple(int(WINE[i] + (WINE_D[i] - WINE[i]) * t) for i in range(3)))
    d.rectangle([0, 0, w - 1, h - 1], outline=GOLD, width=5)
    return im


def _fit(d, txt, size, maxw, bold=True):
    f = _f(size, bold)
    while size > 11 and d.textbbox((0, 0), txt, font=f)[2] > maxw:
        size -= 1
        f = _f(size, bold)
    return f


def _center(d, txt, y, size, color, w, maxw=None, bold=True):
    f = _fit(d, txt, size, maxw or int(w * 0.9), bold)
    bb = d.textbbox((0, 0), txt, font=f)
    d.text(((w - (bb[2] - bb[0])) / 2, y - bb[1]), txt, font=f, fill=color)
    return bb[3] - bb[1]


def _emoji(im, d, ch, x, y, size):
    ef = _ef(size)
    if ef is not None:
        try:
            d.text((x, y), ch, font=ef, fill=CREAM, embedded_color=True)
            return
        except Exception:
            pass
    d.text((x, y), BRANCH_KO.get(ch, "·"), font=_f(size), fill=GOLD)


def _header(im, d, w, title, sub):
    _center(d, title, 62, 66, CREAM, w)
    _center(d, sub, 150, 32, GOLD, w)
    d.line([(w * 0.30, 205), (w * 0.70, 205)], fill=GOLD, width=3)


def _pill(d, cx, cy, pw, ph, fill, text, tsize, tcolor, w):
    d.rounded_rectangle([cx - pw // 2, cy - ph // 2, cx + pw // 2, cy + ph // 2],
                        radius=ph // 2, fill=fill)
    f = _fit(d, text, tsize, int(pw * 0.86))
    bb = d.textbbox((0, 0), text, font=f)
    d.text((cx - (bb[2] - bb[0]) / 2, cy - (bb[3] - bb[1]) / 2 - bb[1] / 2), text, font=f, fill=tcolor)


CTA_TEXT = "무료 운세 · 이용권 1,000원 · 프로필 링크"


def _cta(d, w, h, y=None, pw_ratio=0.74, ph=78, tsize=34):
    """프로필 유입 배지 — 일일 쇼츠와 같은 문구·같은 형태로 통일한다.

    y를 주지 않으면 하단. 쇼츠(1080x1920)에서는 반드시 y를 줘서 위로 올린다.
    유튜브 쇼츠는 하단 15~20%를 제목·채널명·버튼 UI가 덮어, 거기 둔 CTA는 가려진다.
    (일일 쇼츠에서 같은 이유로 날짜 배지 아래로 올렸다.)
    """
    _pill(d, w // 2, y if y is not None else h - 84, int(w * pw_ratio), ph, GOLD,
          CTA_TEXT, tsize, (74, 18, 38), w)


# ── 한장뉴스: 12띠가 한 화면 ──────────────────────────────
def make_onepage(year: int, month: int, out: Path, size=(1080, 1350)) -> Path:
    w, h = size
    rs = all_month_readings(year, month)
    im = _bg(w, h)
    d = ImageDraw.Draw(im)
    _header(im, d, w, f"{year}년 {month}월 띠별운세", f"{month_label(year, month)} · 12간지 종합")

    top, bot = 240, h - 150
    cols, rows = 3, 4
    cw, ch = (w - 80) // cols, (bot - top) // rows
    for i, r in enumerate(rs):
        cx = 40 + (i % cols) * cw
        cy = top + (i // cols) * ch
        d.rounded_rectangle([cx + 6, cy + 6, cx + cw - 6, cy + ch - 8], radius=18,
                            fill=CARD_BG, outline=CARD_LINE, width=1)
        _emoji(im, d, EMOJI[r["sign_ko"]], cx + 24, cy + 22, 52)
        f = _fit(d, r["sign_ko"], 34, cw - 110)
        d.text((cx + 88, cy + 30), r["sign_ko"], font=f, fill=CREAM)
        d.text((cx + 88, cy + 74), f"{r['score']}점", font=_f(26), fill=TONE_COLOR[r["tone"]])
        d.text((cx + 168, cy + 74), r["tone"], font=_f(24, False), fill=DIM)
        hl = _fit(d, r["headline"], 27, cw - 48, False)
        d.text((cx + 26, cy + 118), r["headline"], font=hl, fill=GOLD)
        days = "길일 " + "·".join(f"{x}일" for x in r["lucky_days"])
        d.text((cx + 26, cy + 158), days, font=_fit(d, days, 22, cw - 48, False), fill=DIM)
    _cta(d, w, h)
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out, optimize=True)
    return out


# ── 카드뉴스: 표지 + 3띠×4장 + 마무리 ─────────────────────
def make_cardnews(year: int, month: int, out_dir: Path, size=(1080, 1350)) -> list[Path]:
    w, h = size
    rs = all_month_readings(year, month)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []

    # 표지
    im = _bg(w, h); d = ImageDraw.Draw(im)
    _center(d, f"{year}년 {month}월", int(h * 0.20), 82, GOLD, w)
    _center(d, "띠별 운세", int(h * 0.31), 108, CREAM, w)
    d.line([(w * 0.25, h * 0.40), (w * 0.75, h * 0.40)], fill=GOLD, width=4)
    _center(d, month_label(year, month), int(h * 0.45), 40, DIM, w)
    _center(d, "12간지 전체 · 재물 · 애정 · 건강 · 직업", int(h * 0.53), 36, CREAM, w)
    _center(d, "좋은 시기와 길일까지", int(h * 0.60), 36, CREAM, w)
    _cta(d, w, h)
    p = out_dir / "card_01.png"; im.save(p, optimize=True); paths.append(p)

    # 3띠씩 4장
    for gi in range(4):
        group = rs[gi * 3:(gi + 1) * 3]
        im = _bg(w, h); d = ImageDraw.Draw(im)
        _header(im, d, w, f"{month}월 띠별운세", f"{gi + 1} / 4")
        top = 250
        bh = (h - top - 150) // 3
        for j, r in enumerate(group):
            y = top + j * bh
            d.rounded_rectangle([40, y + 8, w - 40, y + bh - 14], radius=22,
                                fill=CARD_BG, outline=CARD_LINE, width=1)
            _emoji(im, d, EMOJI[r["sign_ko"]], 76, y + 34, 62)
            d.text((166, y + 40), r["sign_ko"], font=_f(44), fill=CREAM)
            d.text((166, y + 96), f"{r['score']}점 · {r['tone']}", font=_f(28, False),
                   fill=TONE_COLOR[r["tone"]])
            hl = _fit(d, r["headline"], 34, w - 220, False)
            d.text((w - 60 - d.textbbox((0, 0), r["headline"], font=hl)[2], y + 44), r["headline"],
                   font=hl, fill=GOLD)
            lines = [f"재물 {r['wealth'][:26]}", f"애정 {r['love'][:26]}", r["period_note"][:34]]
            for k, ln in enumerate(lines):
                d.text((78, y + 148 + k * 40), ln, font=_fit(d, ln, 27, w - 156, False), fill=CREAM)
        _cta(d, w, h)
        p = out_dir / f"card_{gi + 2:02d}.png"; im.save(p, optimize=True); paths.append(p)

    # 마무리
    im = _bg(w, h); d = ImageDraw.Draw(im); _cta(d, w, h)
    _center(d, f"{month}월, 좋은 흐름 되세요", int(h * 0.30), 62, CREAM, w)
    _center(d, "내 사주로 보는 정밀 월운은", int(h * 0.44), 40, GOLD, w)
    _center(d, "프로필 링크에서 확인하세요", int(h * 0.51), 40, GOLD, w)
    _center(d, "재미와 참고용으로 즐겨주세요", int(h * 0.66), 28, DIM, w)
    p = out_dir / "card_06.png"; im.save(p, optimize=True); paths.append(p)
    return paths


# ── 쇼츠용 세로 카드 ─────────────────────────────────────
def make_shorts_cards(year: int, month: int, out_dir: Path) -> dict:
    """쇼츠 조립에 쓸 세로(1080x1920) 카드. 표지 / 12띠요약 / 그룹4장 / 개별12장 / 마무리."""
    w, h = 1080, 1920
    rs = all_month_readings(year, month)
    out_dir.mkdir(parents=True, exist_ok=True)
    res: dict = {"group": [], "single": []}
    # 쇼츠 안전영역: 하단 18%는 유튜브 UI(제목·채널명·버튼)가 덮는다. 정보는 그 위까지만.
    SAFE_BOT = int(h * 0.82)

    im = _bg(w, h); d = ImageDraw.Draw(im)
    _center(d, f"{year}년 {month}월", int(h * 0.26), 96, GOLD, w)
    _center(d, "띠별 운세", int(h * 0.35), 128, CREAM, w)
    d.line([(w * 0.25, h * 0.44), (w * 0.75, h * 0.44)], fill=GOLD, width=5)
    _center(d, f"{month_label(year, month)} · 12간지 종합", int(h * 0.49), 44, DIM, w)
    _cta(d, w, h, y=int(h * 0.60))
    res["cover"] = out_dir / "s_cover.png"; im.save(res["cover"], optimize=True)

    # 12띠 한 화면 요약 (일시정지해 읽는 구간)
    im = _bg(w, h); d = ImageDraw.Draw(im)
    _center(d, f"{month}월 띠별운세", 60, 70, CREAM, w)
    _center(d, month_label(year, month), 148, 34, GOLD, w)
    _cta(d, w, h, y=246, ph=70, tsize=31)
    top, bot = 320, SAFE_BOT
    cw, ch = (w - 70) // 3, (bot - top) // 4
    for i, r in enumerate(rs):
        cx, cy = 35 + (i % 3) * cw, top + (i // 3) * ch
        d.rounded_rectangle([cx + 6, cy + 6, cx + cw - 6, cy + ch - 10], radius=20,
                            fill=CARD_BG, outline=CARD_LINE, width=1)
        _emoji(im, d, EMOJI[r["sign_ko"]], cx + 22, cy + 24, 58)
        d.text((cx + 96, cy + 32), r["sign_ko"], font=_fit(d, r["sign_ko"], 38, cw - 120), fill=CREAM)
        d.text((cx + 96, cy + 84), f"{r['score']}점", font=_f(30), fill=TONE_COLOR[r["tone"]])
        hl = _fit(d, r["headline"], 28, cw - 44, False)
        d.text((cx + 24, cy + 140), r["headline"], font=hl, fill=GOLD)
        dd = "길일 " + "·".join(f"{x}" for x in r["lucky_days"]) + "일"
        d.text((cx + 24, cy + 184), dd, font=_fit(d, dd, 24, cw - 44, False), fill=DIM)
    res["summary"] = out_dir / "s_summary.png"; im.save(res["summary"], optimize=True)

    # 3띠 그룹 4장
    for gi in range(4):
        group = rs[gi * 3:(gi + 1) * 3]
        im = _bg(w, h); d = ImageDraw.Draw(im)
        _center(d, f"{month}월 띠별운세", 60, 64, CREAM, w)
        _cta(d, w, h, y=196, ph=68, tsize=30)
        top = 268; bh = (SAFE_BOT - top) // 3
        for j, r in enumerate(group):
            y = top + j * bh
            d.rounded_rectangle([44, y + 10, w - 44, y + bh - 18], radius=24,
                                fill=CARD_BG, outline=CARD_LINE, width=1)
            _emoji(im, d, EMOJI[r["sign_ko"]], 82, y + 40, 70)
            d.text((186, y + 46), r["sign_ko"], font=_f(52), fill=CREAM)
            d.text((186, y + 112), f"{r['score']}점 · {r['tone']}", font=_f(32, False),
                   fill=TONE_COLOR[r["tone"]])
            for k, ln in enumerate([r["headline"], r["wealth"], r["period_note"]]):
                d.text((84, y + 176 + k * 46), ln,
                       font=_fit(d, ln, 30, w - 168, k > 0), fill=GOLD if k == 0 else CREAM)
        p = out_dir / f"s_group_{gi + 1}.png"; im.save(p, optimize=True); res["group"].append(p)

    # 개별 12장
    for r in rs:
        im = _bg(w, h); d = ImageDraw.Draw(im)
        _cta(d, w, h, y=96, ph=66, tsize=29)
        _emoji(im, d, EMOJI[r["sign_ko"]], w // 2 - 70, 176, 140)
        _center(d, r["sign_ko"], 366, 92, CREAM, w)
        _center(d, f"{r['score']}점 · {r['tone']}", 482, 46, TONE_COLOR[r["tone"]], w)
        _center(d, r["headline"], 576, 50, GOLD, w)
        d.line([(w * 0.18, 662), (w * 0.82, 662)], fill=GOLD, width=3)
        y = 710
        for label, key in (("재물", "wealth"), ("애정", "love"), ("건강", "health"), ("직업", "work")):
            d.text((90, y), label, font=_f(34), fill=GOLD)
            txt = r[key]
            f = _fit(d, txt, 32, w - 260, False)
            d.text((200, y + 2), txt, font=f, fill=CREAM)
            y += 92
        d.text((90, y + 20), r["period_note"], font=_fit(d, r["period_note"], 32, w - 180, False), fill=CREAM)
        dd = "길일 " + " · ".join(f"{x}일" for x in r["lucky_days"])
        d.text((90, y + 90), dd, font=_f(32, False), fill=GOLD)
        lucky = f"행운색 {r['lucky_color']} · 숫자 {r['lucky_number']} · 방향 {r['lucky_direction']}"
        d.text((90, y + 158), lucky, font=_fit(d, lucky, 30, w - 180, False), fill=DIM)
        p = out_dir / f"s_single_{r['sign']}.png"; im.save(p, optimize=True); res["single"].append(p)

    res["outro"] = make_outro_card(year, month, out_dir / "s_outro.png")
    return res


def make_outro_card(year: int, month: int, path: Path) -> Path:
    """쇼츠 마무리 카드 1장. AI 카드만 쓰는 조립에서도 마무리는 이 카드를 쓴다
    (URL·가격 글자는 AI에게 그리게 하면 깨지므로 사람이 그린 카드로 낸다)."""
    w, h = 1080, 1920
    path.parent.mkdir(parents=True, exist_ok=True)
    im = _bg(w, h); d = ImageDraw.Draw(im)
    _center(d, f"{month}월,", int(h * 0.26), 96, CREAM, w)
    _center(d, "좋은 흐름 되세요", int(h * 0.34), 96, CREAM, w)
    _center(d, "내 사주로 보는 정밀 월운은", int(h * 0.48), 46, GOLD, w)
    _center(d, "프로필 링크에서", int(h * 0.54), 46, GOLD, w)
    _cta(d, w, h, y=int(h * 0.64))
    _center(d, "재미와 참고용으로 즐겨주세요", int(h * 0.74), 32, DIM, w)
    im.save(path, optimize=True)
    return path


if __name__ == "__main__":
    import sys
    y = int(sys.argv[1]) if len(sys.argv) > 1 else 2026
    m = int(sys.argv[2]) if len(sys.argv) > 2 else 8
    root = BASE / "month" / f"{y}-{m:02d}"
    op = make_onepage(y, m, root / "onepage.png")
    cn = make_cardnews(y, m, root / "cardnews")
    sc = make_shorts_cards(y, m, root / "shorts_cards")
    print(f"한장뉴스 : {op}")
    print(f"카드뉴스 : {len(cn)}장 → {root / 'cardnews'}")
    print(f"쇼츠카드 : 표지1 요약1 그룹{len(sc['group'])} 개별{len(sc['single'])} 마무리1 → {root / 'shorts_cards'}")
