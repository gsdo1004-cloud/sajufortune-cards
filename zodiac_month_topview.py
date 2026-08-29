# -*- coding: utf-8 -*-
"""zodiac_month_topview.py — 월간 띠별운세 카드 6장을 Topview GPT Image 2로 생성 (2026-07-25)

구성 (한밝님 지시): 표지 1 + 3띠씩 4장 + 12띠 종합 1 = **6장**. 12장씩 만들지 않는다.

일일 파이프라인(zodiac_topview·zodiac_prompt_engine)은 **건드리지 않는다**.
매일 18시에 도는 자동발행을 깨뜨릴 수 없어, 프롬프트 문자열만 월간용으로 새로 짜고
생성·검증·재시도 로직(ensure_one)과 테마 축(daily_theme)은 그대로 빌려 쓴다.

생성 후 프로필 유입 배지를 Pillow로 덧씌운다 — AI에게 URL·가격을 그리게 하면
글자가 깨지므로, 그 부분만 사람이 그린다.
"""
from __future__ import annotations

import argparse
import datetime as _dt
from pathlib import Path

import zodiac_prompt_engine as zpe
import zodiac_topview as zt
from zodiac_month import all_month_readings, month_label

BASE = Path(__file__).resolve().parent
GROUP_NAMES = ["띠별A", "띠별B", "띠별C", "띠별D"]


def log(msg: str) -> None:
    print(f"[month-topview {_dt.datetime.now():%H:%M:%S}] {msg}", flush=True)


def _theme(year: int, month: int) -> dict:
    """월간 테마 — 달마다 화풍이 바뀌도록 그 달 1일 기준으로 축을 뽑는다."""
    return zpe.daily_theme(_dt.date(year, month, 1))


def _rows(year: int, month: int) -> list[dict]:
    out = []
    for r in all_month_readings(year, month):
        out.append({
            "ko": r["sign_ko"],
            "headline": r["headline"],
            "score": r["score"],
            "stars": r["stars"],
            "wealth": r["wealth"],
            "best": (r["best_period"] or {}).get("ten", "고른 흐름"),
            "days": "·".join(str(d) for d in r["lucky_days"]),
        })
    return out


def _stars(n: int) -> str:
    n = max(1, min(5, int(n)))
    return "★" * n + "☆" * (5 - n)


def cover_prompt(year: int, month: int, t: dict, simple: bool = False) -> str:
    guide = zpe._zodiac_feature_guide(zpe.ZODIAC12)
    deco = (f"Background: {t['bg'][1]}. Lucky props scattered: {', '.join(t['props'])}. "
            if not simple else
            "Background: soft plain auspicious gradient with gentle light rays. ")
    return (
        f"Vertical 9:16 Korean MONTHLY fortune COVER poster. "
        f"Large bold clean Korean title '{month}월 띠별운세' at top center, "
        f"subtitle '{year}년 {month_label(year, month)}' clearly just below in smaller Korean type. "
        f"{zpe.ZODIAC_COMMON_BASE} All twelve cute Korean zodiac animals (rat, ox, tiger, rabbit, dragon, snake, "
        f"horse, sheep, monkey, rooster, dog, pig) are gently arranged in a soft "
        f"circular mandala-wheel formation around the title, each animal in its own graceful "
        f"position along the circle — not a grid, not stacked rows. Species guide: {guide}. "
        f"Scene accents: {t['concept'][1]}. "
        f"{deco}{t['palette'][1]}. Art style: {t['style'][1]}. "
        f"{zpe._SNAKE_GUARD} Warm auspicious festive lucky mood. {zpe._NEG}"
    )


