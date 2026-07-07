# -*- coding: utf-8 -*-
"""
띠별운세 카드뉴스 자동생성 + 스레드 캐러셀 발행 (GitHub Actions 통합)
====================================================================
- 데이터: zodiac_seo.py (sajufortune.kr /zodiac 와 100% 동일한 결정론적 운세)
- 생성: HTML → Playwright(Chromium + Noto Color Emoji) → PNG 8장
- 호스팅: 이 public repo의 cards/{날짜}/ 커밋 → raw.githubusercontent.com URL
- 발행: Threads 캐러셀 (item x8 → CAROUSEL → publish) + 첫 댓글 CTA
- 디자인: 흰바탕 + 은은한 핑크 테두리 + 형광펜 + 띠 이모지 (design_saju.md 확정)

모드:
  python zodiac_cardnews.py generate   # PNG 8장 생성 → cards/{KST날짜}/
  python zodiac_cardnews.py publish     # (커밋 후) raw URL로 캐러셀 발행

환경변수(Actions secrets): THREADS_ACCESS_TOKEN, THREADS_USER_ID
"""
import os
import sys
import time
import datetime as dt
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import zodiac_seo as zs

GH_USER = "gsdo1004-cloud"
GH_REPO = "sajufortune-cards"
RAW_BASE = f"https://raw.githubusercontent.com/{GH_USER}/{GH_REPO}/main"
SITE = "sajufortune.kr"

ORDER = ["rat", "ox", "tiger", "rabbit", "dragon", "snake",
         "horse", "goat", "monkey", "rooster", "dog", "pig"]


def date_full(date_iso):
    d = dt.date.fromisoformat(date_iso)
    wd = ["월", "화", "수", "목", "금", "토", "일"][d.weekday()]
    return f"{d.year}년 {d.month}월 {d.day}일 ({wd})"


def stars(n):
    return f'<b>{"★" * n}</b>{"☆" * (5 - n)}'


CSS = """
* { margin:0; padding:0; box-sizing:border-box; }
body { background:#e9e9ee; display:flex; flex-direction:column; gap:0;
  margin:0; font-family:'Pretendard','Noto Color Emoji',-apple-system,sans-serif; }
.card { width:1080px; height:1350px; background:#FBE4EE; padding:40px; }
.sheet { width:100%; height:100%; background:#fff; border-radius:30px;
  padding:80px 74px; position:relative; display:flex; flex-direction:column; }
.tag { align-self:center; font-weight:800; font-size:38px; letter-spacing:-0.02em;
  padding:12px 40px; border-radius:40px; background:#E84B8A; color:#fff; }
.mark { background:linear-gradient(transparent 56%,#FBC0DA 56%); padding:0 6px; }
.brand { margin-top:auto; text-align:center; font-size:34px; font-weight:800;
  color:#c98ab0; letter-spacing:0.02em; }
.cv-title { text-align:center; margin-top:56px; font-weight:900; font-size:128px;
  letter-spacing:-0.03em; color:#26262e; line-height:1.1; }
.cv-sub { text-align:center; margin-top:24px; font-size:44px; font-weight:600; color:#8a8a94; }
.zodiac-grid { margin-top:auto; margin-bottom:16px; display:grid;
  grid-template-columns:repeat(6,1fr); gap:22px 8px; }
.zodiac-grid div { text-align:center; font-size:80px; line-height:1; }
.sec { font-weight:800; font-size:40px; color:#E84B8A; margin-bottom:48px; letter-spacing:-0.02em; }
.block { display:flex; align-items:flex-start; gap:40px; margin-bottom:40px; }
.icon { flex:0 0 148px; width:148px; height:148px; border-radius:50%; background:#FDEFF5;
  display:flex; align-items:center; justify-content:center; font-size:90px; line-height:1; }
.bd { flex:1; padding-top:4px; }
.nm { font-weight:900; font-size:52px; color:#26262e; letter-spacing:-0.02em;
  display:flex; align-items:center; gap:18px; margin-bottom:14px; }
.stars { color:#F4A6C6; font-size:38px; letter-spacing:2px; }
.stars b { color:#E84B8A; }
.run { font-size:35px; line-height:1.5; color:#5f5f68; font-weight:500; }
.luck { margin-top:16px; font-size:29px; font-weight:700; color:#b8568f;
  background:#FDEFF5; display:inline-block; padding:9px 24px; border-radius:22px; }
.toplist { margin-top:80px; display:flex; flex-direction:column; gap:46px; }
.top { display:flex; align-items:center; gap:34px; font-size:64px; font-weight:900; color:#26262e; }
.top .em { font-size:96px; }
.top .st { margin-left:auto; font-size:48px; color:#F4A6C6; }
.top .st b { color:#E84B8A; }
.cta { margin-top:76px; text-align:center; font-size:52px; font-weight:800; color:#E84B8A; line-height:1.4; }
"""


