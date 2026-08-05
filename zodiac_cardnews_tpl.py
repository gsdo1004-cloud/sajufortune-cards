# -*- coding: utf-8 -*-
"""띠별운세 카드 생성 — 배경 템플릿 12세트 + PIL 텍스트 오버레이.

한밝님 지시(2026-08-05): 매일 AI로 이미지를 새로 뽑지 말고 배경을 미리 만들어 두고
글자만 바꾼다. 크레딧 소모가 크다는 문제 제기에서 출발했다.

기존(zodiac_topview.py)과의 차이
  · 기존: 매일 Topview GPT Image 2 가 6~7장을 **글자까지 그려서** 생성
    → 연 500~1,000 크레딧(12만~29만원), 한글이 깨질 때가 있었고, 실패 대비
      장당 4회 재시도 사다리가 필요했으며, 집 PC 로컬 스케줄에 묶여 있었다.
  · 여기: assets/bg_sets/set01~12 (글자 없는 배경, 1회 생성)을 12일 주기로 돌려 쓰고
    텍스트는 PIL 이 얹는다 → 매일 생성 0원, 한글 깨짐 없음, GitHub Actions 안에서 완결.

세트 = 화풍 1종(수채화·3D클레이·수묵화… 기존 12화풍 회전을 그대로 물려받음).
세트당 6장: 01_표지 / 02~05_띠별A~D(각 3띠) / 06_12띠요약.

데이터는 기존과 동일하게 zodiac_topview.build_rows() 를 쓴다 —
sajufortune.kr /zodiac 과 같은 결정론적 운세라 사이트·카드·쇼츠가 항상 일치한다.

실행:
  python zodiac_cardnews_tpl.py generate [YYYY-MM-DD]
  python zodiac_cardnews_tpl.py generate 2026-08-09 --set 3   # 세트 강제
"""
from __future__ import annotations
import sys
import datetime as dt
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import zodiac_seo as zs
import zodiac_prompt_engine as zpe

BASE = Path(__file__).resolve().parent
SETS_DIR = BASE / "assets" / "bg_sets"
FONT_DIR = BASE / "assets" / "fonts"

W, H = 1080, 1920
N_SETS = 12
# 가독성 우선. 2026-07-25 "글자를 못 읽는다"는 시청자 피드백 이력이 있어
# 패널은 거의 불투명하게, 본문색은 충분히 진하게 잡는다(연회색은 배경이 비치면 바로 죽는다).
PANEL = (255, 255, 255, 243)
INK = (28, 28, 38)
SUB = (62, 62, 78)
ACCENT = (208, 45, 112)

_FALLBACK = ["/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
             "C:/Windows/Fonts/malgun.ttf"]


def F(name: str, size: int):
    p = FONT_DIR / name
    if p.exists():
        return ImageFont.truetype(str(p), size)
    for f in _FALLBACK:
        if Path(f).exists():
            return ImageFont.truetype(f, size)
    return ImageFont.load_default()


# 띠 이모지 — 컬러 이모지 폰트가 있어야 나온다.
# 러너(ubuntu)는 fonts-noto-color-emoji, 로컬(Windows)은 Segoe UI Emoji.
# Noto 는 비트맵 폰트라 크기가 109 로 고정돼 있고 Pillow 가 알아서 축소한다.
_EMOJI_PATHS = [
    ("/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf", 109),
    ("/usr/share/fonts/truetype/noto/NotoColorEmoji-Regular.ttf", 109),
    ("C:/Windows/Fonts/seguiemj.ttf", None),
]
_emoji_cache: dict[int, object] = {}


def EF(size: int):
    """컬러 이모지 폰트. 없으면 None → 호출부가 이모지를 건너뛴다."""
    if size in _emoji_cache:
        return _emoji_cache[size]
    font = None
    for path, fixed in _EMOJI_PATHS:
        if not Path(path).exists():
            continue
        try:
            font = ImageFont.truetype(path, fixed or size)
            break
        except OSError:
            continue
    _emoji_cache[size] = font
    return font


def draw_emoji(dr, xy, ch: str, size: int) -> int:
    """이모지를 그리고 차지한 폭을 돌려준다. 폰트가 없으면 0(=아무것도 안 그림)."""
    f = EF(size)
    if not f or not ch:
        return 0
    try:
        dr.text(xy, ch, font=f, embedded_color=True)
        return size + 12
    except Exception:
        return 0


def set_no(date_iso: str) -> int:
    """12일 주기로 세트를 돌린다. 세트=화풍이라 화풍 회전이 그대로 유지된다."""
    return dt.date.fromisoformat(date_iso).toordinal() % N_SETS + 1


def bg(set_n: int, name: str) -> Image.Image:
    # 배경은 jpg 로 보관한다(png 는 세트 12개에 50MB — 러너가 매번 체크아웃한다).
    p = SETS_DIR / f"set{set_n:02d}" / f"{name}.jpg"
    if not p.exists():                      # 세트가 비면 1번으로 떨어진다(발행이 죽지 않게)
        p = SETS_DIR / "set01" / f"{name}.jpg"
    if not p.exists():
        return Image.new("RGB", (W, H), (232, 240, 250))
    im = Image.open(p).convert("RGB")
    sc = max(W / im.width, H / im.height)
    im = im.resize((int(im.width * sc), int(im.height * sc)), Image.LANCZOS)
    ox, oy = (im.width - W) // 2, (im.height - H) // 2
    return im.crop((ox, oy, ox + W, oy + H))


