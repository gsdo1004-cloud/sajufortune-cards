# -*- coding: utf-8 -*-
"""
띠별운세 인스타그램 발행 (Instagram 로그인 API, graph.instagram.com)
====================================================================
- 카드뉴스 캐러셀 (이미지 6장) + 릴스 영상(9:16 mp4) 발행 + 첫 댓글 CTA
- 이미지/영상은 sajufortune-cards public raw URL 사용 (카드/릴스 스크립트가 먼저 생성·커밋)

모드: python zodiac_instagram.py carousel [YYYY-MM-DD]   # 카드 캐러셀
      python zodiac_instagram.py reel     [YYYY-MM-DD]   # 릴스 영상
환경변수(Actions secrets): INSTAGRAM_ACCESS_TOKEN, INSTAGRAM_USER_ID
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
IG = "https://graph.instagram.com/v21.0"
N_CARDS = 6   # 3띠 구성 = 표지1+본문4+요약1


def date_full(di):
    d = dt.date.fromisoformat(di)
    wd = ["월", "화", "수", "목", "금", "토", "일"][d.weekday()]
    return f"{d.year}년 {d.month}월 {d.day}일 {wd}요일"


def _env():
    return os.environ["INSTAGRAM_USER_ID"], os.environ["INSTAGRAM_ACCESS_TOKEN"]


def _post(url, data):
    import requests
    return requests.post(url, data=data, timeout=60).json()


def add_comment(media_id, text):
    uid, tok = _env()
    j = _post(f"{IG}/{media_id}/comments", {"message": text, "access_token": tok})
    print(f"[OK] IG comment: {j.get('id')}")


def publish_carousel(image_urls, caption):
    uid, tok = _env()
    children = []
    for u in image_urls:
        j = _post(f"{IG}/{uid}/media", {
            "image_url": u, "is_carousel_item": "true", "access_token": tok})
        cid = j.get("id")
        if not cid:
            raise SystemExit(f"[FAIL] IG item: {j}")
        children.append(cid)
        time.sleep(2)

    j = _post(f"{IG}/{uid}/media", {
        "media_type": "CAROUSEL", "children": ",".join(children),
        "caption": caption, "access_token": tok})
    carid = j.get("id")
    if not carid:
        raise SystemExit(f"[FAIL] IG carousel container: {j}")

    time.sleep(6)
    j = _post(f"{IG}/{uid}/media_publish", {"creation_id": carid, "access_token": tok})
    pid = j.get("id")
    if not pid:
        raise SystemExit(f"[FAIL] IG carousel publish: {j}")
    print(f"[OK] IG carousel published: {pid}")
    return pid


def publish_reel(video_url, caption):
    import requests
    uid, tok = _env()
    j = _post(f"{IG}/{uid}/media", {
        "media_type": "REELS", "video_url": video_url,
        "caption": caption, "access_token": tok})
    cid = j.get("id")
    if not cid:
        raise SystemExit(f"[FAIL] IG reel container: {j}")

    # 비디오 처리 대기 (status_code 폴링)
    for _ in range(40):
        time.sleep(6)
        st = requests.get(f"{IG}/{cid}",
                          params={"fields": "status_code", "access_token": tok},
                          timeout=30).json()
        sc = st.get("status_code")
        if sc == "FINISHED":
            break
        if sc == "ERROR":
            raise SystemExit(f"[FAIL] IG reel processing: {st}")

    j = _post(f"{IG}/{uid}/media_publish", {"creation_id": cid, "access_token": tok})
    pid = j.get("id")
    if not pid:
        raise SystemExit(f"[FAIL] IG reel publish: {j}")
    print(f"[OK] IG reel published: {pid}")
    return pid


def do_carousel(date_iso):
    urls = [f"{RAW_BASE}/cards/{date_iso}/card_{i:02d}.png" for i in range(1, N_CARDS + 1)]
    caption = (f"{date_full(date_iso)} 오늘의 띠별 운세 🔮\n"
               f"내 띠는 오늘 어떤 흐름일까요?\n\n"
               f"#오늘의운세 #띠별운세 #사주 #운세 #12띠 #데일리운세")
    pid = publish_carousel(urls, caption)
    add_comment(pid, "오늘 내 사주 점수는 몇 점일까요? 생년월일만 넣으면 무료 → "
                     f"https://{SITE}/unse/today?utm_source=instagram&utm_medium=carousel")


def do_reel(date_iso):
    url = f"{RAW_BASE}/reels/{date_iso}_tts.mp4"
    caption = (f"{date_full(date_iso)} 띠별 운세 영상 🔮\n"
               f"오늘 나의 흐름, 영상으로 확인하세요\n\n"
               f"#오늘의운세 #띠별운세 #릴스 #사주 #운세")
    pid = publish_reel(url, caption)
    add_comment(pid, "오늘 내 사주 점수는 몇 점일까요? 생년월일만 넣으면 무료 → "
                     f"https://{SITE}/unse/today?utm_source=instagram&utm_medium=reel")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "carousel"
    di = sys.argv[2] if len(sys.argv) > 2 else zs.today_iso()
    if mode == "carousel":
        do_carousel(di)
    elif mode == "reel":
        do_reel(di)
    else:
        raise SystemExit("사용법: python zodiac_instagram.py [carousel|reel] [YYYY-MM-DD]")