def build_html(date_iso):
    R = {s: zs.make_reading(s, date_iso) for s in ORDER}
    df = date_full(date_iso)

    # 총운 문구: 카드 한 세트(12띠) 안에서 겹치지 않게 유니크 재배정 (결정론 유지)
    _pool = zs.OVERALL_POOL
    _used = set()
    OA = {}
    for _s in ORDER:
        _i = zs._seed(_s, date_iso) % len(_pool)
        while _i in _used:
            _i = (_i + 1) % len(_pool)
        _used.add(_i)
        OA[_s] = _pool[_i]

    em = "".join(f"<div>{R[s].emoji}</div>" for s in ORDER)
    cover = (f'<div class="card"><div class="sheet">'
             f'<div class="tag">{df}</div>'
             f'<div class="cv-title"><span class="mark">띠별</span> 운세</div>'
             f'<div class="cv-sub">오늘, 나의 흐름은?</div>'
             f'<div class="zodiac-grid">{em}</div>'
             f'<div class="brand">{SITE}</div></div></div>')

    groups = [ORDER[i:i + 3] for i in range(0, 12, 3)]   # 한 장에 3띠 (총 6장)
    total = len(groups) + 2   # 표지 + 본문 + 요약
    bodies = ""
    for idx, grp in enumerate(groups):
        blocks = ""
        for s in grp:
            r = R[s]
            # 행운 정보 파싱 (tip 예: "오늘의 행운 색: 푸른색 / 행운 방향: 동쪽")
            _t = r.tip.replace("오늘의 ", "").split(" / ")
            _color = _t[0].split(":")[-1].strip() if _t else ""
            _dir = _t[1].split(":")[-1].strip() if len(_t) > 1 else ""
            luck = f"🎲 행운수 {r.lucky_num} · 🎨 {_color} · 🧭 {_dir}"
            blocks += (f'<div class="block"><div class="icon">{r.emoji}</div>'
                       f'<div class="bd"><div class="nm">{r.sign_ko} '
                       f'<span class="stars">{stars(r.overall_score)}</span></div>'
                       f'<div class="run">{OA[s]}</div>'
                       f'<div class="luck">{luck}</div></div></div>')
        sec = " · ".join(R[s].sign_ko for s in grp)
        bodies += (f'<div class="card"><div class="sheet">'
                   f'<div class="sec">오늘의 흐름 · {sec}</div>{blocks}'
                   f'<div class="brand">{SITE} · {idx + 2} / {total}</div></div></div>')

    top = sorted(ORDER, key=lambda s: R[s].overall_score, reverse=True)[:3]
    items = "".join(
        f'<div class="top"><span class="em">{R[s].emoji}</span> {R[s].sign_ko}'
        f'<span class="st">{stars(R[s].overall_score)}</span></div>' for s in top)
    summary = (f'<div class="card"><div class="sheet">'
               f'<div class="cv-title" style="font-size:98px;margin-top:40px">오늘 웃는 띠<br>'
               f'<span class="mark">TOP 3</span></div>'
               f'<div class="toplist">{items}</div>'
               f'<div class="cta">내 사주 흐름 자세히 보기<br>{SITE}</div>'
               f'<div class="brand">{df}</div></div></div>')

    return ('<!doctype html><html lang="ko"><head><meta charset="utf-8">'
            '<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.css">'
            f'<style>{CSS}</style></head><body>{cover}{bodies}{summary}</body></html>')