def group_prompt(year: int, month: int, rows: list[dict], t: dict, simple: bool = False) -> str:
    comp = t.get("composition") or zpe.GROUP_COMPOSITIONS[0]
    guide = zpe._zodiac_feature_guide([r["ko"] for r in rows])
    secs = ""
    for i, r in enumerate(rows, 1):
        en = zpe.ZODIAC_EN.get(r["ko"], "animal")
        feature = zpe.ZODIAC_FEATURES.get(r["ko"], "a cute natural animal mascot")
        secs += (f"Vignette {i} — a cute {en} zodiac mascot ({feature}) labeled '{r['ko']}' in elegant small "
                 f"Korean type, its monthly one-line '{r['headline']}' and star line "
                 f"'{_stars(r['stars'])}' gently placed beside it, not boxed or tabled. ")
    deco = (f"Background: {t['bg'][1]}. " if not simple else
            "Background: soft plain auspicious gradient. ")
    return (
        f"Vertical 9:16 Korean MONTHLY fortune card for three zodiac signs. "
        f"Small header '{month}월 띠별운세' at top center in clean Korean type. "
        f"{zpe.ZODIAC_COMMON_BASE} Three cute Korean zodiac animals {comp[1]}. "
        f"Species guide: {guide}. Scene accents: {t['concept'][1]}. "
        f"{secs}{deco}{t['palette'][1]}. Art style: {t['style'][1]}. "
        f"{zpe._SNAKE_GUARD} Warm auspicious mood, generous spacing, readable Korean text. {zpe._NEG}"
    )


def summary12_prompt(year: int, month: int, rows: list[dict], t: dict, simple: bool = False) -> str:
    """12띠 전부를 한 장에 — 시청자가 일시정지해 자기 띠를 찾는 카드."""
    cells = ""
    for r in rows:
        cells += (f"'{r['ko']}' {r['score']}점 {_stars(r['stars'])} / "
                  f"'{r['headline']}' / 길일 {r['days']}일; ")
    guide = zpe._zodiac_feature_guide(zpe.ZODIAC12)
    deco = "" if simple else f"Soft {t['bg'][1]} as a light background wash. "
    return (
        f"Vertical 9:16 Korean MONTHLY fortune SUMMARY card containing ALL TWELVE zodiac signs "
        f"in a clean 3-column x 4-row grid of rounded cards. "
        f"Header at top center: '{year}년 {month}월 띠별운세' with smaller '{month_label(year, month)}' below. "
        f"{zpe.ZODIAC_COMMON_BASE} Each of the twelve cells shows a small cute natural zodiac animal mascot icon, its Korean name, "
        f"a score, a star row, one short Korean line, and a lucky-days line: {cells}"
        f"Species guide: {guide}. "
        f"{deco}Bright clean editorial layout, generous padding, soft card shadows, "
        f"small but crisp readable Korean typography. {t['palette'][1]}. "
        f"Art style: {t['style'][1]}. {zpe._SNAKE_GUARD} {zpe._NEG}"
    )


def month_set(year: int, month: int) -> dict:
    """표지1 + 3띠×4 + 12띠종합1 = 6장 스펙."""
    t = _theme(year, month)
    rows = _rows(year, month)
    images = [{
        "name": "표지", "file": "01_표지", "signs": list(zpe.ZODIAC12),
        "prompt": cover_prompt(year, month, t),
        "simple_prompt": cover_prompt(year, month, t, simple=True),
    }]
    for gi, group in enumerate(zpe.GROUPS):
        g = [r for r in rows if r["ko"] in group]
        images.append({
            "name": GROUP_NAMES[gi], "file": f"{gi + 2:02d}_{GROUP_NAMES[gi]}",
            "signs": list(group),
            "prompt": group_prompt(year, month, g, t),
            "simple_prompt": group_prompt(year, month, g, t, simple=True),
        })
    images.append({
        "name": "12띠종합", "file": "06_12띠종합", "signs": list(zpe.ZODIAC12),
        "prompt": summary12_prompt(year, month, rows, t),
        "simple_prompt": summary12_prompt(year, month, rows, t, simple=True),
    })
    return {"theme": t, "images": images}


# ── 프로필 유입 배지 (AI가 그린 그림 위에 사람이 얹는다) ──────────
CTA_TEXT = "무료 운세 · 이용권 1,000원 · 프로필 링크"


