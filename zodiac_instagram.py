# -*- coding: utf-8 -*-
"""Instagram 자동 발행 — 오늘운세/사주형 릴스·캐러셀.

공개 미디어는 sajufortune-cards raw URL을 사용한다. 게시물에는 URL을 반복 삽입하지
않고 프로필 첫 링크로만 유도한다. 과거 링크 자동댓글 제한 이력이 있어 자동 댓글은
기본 OFF이며, 날짜+콘텐츠 종류별 마커로 백업 cron 중복 게시를 막는다.

사용:
  python zodiac_instagram.py preflight
  python zodiac_instagram.py status [YYYY-MM-DD]
  python zodiac_instagram.py carousel [YYYY-MM-DD]
  python zodiac_instagram.py reel [YYYY-MM-DD]
  python zodiac_instagram.py signal [YYYY-MM-DD]
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import zodiac_seo as zs

BASE = Path(__file__).resolve().parent
GH_USER = "gsdo1004-cloud"
GH_REPO = "sajufortune-cards"
RAW_BASE = f"https://raw.githubusercontent.com/{GH_USER}/{GH_REPO}/main"
PROFILE_LANDING = (
    "https://sajufortune.kr/links?utm_source=instagram&utm_medium=profile&"
    "utm_campaign=instagram_reels_revenue"
)
IG_API_VERSION = os.environ.get("INSTAGRAM_API_VERSION", "v21.0").strip() or "v21.0"
IG = f"https://graph.instagram.com/{IG_API_VERSION}"
N_CARDS = 4
IG_RESUME_DATE = dt.date(2026, 8, 15)
CTA_COMMENT = "내 오늘운세는 프로필 첫 링크에서 무료로 확인하실 수 있어요 🔮"
AUTO_COMMENT = os.environ.get("INSTAGRAM_AUTO_COMMENT", "0").strip().lower() in {"1", "true", "yes", "on"}


def date_full(di: str) -> str:
    d = dt.date.fromisoformat(di)
    wd = ["월", "화", "수", "목", "금", "토", "일"][d.weekday()]
    return f"{d.year}년 {d.month}월 {d.day}일 {wd}요일"


def target_date() -> str:
    base = dt.date.fromisoformat(zs.today_iso())
    try:
        offset = int(os.environ.get("ZODIAC_PUBLISH_OFFSET_DAYS", "0"))
    except ValueError:
        offset = 0
    return (base + dt.timedelta(days=offset)).isoformat()


def _env() -> tuple[str, str]:
    uid = os.environ.get("INSTAGRAM_USER_ID", "").strip()
    tok = os.environ.get("INSTAGRAM_ACCESS_TOKEN", "").strip()
    if not uid or not tok:
        raise RuntimeError("INSTAGRAM_USER_ID / INSTAGRAM_ACCESS_TOKEN missing")
    return uid, tok


def _post(url: str, data: dict) -> dict:
    r = requests.post(url, data=data, timeout=60)
    try:
        return r.json()
    except Exception:
        return {"error": {"message": f"HTTP {r.status_code}: non-json response"}}


def _marker(date_iso: str, kind: str) -> Path:
    return BASE / "cards" / date_iso / f"instagram_pub_{kind}.json"


def _write_marker(date_iso: str, kind: str, post_id: str, *, media_url: str = "") -> None:
    p = _marker(date_iso, kind)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "date": date_iso,
        "kind": kind,
        "post_id": post_id,
        "published_at": dt.datetime.now().isoformat(timespec="seconds"),
        "media_url": media_url,
        "profile_campaign": "instagram_reels_revenue",
    }, ensure_ascii=False, indent=2), encoding="utf-8")


def preflight() -> bool:
    uid, tok = _env()
    r = requests.get(
        f"{IG}/{uid}",
        params={"fields": "id,username,account_type,media_count", "access_token": tok},
        timeout=30,
    )
    data = r.json() if r.content else {}
    if r.status_code >= 400 or not data.get("id"):
        msg = str((data.get("error") or {}).get("message") or f"HTTP {r.status_code}")
        raise RuntimeError(f"Instagram token preflight failed: {msg[:300]}")
    print(f"[OK] Instagram preflight: account={data.get('username','?')} media_count={data.get('media_count','?')}")
    return True


def add_comment(media_id: str, text: str) -> None:
    if not AUTO_COMMENT:
        print("[SAFE] Instagram auto comment OFF")
        return
    _, tok = _env()
    j = _post(f"{IG}/{media_id}/comments", {"message": text, "access_token": tok})
    if not j.get("id"):
        print(f"[WARN] IG comment skipped/failed: {j}")
        return
    print(f"[OK] IG comment: {j.get('id')}")


def publish_carousel(image_urls: list[str], caption: str) -> str:
    uid, tok = _env()
    children: list[str] = []
    for u in image_urls:
        j = _post(f"{IG}/{uid}/media", {
            "image_url": u, "is_carousel_item": "true", "access_token": tok,
        })
        cid = j.get("id")
        if not cid:
            raise RuntimeError(f"IG item create failed: {j}")
        children.append(cid)
        time.sleep(2)
    j = _post(f"{IG}/{uid}/media", {
        "media_type": "CAROUSEL", "children": ",".join(children),
        "caption": caption, "access_token": tok,
    })
    carid = j.get("id")
    if not carid:
        raise RuntimeError(f"IG carousel container failed: {j}")
    time.sleep(6)
    j = _post(f"{IG}/{uid}/media_publish", {"creation_id": carid, "access_token": tok})
    pid = j.get("id")
    if not pid:
        raise RuntimeError(f"IG carousel publish failed: {j}")
    print(f"[OK] IG carousel published: {pid}")
    return str(pid)


def publish_reel(video_url: str, caption: str) -> str:
    uid, tok = _env()
    j = _post(f"{IG}/{uid}/media", {
        "media_type": "REELS", "video_url": video_url,
        "caption": caption, "access_token": tok,
    })
    cid = j.get("id")
    if not cid:
        raise RuntimeError(f"IG reel container failed: {j}")
    finished = False
    for _ in range(40):
        time.sleep(6)
        st = requests.get(
            f"{IG}/{cid}", params={"fields": "status_code", "access_token": tok}, timeout=30
        ).json()
        sc = st.get("status_code")
        if sc == "FINISHED":
            finished = True
            break
        if sc == "ERROR":
            raise RuntimeError(f"IG reel processing failed: {st}")
    if not finished:
        raise RuntimeError("IG reel processing timed out before FINISHED")
    j = _post(f"{IG}/{uid}/media_publish", {"creation_id": cid, "access_token": tok})
    pid = j.get("id")
    if not pid:
        raise RuntimeError(f"IG reel publish failed: {j}")
    print(f"[OK] IG reel published: {pid}")
    return str(pid)


def _skip_if_done(date_iso: str, kind: str) -> bool:
    p = _marker(date_iso, kind)
    if not p.exists():
        return False
    try:
        post_id = json.loads(p.read_text(encoding="utf-8")).get("post_id", "?")
    except Exception:
        post_id = "?"
    print(f"[SKIP] Instagram {kind} already published: {date_iso} -> {post_id}")
    return True


def do_carousel(date_iso: str) -> None:
    if _skip_if_done(date_iso, "carousel"):
        return
    local = sorted((BASE / "cards" / date_iso).glob("card_*.png"))
    n = len(local) if local else N_CARDS
    urls = [f"{RAW_BASE}/cards/{date_iso}/card_{i:02d}.png" for i in range(1, n + 1)]
    caption = (
        f"{date_full(date_iso)} 오늘의 띠별 운세 🔮\n"
        "내 띠의 흐름을 먼저 보고, 내 생년월일 기준 오늘운세는 프로필 첫 링크에서 무료로 확인하세요.\n\n"
        "#오늘의운세 #띠별운세 #사주 #운세 #12띠 #데일리운세"
    )
    pid = publish_carousel(urls, caption)
    _write_marker(date_iso, "carousel", pid)
    add_comment(pid, CTA_COMMENT)


def do_reel(date_iso: str) -> None:
    if _skip_if_done(date_iso, "reel"):
        return
    url = f"{RAW_BASE}/reels/{date_iso}_tts.mp4"
    caption = (
        f"{date_full(date_iso)} 오늘의 띠별 운세 🔮\n"
        "영상은 12띠의 공통 흐름입니다. 내 생년월일 기준 오늘운세는 프로필 첫 링크에서 무료로 확인하세요.\n\n"
        "#오늘의운세 #띠별운세 #릴스 #사주 #운세 #무료운세"
    )
    pid = publish_reel(url, caption)
    _write_marker(date_iso, "reel", pid, media_url=url)
    add_comment(pid, CTA_COMMENT)


def do_signal_reel(date_iso: str) -> None:
    if _skip_if_done(date_iso, "signal"):
        return
    url = f"{RAW_BASE}/reels/{date_iso}_signal.mp4"
    caption = (
        f"{date_full(date_iso)} 오늘 눈여겨볼 띠 한 가지 🔮\n"
        "짧은 영상은 공통 신호만 보여드립니다. 내 사주 기준 흐름은 프로필 첫 링크의 무료 오늘운세에서 확인하세요.\n\n"
        "#사주 #띠별운세 #오늘의운세 #릴스 #운세 #명리"
    )
    pid = publish_reel(url, caption)
    _write_marker(date_iso, "signal", pid, media_url=url)
    add_comment(pid, CTA_COMMENT)


def status(date_iso: str) -> None:
    print(json.dumps({
        "date": date_iso,
        "credentials_present": bool(os.environ.get("INSTAGRAM_USER_ID") and os.environ.get("INSTAGRAM_ACCESS_TOKEN")),
        "auto_comment": AUTO_COMMENT,
        "profile_landing": PROFILE_LANDING,
        "markers": {k: _marker(date_iso, k).exists() for k in ("carousel", "reel", "signal")},
    }, ensure_ascii=False, indent=2))


def main() -> int:
    today = dt.date.fromisoformat(zs.today_iso())
    mode = sys.argv[1] if len(sys.argv) > 1 else "status"
    di = sys.argv[2] if len(sys.argv) > 2 else target_date()
    if mode == "status":
        status(di); return 0
    if mode == "preflight":
        preflight(); return 0
    if today < IG_RESUME_DATE:
        print(f"[SKIP] Instagram resume gate until {IG_RESUME_DATE}")
        return 0
    if mode == "carousel": do_carousel(di)
    elif mode == "reel": do_reel(di)
    elif mode == "signal": do_signal_reel(di)
    else: raise SystemExit("usage: zodiac_instagram.py [preflight|status|carousel|reel|signal] [YYYY-MM-DD]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
