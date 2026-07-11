# -*- coding: utf-8 -*-
"""오행 5색 틴트 미리보기 — 커버 5장 + 오늘 실제 본문 1장 렌더 (_preview/, 커밋 제외)."""
import sys
import datetime as dt
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8")

from zodiac_cardnews import build_html, ELEM_THEME
from ganzhi_zodiac import day_context

BASE = Path(__file__).resolve().parent
out = BASE / "_preview"
out.mkdir(exist_ok=True)

today = dt.date.today().isoformat()
dc = day_context(dt.date.today())
print(f"오늘: {dc['label']} — 지지 오행 {dc['branch_elem']} (테마 자동={dc['branch_elem']})")

from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1200, "height": 1440}, device_scale_factor=1)
    # 5색 커버 미리보기
    for elem in ELEM_THEME:
        html = build_html(today, theme_elem=elem)
        hp = out / f"_page_{elem}.html"
        hp.write_text(html, encoding="utf-8")
        pg.goto(hp.as_uri(), wait_until="networkidle")
        pg.wait_for_timeout(700)
        pg.locator(".card").nth(0).screenshot(path=str(out / f"cover_{elem}.png"))
        print(f"  cover_{elem}.png ✓")
    # 오늘 실제 테마 본문 1장 (띠 문구·행운 확인용)
    html = build_html(today)
    hp = out / "_page_today.html"
    hp.write_text(html, encoding="utf-8")
    pg.goto(hp.as_uri(), wait_until="networkidle")
    pg.wait_for_timeout(700)
    pg.locator(".card").nth(1).screenshot(path=str(out / "body_today.png"))
    print("  body_today.png ✓")
    b.close()
print("완료:", out)
