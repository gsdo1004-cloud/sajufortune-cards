# -*- coding: utf-8 -*-
"""당근 비즈프로필 소식 자동 생성 — 본문 + 카드 6장. 유료 API 호출 없음(크레딧 0).

왜 라이브에서 상품을 읽는가
  한밝님 지적(2026-08-07): "옛날 라우트는 정보가 달라. 홈페이지 최신정보를 반영하지 않았어."
  그래서 상품명·가격·랜딩 URL을 코드에 박지 않고 실행할 때마다
  https://sajufortune.kr/karrot-feed.csv 를 읽는다. 홈페이지가 바뀌면 자동으로 따라간다.

운세 문구는 zodiac_seo.make_reading(결정론적 seed 기반)을 그대로 쓴다 — LLM 호출이 없으므로
매일 돌려도 비용이 0이고, 같은 날짜면 같은 결과가 나와 재현이 된다.

카드 톤은 작업실 규칙을 따른다: 밝은 배경(크림) + 굵은 글자, 다크 톤 금지.

실행:
  python daangn_auto.py                    # 오늘 날짜로 생성
  python daangn_auto.py --date 2026-08-08
  python daangn_auto.py --clip             # 본문을 클립보드에 넣기
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BASE = Path(__file__).resolve().parent
FONT_DIR = BASE / "assets" / "fonts"
OUT_ROOT = BASE / "daangn"            # 리포 안에 둔다 — Actions 가 커밋해 폰에서 받는다

import zodiac_seo as zs               # noqa: E402
import daangn_guard as guard          # noqa: E402

FEED_URL = "https://sajufortune.kr/karrot-feed.csv"
FREE_LANDING = "https://sajufortune.kr/unse/today"     # 무료 진입 — 소식 CTA 목적지
SITE = "sajufortune.kr"

W = H = 1080                          # 당근 피드는 정사각형이 잘리지 않는다
CREAM = (255, 248, 240)
ORANGE = (255, 107, 0)                # 브랜드 포인트
INK = (34, 30, 28)
GRAY = (120, 112, 106)

# 카드 2~5에 3띠씩 나눠 담는다(12띠 ÷ 4장)
PER_CARD = 3


def F(name: str, size: int) -> ImageFont.FreeTypeFont:
    p = FONT_DIR / name
    if p.exists():
        return ImageFont.truetype(str(p), size)
    return ImageFont.truetype("C:/Windows/Fonts/malgun.ttf", size)


def EMOJI(size: int):
    """본문 폰트에는 이모지 글리프가 없어 두부(□)로 찍힌다 — 컬러 이모지 폰트를 따로 쓴다.
    러너(ubuntu)에는 seguiemj 가 없으므로 None 을 돌려주고 호출부가 이모지를 생략한다."""
    for p in ("C:/Windows/Fonts/seguiemj.ttf",
              "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"):
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                return None
    return None


def stars(score: int) -> str:
    """make_reading 의 점수는 1~5 스케일이다(2026-08-07 실측)."""
    return "★" * max(1, min(5, int(score)))


def fetch_products() -> list[dict]:
    """라이브 카탈로그 피드에서 현재 판매 상품을 읽는다. 심사 위험 SKU는 걸러낸다."""
    # 기본 Python UA 는 403 으로 막힌다(Cloudflare) — 브라우저 UA 를 붙인다.
    req = urllib.request.Request(FEED_URL, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/127.0 Safari/537.36",
    })
    with urllib.request.urlopen(req, timeout=20) as r:
        body = r.read().decode("utf-8")
    rows = list(csv.DictReader(io.StringIO(body)))
    return [r for r in rows if guard.product_allowed(r["id"], r["title"])]


def wrap(dr: ImageDraw.ImageDraw, text: str, font, max_w: int) -> list[str]:
    """한글은 어절 단위로 끊는다."""
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


def first_sentence(text: str, limit: int = 46) -> str:
    """카드에 넣을 한 줄만 뽑는다."""
    for mark in (". ", "? ", "! ", "다.", "요."):
        i = text.find(mark)
        if 0 < i <= limit:
            return text[: i + len(mark)].strip()
    return text[:limit].rstrip() + ("…" if len(text) > limit else "")


def canvas() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (W, H), CREAM)
    return img, ImageDraw.Draw(img)


def header(dr: ImageDraw.ImageDraw, label: str) -> None:
    """상단 주황 바 — 밝은 배경에서 시선을 먼저 잡는 자리."""
    dr.rectangle([0, 0, W, 132], fill=ORANGE)
    f = F("Pretendard-Black.ttf", 46)
    dr.text((60, 66), label, font=f, fill="white", anchor="lm")


def footer(dr: ImageDraw.ImageDraw, note: str = SITE) -> None:
    f = F("NanumGothic-Bold.ttf", 34)
    dr.text((W // 2, H - 58), note, font=f, fill=GRAY, anchor="mm")


def card_cover(date_ko: str, readings: list) -> Image.Image:
    img, dr = canvas()
    header(dr, "오늘의 띠별 운세")

    ft = F("GowunBatang-Bold.ttf", 96)
    dr.text((60, 250), date_ko, font=ft, fill=INK)

    fs = F("GowunBatang-Bold.ttf", 64)
    dr.text((60, 380), "열두 띠 중", font=fs, fill=INK)
    dr.text((60, 466), "내 띠는 어떤가", font=fs, fill=ORANGE)

    # 상위 3띠를 표지에 미리 보여준다(스크롤을 멈추게 하는 장치)
    top = sorted(readings, key=lambda r: r.overall_score, reverse=True)[:3]
    fb = F("NanumGothic-Bold.ttf", 40)
    y = 640
    dr.text((60, y), "오늘 흐름이 좋은 띠", font=fb, fill=GRAY)
    y += 66
    fe = F("NanumGothic-Bold.ttf", 52)
    dr.text((60, y), "   ".join(r.sign_ko for r in top), font=fe, fill=INK)

    footer(dr, f"{SITE} · 무료")
    return img


def card_signs(label: str, group: list) -> Image.Image:
    img, dr = canvas()
    header(dr, label)

    y = 210
    fn = F("GowunBatang-Bold.ttf", 60)
    fb = F("NanumGothic-Regular.ttf", 34)
    fem = EMOJI(48)
    for r in group:
        x = 60
        if fem:
            dr.text((x, y + 10), r.emoji, font=fem, embedded_color=True)
            x += 68
        dr.text((x, y), r.sign_ko, font=fn, fill=INK)
        dr.text((W - 60, y + 18), stars(r.overall_score),
                font=F("NanumGothic-Bold.ttf", 40), fill=ORANGE, anchor="rm")
        y += 86
        for ln in wrap(dr, first_sentence(r.overall), fb, W - 130)[:2]:
            dr.text((64, y), ln, font=fb, fill=GRAY)
            y += 46
        y += 34

    footer(dr)
    return img


def card_cta(products: list[dict]) -> Image.Image:
    img, dr = canvas()
    header(dr, "무료로 더 보기")

    ft = F("GowunBatang-Bold.ttf", 72)
    dr.text((60, 240), "띠 운세 전체와", font=ft, fill=INK)
    dr.text((60, 330), "내 사주 풀이는", font=ft, fill=INK)

    # 주소를 눈에 박히게 — 소식 본문의 링크와 같은 곳
    dr.rounded_rectangle([60, 460, W - 60, 590], radius=24, fill=ORANGE)
    fu = F("Pretendard-Black.ttf", 54)
    dr.text((W // 2, 525), SITE, font=fu, fill="white", anchor="mm")

    fb = F("NanumGothic-Bold.ttf", 36)
    dr.text((60, 646), "오늘 운세 · 성향 풀이 · 열두 띠 전체 무료", font=fb, fill=GRAY)

    # 상품은 라이브 피드에서 읽은 것만 쓴다(가격은 적지 않는다 — 바뀌면 허위표시가 된다)
    names = [p["title"] for p in products[:4]]
    fs = F("NanumGothic-Regular.ttf", 32)
    y = 720
    for n in names:
        dr.text((64, y), f"· {n}", font=fs, fill=INK)
        y += 46

    fd = F("NanumGothic-Regular.ttf", 26)
    dr.text((60, H - 108), "운세는 참고용입니다.", font=fd, fill=GRAY)
    footer(dr)
    return img


def build_post_text(date_ko: str, readings: list) -> str:
    """소식 본문. 80~280자, 이모지 절제, 면책 1줄, 링크 1개."""
    top = sorted(readings, key=lambda r: r.overall_score, reverse=True)[:3]
    tops = ", ".join(f"{r.sign_ko}" for r in top)
    text = (
        f"{date_ko} 열두 띠 운세를 정리했어요.\n\n"
        f"오늘 흐름이 좋은 띠는 {tops}입니다. "
        f"나머지 띠도 카드에 한 줄씩 담았으니 내 띠를 찾아보세요.\n\n"
        f"띠 운세 전체와 생년월일로 보는 성향 풀이는 아래에서 무료로 볼 수 있어요.\n"
        f"{FREE_LANDING}\n\n"
        f"운세는 참고용입니다 🙂"
    )
    safe = guard.soften(text)
    guard.assert_safe(safe, "소식 본문")
    return safe


def to_clipboard(text: str) -> bool:
    """PowerShell 로 넘긴다 — 한글이 깨지지 않게 UTF-8 파일을 경유한다."""
    tmp = OUT_ROOT / "_clip.txt"
    tmp.write_text(text, encoding="utf-8")
    r = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         f"Get-Content -Raw -Encoding UTF8 '{tmp}' | Set-Clipboard"],
        capture_output=True,
    )
    return r.returncode == 0


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=dt.date.today().isoformat())
    ap.add_argument("--clip", action="store_true", help="본문을 클립보드에 넣는다")
    args = ap.parse_args()

    date_iso = args.date
    d = dt.date.fromisoformat(date_iso)
    date_ko = f"{d.month}월 {d.day}일"

    out = OUT_ROOT / date_iso
    out.mkdir(parents=True, exist_ok=True)

    products = fetch_products()
    print(f"라이브 피드 상품 {len(products)}종 (심사 위험 SKU 제외 후)")

    # all_signs() 는 {"slug","ko","branch","years"} dict 리스트를 준다
    readings = [zs.make_reading(s["slug"], date_iso) for s in zs.all_signs()]

    cards: list[tuple[str, Image.Image]] = [("card_01.png", card_cover(date_ko, readings))]
    for i in range(0, len(readings), PER_CARD):
        group = readings[i:i + PER_CARD]
        n = i // PER_CARD + 2
        cards.append((f"card_{n:02d}.png", card_signs(f"{date_ko} 띠별 운세", group)))
    cards.append((f"card_{len(cards) + 1:02d}.png", card_cta(products)))

    for name, img in cards:
        img.save(out / name, "PNG", optimize=True)
    print(f"카드 {len(cards)}장 저장 → {out}")

    text = build_post_text(date_ko, readings)
    (out / "post.txt").write_text(text, encoding="utf-8")
    (out / "meta.json").write_text(json.dumps({
        "date": date_iso,
        "landing": FREE_LANDING,
        "cards": [n for n, _ in cards],
        "products_in_feed": [p["id"] for p in products],
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n--- 소식 본문 ---")
    print(text)
    print(f"\n글자수 {len(text)}자 · 심사 필터 통과")

    if args.clip and to_clipboard(text):
        print("클립보드에 본문을 넣었습니다.")


if __name__ == "__main__":
    main()
