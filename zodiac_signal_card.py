# -*- coding: utf-8 -*-
"""띠 지목 카드뉴스 생성 — 배경 템플릿 12종 + PIL 텍스트 오버레이.

한밝님 지시(2026-08-05): 매일 AI로 새로 뽑지 말고 배경을 미리 만들어 두고 글자만 바꾼다.

왜 이렇게 바꿨나
  · 기존 띠별 카드는 Topview GPT Image 2 가 **글자까지 그렸다** → 매일 6장 생성 =
    크레딧이 계속 나가고, 한글이 깨질 때가 있었고("7월 30일" 실측), 실패에 대비해
    장당 4회 재시도 사다리까지 필요했다.
  · 여기서는 배경(assets/bg/bg_{띠}.png, 글자 없음)을 12종 고정해 두고 텍스트는
    PIL 이 폰트로 얹는다 → 매일 생성 크레딧 0, 한글 깨짐 원천 차단, 실패 가능성 없음.
  · 배경이 12종인 건 우연이 아니다 — zodiac_signal 의 띠 회전이 12일 주기라 정확히 맞는다.

한 장의 배경으로 5장을 만들되 줌·크롭을 달리해 같은 그림이 반복돼 보이지 않게 한다.

실행:
  python zodiac_signal_card.py 2026-08-06            # cards/2026-08-06/signal_01..05.png
  python zodiac_signal_card.py 2026-08-06 --sign dog
"""
from __future__ import annotations
import sys
import datetime as dt
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import zodiac_seo as zs
import zodiac_signal as zsig

BASE = Path(__file__).resolve().parent
BG_DIR = BASE / "assets" / "bg"
FONT_DIR = BASE / "assets" / "fonts"

W, H = 1080, 1920          # 9:16 — 기존 띠별 카드와 같은 비율로 맞춘다
PANEL_ALPHA = 218          # 배경이 복잡해도 글자가 읽히게 하는 최소치(실측으로 조정)

# 러너(ubuntu)에도 있어야 하므로 폰트는 레포에 동봉한다. 없으면 시스템 폰트로 떨어진다.
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


def wrap(dr, text: str, font, max_w: int) -> list[str]:
    """한글은 어절 단위로 끊는다(word-break: keep-all 과 같은 의도)."""
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