def wrap(dr, text: str, font, max_w: int) -> list[str]:
    out, cur = [], ""
    for word in text.split():
        t = (cur + " " + word).strip()
        if dr.textlength(t, font=font) <= max_w or not cur:
            cur = t
        else:
            out.append(cur)
            cur = word
    if cur:
        out.append(cur)
    return out


def stars(n: int) -> str:
    n = max(0, min(5, int(n)))
    return "★" * n + "☆" * (5 - n)


def date_full(date_iso: str) -> str:
    d = dt.date.fromisoformat(date_iso)
    wd = ["월", "화", "수", "목", "금", "토", "일"][d.weekday()]
    return f"{d.year}년 {d.month}월 {d.day}일 ({wd})"


# ── 01 표지 / 06 요약 표지 ────────────────────────────────────
def card_cover(set_n: int, date_iso: str, name: str, title: str, sub: str) -> Image.Image:
    im = bg(set_n, name)
    dr = ImageDraw.Draw(im, "RGBA")
    f_t = F("GowunBatang-Bold.ttf", 118)
    f_d = F("Pretendard-Black.ttf", 50)
    f_s = F("NanumGothic-Regular.ttf", 42)

    # 배경 가운데가 비어 있게 뽑았으므로 그 자리에 얹는다.
    cy = int(H * 0.37)
    tw = dr.textlength(title, font=f_t)
    dr.text(((W - tw) / 2, cy), title, font=f_t, fill=INK,
            stroke_width=11, stroke_fill=(255, 255, 255))
    d = date_full(date_iso)
    dw = dr.textlength(d, font=f_d)
    # 제목(118pt)의 실제 높이가 150 가까워서 +150 이면 날짜 배지가 제목에 붙어 보인다.
    # 제목 아래끝에서 한 숨 띄운다.
    y = cy + 206
    dr.rounded_rectangle([(W - dw) / 2 - 32, y - 10, (W + dw) / 2 + 32, y + 70],
                         radius=40, fill=ACCENT)
    dr.text(((W - dw) / 2, y), d, font=f_d, fill=(255, 255, 255))
    if sub:
        sw = dr.textlength(sub, font=f_s)
        dr.text(((W - sw) / 2, y + 120), sub, font=f_s, fill=SUB,
                stroke_width=6, stroke_fill=(255, 255, 255))
    return im


# ── 02~05 띠별 3띠 ───────────────────────────────────────────
# 배경은 왼쪽 1/3 에 동물 3마리를 세로로 세워 두고 오른쪽 2/3 을 비워 뒀다.
# 텍스트를 그 빈 곳에, 각 동물의 세로 중심에 맞춰 얹는다.
BLOCK_Y = (0.150, 0.435, 0.720)      # 동물 3마리의 세로 중심 비율
TEXT_X = int(W * 0.335)              # 오른쪽 텍스트 영역 시작
TEXT_W = W - TEXT_X - 52


def card_group(set_n: int, date_iso: str, name: str,
               rows: list[tuple[str, dict]]) -> Image.Image:
    im = bg(set_n, name)
    dr = ImageDraw.Draw(im, "RGBA")
    f_h = F("Pretendard-Black.ttf", 46)
    f_ko = F("GowunBatang-Bold.ttf", 66)
    f_line = F("NanumGothic-Bold.ttf", 40)
    f_star = F("Pretendard-Black.ttf", 33)

    # 상단 헤더 — 배경 상단 12%를 비워 뒀다.
    hd = f"오늘의 띠별운세 · {date_full(date_iso)}"
    hw = dr.textlength(hd, font=f_h)
    dr.rounded_rectangle([(W - hw) / 2 - 30, 52, (W + hw) / 2 + 30, 130],
                         radius=38, fill=(255, 255, 255, 228))
    dr.text(((W - hw) / 2, 66), hd, font=f_h, fill=INK)

    for (ko, r), yr in zip(rows, BLOCK_Y):
        cy = int(H * yr)
        line_ls = wrap(dr, r["line"], f_line, TEXT_W - 60)
        # 패널 높이 = 상여백18 + 띠이름80 + 리드(52×n) + 별점 2줄(42×2) + 하여백22
        blk = 18 + 80 + len(line_ls) * 52 + 84 + 22
        top = cy - blk // 2
        dr.rounded_rectangle([TEXT_X - 18, top, W - 34, top + blk],
                             radius=34, fill=PANEL)
        y = top + 18
        ew = draw_emoji(dr, (TEXT_X + 14, y + 2), r.get("emoji", ""), 66)
        dr.text((TEXT_X + 14 + ew, y), ko, font=f_ko, fill=INK)
        y += 80
        for ln in line_ls:
            dr.text((TEXT_X + 16, y), ln, font=f_line, fill=SUB)
            y += 52
        st = r["stars"]
        s = (f"전체 {stars(st['전체'])}   금전 {stars(st['금전'])}\n"
             f"연애 {stars(st['연애'])}   건강 {stars(st['건강'])}")
        for i, ln in enumerate(s.split("\n")):
            dr.text((TEXT_X + 16, y + i * 42), ln, font=f_star, fill=ACCENT)
    return im