def render_pngs(date_iso, outdir):
    from playwright.sync_api import sync_playwright
    html = build_html(date_iso)
    hp = outdir / "_page.html"
    hp.write_text(html, encoding="utf-8")
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1200, "height": 1440}, device_scale_factor=1)
        pg.goto(hp.as_uri(), wait_until="networkidle")
        pg.wait_for_timeout(900)  # 폰트/이모지 로드
        cards = pg.locator(".card")
        n = cards.count()
        for i in range(n):
            cards.nth(i).screenshot(path=str(outdir / f"card_{i + 1:02d}.png"))
        b.close()
    hp.unlink()
    return n


# ── Threads 캐러셀 발행 ──
def _post(url, data):
    import requests
    return requests.post(url, data=data, timeout=30).json()


def publish_carousel(image_urls, caption):
    tok = os.environ["THREADS_ACCESS_TOKEN"]
    uid = os.environ["THREADS_USER_ID"]
    base = f"https://graph.threads.net/v1.0/{uid}"

    children = []
    for u in image_urls:
        j = _post(f"{base}/threads", {
            "media_type": "IMAGE", "image_url": u,
            "is_carousel_item": "true", "access_token": tok})
        cid = j.get("id")
        if not cid:
            raise SystemExit(f"[FAIL] item container: {j}")
        children.append(cid)
        time.sleep(2)

    j = _post(f"{base}/threads", {
        "media_type": "CAROUSEL", "children": ",".join(children),
        "text": caption, "access_token": tok})
    carousel_id = j.get("id")
    if not carousel_id:
        raise SystemExit(f"[FAIL] carousel container: {j}")

    time.sleep(6)  # 처리 대기
    j = _post(f"{base}/threads_publish", {"creation_id": carousel_id, "access_token": tok})
    pid = j.get("id")
    if not pid:
        raise SystemExit(f"[FAIL] publish: {j}")
    print(f"[OK] published carousel: {pid}")
    return pid


def publish_reply(post_id, text):
    tok = os.environ["THREADS_ACCESS_TOKEN"]
    uid = os.environ["THREADS_USER_ID"]
    base = f"https://graph.threads.net/v1.0/{uid}"
    j = _post(f"{base}/threads", {
        "media_type": "TEXT", "text": text,
        "reply_to_id": post_id, "access_token": tok})
    cid = j.get("id")
    if not cid:
        print(f"[WARN] reply container: {j}")
        return
    time.sleep(3)
    j = _post(f"{base}/threads_publish", {"creation_id": cid, "access_token": tok})
    print(f"[OK] reply: {j.get('id')}")


def do_generate():
    date_iso = zs.today_iso()
    outdir = Path(__file__).resolve().parent / "cards" / date_iso
    outdir.mkdir(parents=True, exist_ok=True)
    n = render_pngs(date_iso, outdir)
    print(f"[OK] generated {n} cards → {outdir}  ({date_full(date_iso)})")


def do_publish():
    date_iso = zs.today_iso()
    urls = [f"{RAW_BASE}/cards/{date_iso}/card_{i:02d}.png" for i in range(1, 9)]
    caption = (f"{date_full(date_iso)} 오늘의 띠별 운세 🔮\n"
               f"내 띠는 오늘 어떤 흐름일까요?\n\n"
               f"#오늘의운세 #띠별운세 #사주 #운세 #12띠")
    pid = publish_carousel(urls, caption)
    publish_reply(pid, f"내 띠 운세 자세히 보기 →\nhttps://{SITE}/zodiac")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "generate"
    if mode == "generate":
        do_generate()
    elif mode == "publish":
        do_publish()
    else:
        raise SystemExit("사용법: python zodiac_cardnews.py [generate|publish]")
