# -*- coding: utf-8 -*-
"""AI 뉴스 인포그래픽 카드 렌더 (1080x1350, 2026-07-27 신설).

왜 로컬 렌더인가
----------------
Topview(GPT Image 2)로 뽑으면 한글이 가끔 깨진다 — 지목3띠 카드에서 '7월 30일'이
'7월 30얼'로 나온 실측이 있다. 운세 카드는 오타 하나를 넘길 수 있지만 **뉴스는 다르다.**
회사명·금액·연도가 틀리면 그건 허위정보다(운명과학TV 허위콘텐츠 정지 이력).
그래서 텍스트는 전부 PIL 로 직접 그린다. 정확도 100%, 크레딧 0.

폰트
----
로컬은 Gmarket, GitHub 러너(우분투)는 나눔고딕을 쓴다. 워크플로에서
`apt-get install fonts-nanum` 으로 깔아준다. 둘 다 없으면 기본 폰트로 떨어진다.

실행:
  python ai_news_card.py "헤드라인" "해석 문장" "언론사"
"""
from __future__ import annotations

import datetime as dt
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BASE = Path(__file__).resolve().parent
W, H = 1080, 1350          # 4:5 — 스레드 허용 범위(0.01:1~10:1) 안. 정보형은 이 비율이 읽기 좋다

C_BG_TOP = (24, 28, 42)
C_BG_BOT = (46, 40, 72)
C_INK = (247, 246, 250)
C_SUB = (176, 180, 200)
C_ACCENT = (255, 205, 90)
C_BADGE = (138, 30, 62)

FONT_DIRS = [
    Path(r"G:\내 드라이브\01클로드\에셋라이브러리\폰트"),
    Path(r"C:\Windows\Fonts"),
    Path("/usr/share/fonts/truetype/nanum"),          # GitHub 러너(fonts-nanum)
    Path("/usr/share/fonts/truetype/dejavu"),
]
_BOLD = ["GmarketSansTTFBold.ttf", "malgunbd.ttf", "NanumGothicBold.ttf",
         "NanumGothic.ttf", "DejaVuSans-Bold.ttf"]
_REG = ["GmarketSansTTFMedium.ttf", "malgun.ttf", "NanumGothic.ttf",
        "DejaVuSans.ttf"]


_font_reported = False


def _font(names: list[str], size: int):
    global _font_reported
    for d in FONT_DIRS:
        for n in names:
            p = d / n
            if p.exists():
                try:
                    f = ImageFont.truetype(str(p), size)
                    if not _font_reported:
                        # 러너에 한글 폰트가 없으면 글자가 네모로 나온다. 어떤 폰트가
                        # 실제로 잡혔는지 로그로 남겨야 사후에 원인을 찾을 수 있다.
                        print(f"[card] 폰트: {p}", flush=True)
                        _font_reported = True
                    return f
                except OSError:
                    continue
    print("[card] ⚠️ 한글 폰트를 못 찾았습니다 — 기본 폰트로 대체(한글 깨질 수 있음)",
          flush=True)
    return ImageFont.load_default()


def _wrap(dr, text: str, font, max_w: int, max_lines: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = f"{cur} {w}".strip()
        if dr.textlength(t, font=font) <= max_w or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
            if len(lines) == max_lines:
                return lines
    if cur and len(lines) < max_lines:
        lines.append(cur)
    return lines


def _bg(im: Image.Image):
    col = Image.new("RGB", (1, H))
    px = col.load()
    for y in range(H):
        r = y / (H - 1)
        px[0, y] = tuple(int(a + (b - a) * r) for a, b in zip(C_BG_TOP, C_BG_BOT))
    im.paste(col.resize((W, H)), (0, 0))


def _layout(headline: str, body: str, pad: int):
    """실제로 몇 줄이 나오는지 미리 재서 카드 높이를 정한다.

    고정 높이로 그렸더니 본문이 짧은 날 아래 절반이 통째로 비었다(실측).
    스레드는 0.01:1~10:1 이면 크롭하지 않으니 높이를 내용에 맞추는 편이 낫다.
    """
    probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    inner = W - pad * 2
    for size in (66, 60, 54, 48, 42):
        f_h = _font(_BOLD, size)
        lines_h = _wrap(probe, headline, f_h, inner, 5)
        joined = " ".join(lines_h)
        # 잘림 없이(=원문 길이만큼) 들어갔고 4줄 이내면 채택
        if len(joined) >= len(headline) - 1 and len(lines_h) <= 4:
            break
    f_b = _font(_REG, 36)
    lines_b = _wrap(probe, body, f_b, inner, 8)
    return f_h, lines_h, size, f_b, lines_b


def render(headline: str, body: str, source: str, out: Path,
           date: dt.date | None = None) -> Path:
    d = date or dt.date.today()
    pad = 72
    f_h, lines_h, size, f_b, lines_b = _layout(headline, body, pad)

    global H
    top_block = 190                                   # 배지 + 여백
    h_head = len(lines_h) * int(size * 1.34)
    h_body = len(lines_b) * 54
    H = max(900, top_block + h_head + 66 + h_body + 200)

    im = Image.new("RGB", (W, H), C_BG_TOP)
    _bg(im)
    dr = ImageDraw.Draw(im)

    # 상단 배지 — 이 계정이 운세만 하는 곳이 아니라는 표시
    f_badge = _font(_BOLD, 30)
    label = "AI 뉴스"
    bw = dr.textlength(label, font=f_badge) + 46
    dr.rounded_rectangle([pad, 70, pad + bw, 70 + 56], radius=28, fill=C_BADGE)
    dr.text((pad + bw / 2, 98), label, font=f_badge, fill=C_INK, anchor="mm")
    dr.text((pad + bw + 24, 98), f"{d.month}월 {d.day}일",
            font=_font(_REG, 28), fill=C_SUB, anchor="lm")

    # 헤드라인 (크기·줄바꿈은 _layout 에서 이미 확정됐다)
    y = 190
    for ln in lines_h:
        dr.text((pad, y), ln, font=f_h, fill=C_INK)
        y += int(size * 1.34)

    # 구분선
    y += 26
    dr.line([pad, y, W - pad, y], fill=(90, 95, 120), width=2)
    y += 40

    # 해석 2문장
    for ln in lines_b:
        dr.text((pad, y), ln, font=f_b, fill=C_SUB)
        y += 54

    # 하단 — 출처와 유입 문구. 링크(URL)는 넣지 않는다(스레드 도달 저하·제재 회피).
    dr.text((pad, H - 132), f"출처 · {source}", font=_font(_REG, 30), fill=C_SUB)
    dr.text((pad, H - 84), "운세와 AI, 매일 같이 봅니다 · 프로필 링크",
            font=_font(_BOLD, 30), fill=C_ACCENT)

    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out, quality=92)
    return out


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    hl = sys.argv[1] if len(sys.argv) > 1 else "AI데이터센터 판 키운다… 네이버 100억달러 유치"
    bd = sys.argv[2] if len(sys.argv) > 2 else (
        "네이버가 대규모 투자를 유치하고 통신사도 설비를 늘리면서 국내 인공지능 기반 시설 "
        "경쟁이 본격화되고 있습니다. 우리가 쓰는 인공지능 서비스가 더 빠르고 안정적으로 "
        "돌아가는 쪽으로 이어질 전망입니다.")
    sc = sys.argv[3] if len(sys.argv) > 3 else "전자신문"
    p = render(hl, bd, sc, BASE / "cards" / "ai_news" / "_preview.png")
    print(f"OK {p} {p.stat().st_size // 1024}KB")
