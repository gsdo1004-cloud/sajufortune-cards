"""정통명리엔진 스레드 캐러셀 카드 생성.

AI로 만든 배경에 결정론적 타이포그래피를 얹어, 이미지 생성기의 한글 깨짐 없이
promo/engine/card_01.png..card_06.png을 만든다.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

import promo_content as pc


BASE = Path(__file__).resolve().parent
OUT = BASE / "promo" / "engine"
BACKGROUND = OUT / "background.png"
SIZE = (768, 1360)
FONT_BOLD = Path(r"C:\Windows\Fonts\malgunbd.ttf")
FONT_REGULAR = Path(r"C:\Windows\Fonts\malgun.ttf")


def font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(path), size=size)


def centered(draw: ImageDraw.ImageDraw, text: str, y: int, text_font, fill, spacing=12):
    box = draw.multiline_textbbox((0, 0), text, font=text_font, spacing=spacing,
                                  align="center")
    width = box[2] - box[0]
    draw.multiline_text(((SIZE[0] - width) // 2, y), text, font=text_font,
                        fill=fill, spacing=spacing, align="center")


def make_card(headline: str, sub: str, index: int) -> Image.Image:
    base = Image.open(BACKGROUND).convert("RGB")
    base = base.resize(SIZE, Image.Resampling.LANCZOS)
    base = ImageEnhance.Brightness(base).enhance(0.77)
    # 상단 문구의 대비만 보강하며 원본 배경의 질감과 하단 책 이미지는 유지한다.
    shade = Image.new("RGBA", SIZE, (7, 14, 28, 0))
    alpha = Image.new("L", SIZE, 0)
    alpha_draw = ImageDraw.Draw(alpha)
    alpha_draw.rectangle((0, 0, SIZE[0], 650), fill=185)
    alpha_draw.rectangle((0, 600, SIZE[0], SIZE[1]), fill=35)
    shade.putalpha(alpha.filter(ImageFilter.GaussianBlur(45)))
    card = Image.alpha_composite(base.convert("RGBA"), shade)
    draw = ImageDraw.Draw(card)

    gold = (217, 179, 97, 255)
    ivory = (248, 241, 223, 255)
    muted = (211, 202, 181, 255)
    draw.line((90, 130, 678, 130), fill=gold, width=2)
    centered(draw, "대박운세  |  정통명리엔진", 165, font(FONT_REGULAR, 25), gold)
    centered(draw, headline, 285, font(FONT_BOLD, 57), ivory, spacing=18)
    centered(draw, sub, 470, font(FONT_REGULAR, 31), muted, spacing=12)
    draw.line((90, 610, 678, 610), fill=(217, 179, 97, 135), width=1)
    centered(draw, f"0{index}  /  06", 1215, font(FONT_REGULAR, 22), gold)
    centered(draw, "사주명리학을 바탕으로 한 참고용 해석", 1260,
             font(FONT_REGULAR, 18), (203, 196, 181, 230))
    return card.convert("RGB")


def main() -> None:
    if not BACKGROUND.exists():
        raise SystemExit(f"[FAIL] 배경이 없습니다: {BACKGROUND}")
    for index, card in enumerate(pc.BY_KEY["engine"]["cards"], 1):
        output = OUT / f"card_{index:02d}.png"
        make_card(card["headline"], card["sub"], index).save(output, quality=95)
        print(f"[OK] {output.name}")


if __name__ == "__main__":
    main()