# ── 06 12띠 요약 ─────────────────────────────────────────────
def card_summary(set_n: int, date_iso: str, allrows: dict[str, dict]) -> Image.Image:
    im = bg(set_n, "06_12띠요약")
    dr = ImageDraw.Draw(im, "RGBA")
    f_h = F("Pretendard-Black.ttf", 48)
    # 셀 높이가 260 인데 내용이 180 밖에 안 차 아래가 비었다 → 전부 키워 채운다(2026-08-05).
    f_ko = F("GowunBatang-Bold.ttf", 54)
    f_st = F("Pretendard-Black.ttf", 35)

    hd = f"12띠 총정리 · {date_full(date_iso)}"
    hw = dr.textlength(hd, font=f_h)
    dr.rounded_rectangle([(W - hw) / 2 - 30, 50, (W + hw) / 2 + 30, 132],
                         radius=38, fill=(255, 255, 255, 230))
    dr.text(((W - hw) / 2, 66), hd, font=f_h, fill=INK)

    # 12띠를 2열 6행. 큰 패널 하나로 덮으면 배경 동물이 뿌옇게 비쳐 지저분하고
    # 가운데가 텅 빈다(2026-08-05 실측) → 셀마다 작은 패널을 두고 배경은 살린다.
    order = [ko for g in zpe.GROUPS for ko in g]
    top, bot = 176, H - 120
    gap_x, gap_y = 16, 12
    cw = (W - 88 - gap_x) // 2
    ch = (bot - top - gap_y * 5) // 6
    f_ln = F("NanumGothic-Bold.ttf", 34)
    for i, ko in enumerate(order):
        cx = 44 + (i % 2) * (cw + gap_x)
        cy = top + (i // 2) * (ch + gap_y)
        dr.rounded_rectangle([cx, cy, cx + cw, cy + ch], radius=26, fill=PANEL)
        st = allrows[ko]["stars"]
        ew = draw_emoji(dr, (cx + 20, cy + 18), allrows[ko].get("emoji", ""), 54)
        dr.text((cx + 20 + ew, cy + 16), ko, font=f_ko, fill=INK)
        dr.text((cx + 22, cy + 84), f"전체 {stars(st['전체'])}", font=f_st, fill=ACCENT)
        # 한 줄 운세까지 넣어야 셀이 채워지고 저장할 이유가 생긴다.
        for j, ln in enumerate(wrap(dr, allrows[ko]["line"], f_ln, cw - 44)[:2]):
            dr.text((cx + 22, cy + 134 + j * 40), ln, font=f_ln, fill=SUB)
    return im


def build(date_iso: str, force_set: int | None = None) -> list[Path]:
    import zodiac_topview as zt          # build_rows 재사용(사이트와 같은 운세 데이터)
    sn = force_set or set_no(date_iso)
    rows = zt.build_rows(date_iso)
    # build_rows 에는 이모지가 없다 — 기존 코드를 건드리지 않고 여기서 얹는다.
    for ko, r in rows.items():
        r.setdefault("emoji", zs.SIGN_EMOJI.get(zs.KO_TO_SLUG.get(ko, ""), ""))
    out = BASE / "cards" / date_iso
    out.mkdir(parents=True, exist_ok=True)

    imgs = [("01_표지", card_cover(sn, date_iso, "01_표지", "오늘의 운세", "12띠 전체 흐름"))]
    for gi, (gname, group) in enumerate(zip(
            ["02_띠별A", "03_띠별B", "04_띠별C", "05_띠별D"], zpe.GROUPS)):
        imgs.append((gname, card_group(sn, date_iso, gname,
                                       [(ko, rows[ko]) for ko in group])))
    imgs.append(("06_12띠요약", card_summary(sn, date_iso, rows)))

    paths = []
    for i, (_, im) in enumerate(imgs, 1):
        p = out / f"card_{i:02d}.jpg"
        im.convert("RGB").save(p, "JPEG", quality=88, optimize=True, progressive=True)
        paths.append(p)
    return paths


def main():
    argv = sys.argv[1:]
    force = None
    if "--set" in argv:
        i = argv.index("--set")
        if i + 1 < len(argv):
            force = int(argv[i + 1])
    args = [a for a in argv if not a.startswith("--") and a != str(force)]
    if args and args[0] == "generate":
        args = args[1:]
    date_iso = args[0] if args else zs.today_iso()
    sn = force or set_no(date_iso)
    print(f"=== {date_iso} 띠별 카드 (세트 {sn}) ===")
    for p in build(date_iso, force):
        print(f"[OK] {p.name}  {p.stat().st_size // 1024}KB")


if __name__ == "__main__":
    main()