def _find_clean_band(im, lo: float = 0.06, hi: float = 0.78, band: float = 0.058) -> float:
    """글자·그림이 가장 적은 가로 띠를 찾아 그 중심 y비율을 돌려준다.

    고정 위치(76%)로 얹었더니 '호랑이띠'·3번째 줄 문구를 덮었다. 카드마다 제목 높이와
    본문 시작점이 달라서, 값 하나로는 못 맞춘다.
    '어두운 픽셀=글자' 기준을 먼저 썼는데, 밝은 배경에 밝은 글자(2026-08 카드)에서는
    글자를 못 봐 '쥐띠'·'닭띠' 이름을 덮었다. 그래서 밝기 대신 **엣지 에너지**로 판단한다.
    글자든 그림이든 윤곽이 있으면 에너지가 높고, 하늘·여백은 낮다.
    하단은 유튜브 UI가 덮으므로 78%까지만 본다. 같은 값이면 위쪽을 택한다.
    """
    from PIL import Image, ImageFilter
    w, h = im.size
    # 폭 1로 줄이면 각 행의 평균 엣지 강도가 한 번에 나온다(행 단위 스캔보다 훨씬 빠름).
    g = im.convert("L").filter(ImageFilter.FIND_EDGES)
    g = g.crop((int(w * 0.06), 0, int(w * 0.94), h)).resize((1, h), Image.BOX)
    rows = [g.getpixel((0, y)) for y in range(h)]

    # 배지보다 넓은 구간(1.8배)이 통째로 조용해야 여백으로 인정한다.
    # 딱 배지 높이만 봤더니 표지에서 '8월'과 '띠별운세' 줄 사이 좁은 틈을 골라 제목을 덮었다.
    bh = int(h * band)
    ch = int(bh * 1.8)
    best, best_score = int(h * lo), None
    for top in range(int(h * lo), max(int(h * lo) + 1, int(h * hi) - ch), max(3, bh // 8)):
        e = sum(rows[top:top + ch]) / ch
        pos = (top + ch / 2) / h
        score = e * (1.0 + 0.30 * pos)             # 값이 비슷하면 위쪽 우선
        if best_score is None or score < best_score:
            best_score, best = score, top
    return (best + ch / 2) / h


def add_cta(path: Path) -> None:
    """AI 카드 '제목 바로 아래' 여백에 CTA 배지를 얹는다.

    URL·가격을 AI에게 그리게 하면 글자가 깨지므로 그 부분만 사람이 그린다.
    실패해도 원본을 그대로 둔다(영상 조립은 계속돼야 한다).
    """
    try:
        from PIL import Image, ImageDraw, ImageFilter, ImageFont
        im = Image.open(path).convert("RGBA")
        w, h = im.size
        pw, ph = int(w * 0.86), max(46, int(h * 0.042))
        cx, cy = w // 2, int(h * _find_clean_band(im))
        box = [cx - pw // 2, cy - ph // 2, cx + pw // 2, cy + ph // 2]

        sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
        ImageDraw.Draw(sh).rounded_rectangle([box[0], box[1] + 6, box[2], box[3] + 6],
                                             radius=ph // 2, fill=(0, 0, 0, 110))
        im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(8)))

        d = ImageDraw.Draw(im)
        d.rounded_rectangle(box, radius=ph // 2, fill=(107, 31, 55, 255),
                            outline=(255, 248, 235, 255), width=max(3, ph // 20))

        fp = None
        for c in (Path(r"G:\내 드라이브\01클로드\에셋라이브러리\폰트\GmarketSansTTFBold.ttf"),
                  Path(r"C:\Windows\Fonts\malgunbd.ttf")):
            if c.exists():
                fp = c
                break
        size = int(ph * 0.52)
        while size > 10:
            f = ImageFont.truetype(str(fp), size) if fp else ImageFont.load_default()
            if d.textbbox((0, 0), CTA_TEXT, font=f)[2] <= pw * 0.9 or not fp:
                break
            size -= 1
        bb = d.textbbox((0, 0), CTA_TEXT, font=f)
        d.text((cx - (bb[2] - bb[0]) / 2, cy - (bb[3] - bb[1]) / 2 - bb[1] / 2),
               CTA_TEXT, font=f, fill=(255, 248, 235, 255))
        im.convert("RGB").save(path)
    except Exception as e:
        log(f"  [!] CTA 배지 실패({e}) — 원본 유지: {path.name}")


def ensure_month_images(year: int, month: int, with_cta: bool = False) -> dict:
    """6장 보장 생성(멱등). 이미 있으면 건너뛴다.

    2026-07-25: CTA 배지는 **기본 끔**. AI 카드마다 제목·띠 이름 위치가 달라
    자동 배치가 '8월'·'쥐띠'·'닭띠'를 덮었다(3회 시도 실패). 한밝님 지시로
    유입 문구는 그림 대신 **쇼츠 나레이션(TTS)**으로 넣는다.
    배지가 필요하면 `--cta`로 켤 수 있다.
    """
    out_dir = BASE / "month" / f"{year}-{month:02d}" / "ai_cards"
    out_dir.mkdir(parents=True, exist_ok=True)

    ms = month_set(year, month)
    t = ms["theme"]
    log(f"=== {year}년 {month}월 카드 6장 생성 ({zt.MODEL}) ===")
    log(f"이달 조합: [{t['style'][0]}] 배경={t['bg'][0]} 컨셉={t['concept'][0]} "
        f"색={t['palette'][0]} 구도={t['composition'][0]}")

    alerts: list[str] = []
    client = zt.make_client()
    zt.check_balance(client, alerts)

    files, failed, dead = [], [], set()
    for i, spec in enumerate(ms["images"], 1):
        out = out_dir / f"card_{i:02d}.png"
        if out.exists() and out.stat().st_size > 50_000:
            log(f"  [{i}/6] {spec['name']} 이미 있음 — 건너뜀")
            files.append(str(out))
            continue
        log(f"  [{i}/6] {spec['name']} 생성 중…")
        if zt.ensure_one(client, spec, out, alerts, dead):
            if with_cta:
                add_cta(out)
            files.append(str(out))
        else:
            failed.append(spec["name"])
            if dead >= {"rest", "mcp"}:
                log("  [!] REST·MCP 두 경로 모두 실패 — 중단")
                break

    log(f"=== 결과: {len(files)}/6 성공"
        f"{' | 실패: ' + ', '.join(failed) if failed else ''} ===")
    return {"year": year, "month": month, "ok": not failed,
            "dir": out_dir, "files": files, "failed": failed, "alerts": alerts}


def apply_cta_all(year: int, month: int) -> int:
    """생성된 6장에 CTA 배지를 입힌다(원본은 raw/ 에 보관 → 위치 조정 시 재생성 불필요)."""
    import shutil
    d = BASE / "month" / f"{year}-{month:02d}" / "ai_cards"
    raw = d / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    n = 0
    for p in sorted(d.glob("card_*.png")):
        src = raw / p.name
        if not src.exists():                 # 최초 1회만 원본 보관
            shutil.copy2(p, src)
        shutil.copy2(src, p)                 # 항상 깨끗한 원본에서 다시 시작
        add_cta(p)
        n += 1
    log(f"CTA 배지 {n}장 적용 (원본 보관: {raw})")
    return n


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="월간 띠별운세 카드 6장 (Topview GPT Image 2)")
    ap.add_argument("--cta-only", action="store_true", help="생성 없이 기존 카드에 CTA만 다시 입힘")
    today = _dt.date.today()
    nxt = _dt.date(today.year + (today.month == 12), (today.month % 12) + 1, 1)
    ap.add_argument("--year", type=int, default=nxt.year)
    ap.add_argument("--month", type=int, default=nxt.month)
    ap.add_argument("--cta", action="store_true", help="CTA 배지를 그림에 얹는다(기본: 끔, TTS로 대체)")
    ap.add_argument("--no-cta", action="store_true", help="(구버전 호환) 기본값과 동일")
    ap.add_argument("--prompt-only", action="store_true", help="생성 없이 프롬프트만 출력")
    a = ap.parse_args()

    if a.cta_only:
        apply_cta_all(a.year, a.month)
    elif a.prompt_only:
        for i, s in enumerate(month_set(a.year, a.month)["images"], 1):
            print(f"\n--- [{i}] {s['name']} ---\n{s['prompt'][:600]}")
    else:
        r = ensure_month_images(a.year, a.month, with_cta=a.cta and not a.no_cta)
        print("\n폴더:", r["dir"])
        for f in r["files"]:
            print("  ", Path(f).name)