def bg_for(slug: str, variant: int) -> Image.Image:
    """배경 1장을 줌·이동으로 변주한다. 5장이 같은 그림으로 안 보이게 하는 장치."""
    src = BG_DIR / f"bg_{slug}.jpg"
    if not src.exists():
        im = Image.new("RGB", (W, H), (226, 236, 247))
    else:
        im = Image.open(src).convert("RGB")
    # 커버 리사이즈
    sc = max(W / im.width, H / im.height)
    im = im.resize((int(im.width * sc), int(im.height * sc)), Image.LANCZOS)

    zoom, dy = [(1.00, 0.0), (1.08, -0.04), (1.14, 0.06),
                (1.10, -0.02), (1.04, 0.03)][variant % 5]
    if zoom > 1.0:
        nw, nh = int(im.width * zoom), int(im.height * zoom)
        im = im.resize((nw, nh), Image.LANCZOS)
    ox = (im.width - W) // 2
    oy = int((im.height - H) // 2 + H * dy)
    oy = max(0, min(oy, im.height - H))
    return im.crop((ox, oy, ox + W, oy + H))


def panel(dr, top: int, bottom: int, pad: int = 60):
    dr.rounded_rectangle([pad, top, W - pad, bottom], radius=48,
                         fill=(255, 255, 255, PANEL_ALPHA))


def card_cover(slug: str, sign_ko: str, years: str, hook: str) -> Image.Image:
    im = bg_for(slug, 0)
    dr = ImageDraw.Draw(im, "RGBA")
    f_sign = F("GowunBatang-Bold.ttf", 132)
    f_year = F("Pretendard-Black.ttf", 54)
    f_hook = F("Pretendard-Black.ttf", 52)

    y = 190
    tw = dr.textlength(sign_ko, font=f_sign)
    # 제목은 패널 없이 얹되 흰 테두리로 배경과 분리한다(밝은 배경이라 검정 글자가 산다).
    dr.text(((W - tw) / 2, y), sign_ko, font=f_sign, fill=(26, 26, 46),
            stroke_width=10, stroke_fill=(255, 255, 255))
    y += 172
    # 생년이 5개라 한 줄이 길다 — 폭에 맞을 때까지 폰트를 줄인다(잘리는 것보다 낫다).
    sz = 54
    for sz in (54, 48, 43, 39, 35):
        f_year = F("Pretendard-Black.ttf", sz)
        yw = dr.textlength(years, font=f_year)
        if yw <= W - 210:
            break
    dr.rounded_rectangle([(W - yw) / 2 - 34, y - 12, (W + yw) / 2 + 34, y + sz + 20],
                         radius=42, fill=(232, 75, 138))
    dr.text(((W - yw) / 2, y), years, font=f_year, fill=(255, 255, 255))

    y += sz + 96
    lines = wrap(dr, hook, f_hook, W - 240)
    panel(dr, y - 34, y + len(lines) * 72 + 26)
    for ln in lines:
        lw = dr.textlength(ln, font=f_hook)
        dr.text(((W - lw) / 2, y), ln, font=f_hook, fill=(26, 26, 46))
        y += 72
    return im


def card_text(slug: str, variant: int, body: str, color=(70, 70, 86),
              font_name="NanumGothic-Regular.ttf", size=52,
              stroke=False) -> Image.Image:
    im = bg_for(slug, variant)
    dr = ImageDraw.Draw(im, "RGBA")
    f = F(font_name, size)
    lines: list[str] = []
    for para in body.split("\n"):
        lines += wrap(dr, para, f, W - 260) if para.strip() else [""]
    lh = int(size * 1.62)
    block = len(lines) * lh
    top = int(H * 0.30) - 40
    panel(dr, top, top + block + 80)
    y = top + 40
    for ln in lines:
        if ln:
            lw = dr.textlength(ln, font=f)
            if stroke:
                dr.text(((W - lw) / 2, y), ln, font=f, fill=color,
                        stroke_width=3, stroke_fill=(255, 255, 255))
            else:
                dr.text(((W - lw) / 2, y), ln, font=f, fill=color)
        y += lh
    return im


def card_quote(slug: str, quote: str, bridge: str) -> Image.Image:
    im = bg_for(slug, 2)
    dr = ImageDraw.Draw(im, "RGBA")
    f_q = F("NanumPenScript-Regular.ttf", 96)
    f_b = F("NanumGothic-Regular.ttf", 46)
    top = int(H * 0.30)
    b_lines = wrap(dr, bridge, f_b, W - 260)
    panel(dr, top - 40, top + 150 + len(b_lines) * 70)

    qw = dr.textlength(quote, font=f_q)
    # 형광펜 — 글자 아래쪽 절반에 깔아 밑줄처럼 보이게 한다.
    dr.rectangle([(W - qw) / 2 - 18, top + 66, (W + qw) / 2 + 18, top + 112],
                 fill=(251, 192, 218))
    dr.text(((W - qw) / 2, top + 10), quote, font=f_q, fill=(40, 30, 40))
    y = top + 150
    for ln in b_lines:
        lw = dr.textlength(ln, font=f_b)
        dr.text(((W - lw) / 2, y), ln, font=f_b, fill=(95, 95, 110))
        y += 70
    return im


def card_cta(slug: str, sign_ko: str, cta: str) -> Image.Image:
    im = bg_for(slug, 4)
    dr = ImageDraw.Draw(im, "RGBA")
    f_t = F("GowunBatang-Bold.ttf", 66)
    f_c = F("Pretendard-Black.ttf", 44)
    top = int(H * 0.32)
    lines = wrap(dr, cta, f_c, W - 260)
    panel(dr, top - 40, top + 130 + len(lines) * 66)
    t = f"{sign_ko}의 흐름"
    tw = dr.textlength(t, font=f_t)
    dr.text(((W - tw) / 2, top + 6), t, font=f_t, fill=(26, 26, 46))
    y = top + 130
    for ln in lines:
        lw = dr.textlength(ln, font=f_c)
        dr.text(((W - lw) / 2, y), ln, font=f_c, fill=(200, 40, 90))
        y += 66
    return im


def build(date_iso: str, slug: str | None = None) -> list[Path]:
    slug = slug or zsig.sign_of(date_iso)
    d = dt.date.fromisoformat(date_iso)
    sign_ko = zs.SLUG_TO_INFO[slug][1]
    if not sign_ko.endswith("띠"):
        sign_ko += "띠"

    angle = zsig.angle_of(date_iso)
    trait, quote, turn = zsig.TRAITS[slug][angle]
    years = " · ".join(zsig.pick_years(slug, date_iso))
    hook = zsig.HOOKS[d.toordinal() % len(zsig.HOOKS)].format(sign=sign_ko)
    bridges = zsig.BRIDGES[angle]
    bridge = bridges[d.toordinal() % len(bridges)]
    cta = zsig.CTA_POOL[d.toordinal() % len(zsig.CTA_POOL)].format(sign=sign_ko)

    out_dir = BASE / "cards" / date_iso
    out_dir.mkdir(parents=True, exist_ok=True)
    imgs = [
        card_cover(slug, sign_ko, years, hook),
        card_text(slug, 1, trait),
        card_quote(slug, quote, bridge),
        card_text(slug, 3, turn, color=(200, 40, 90),
                  font_name="GowunBatang-Bold.ttf", size=60),
        card_cta(slug, sign_ko, cta),
    ]
    # JPEG 로 저장한다 — PNG 는 장당 3MB 라 5장이면 15MB 다. 매일 쌓이면 레포가 감당 못 하고
    # 러너 체크아웃도 느려진다. 사진형 일러스트라 JPEG 손실이 눈에 띄지 않는다.
    paths = []
    for i, im in enumerate(imgs, 1):
        p = out_dir / f"signal_{i:02d}.jpg"
        im.convert("RGB").save(p, "JPEG", quality=88, optimize=True, progressive=True)
        paths.append(p)
    return paths


def main():
    argv = sys.argv[1:]
    slug = None
    if "--sign" in argv:
        i = argv.index("--sign")
        if i + 1 < len(argv):
            slug = argv[i + 1]
    args = [a for a in argv if not a.startswith("--") and a != slug]
    date_iso = args[0] if args else zs.today_iso()
    for p in build(date_iso, slug):
        print(f"[OK] {p.relative_to(BASE)}  {p.stat().st_size // 1024}KB")


if __name__ == "__main__":
    main()
