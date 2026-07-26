# -*- coding: utf-8 -*-
"""내 스레드 글에 달린 댓글에 답글 달기 — **반자동** (2026-07-27 신설).

왜 반자동인가
-------------
인스타 계정이 **자동 댓글로 이미 제재**를 받았다(링크 자동댓글 대량 살포).
스레드에서 같은 실수를 하면 이 계정도 잃는다. 그래서 기본값은 초안 출력이고,
`--send` 를 명시해야만 실제로 나간다. 하루 상한도 둔다.

권한
----
Threads 문서: "스레드에 답글을 달려면 **루트 게시물의 소유자**이거나
threads_keyword_search / threads_manage_mentions 권한을 보유해야 한다."
→ **내 글에 달린 댓글은 내가 소유자라 추가 권한이 필요 없다.** 지금 토큰으로 된다.
(남의 글에 답글을 다는 것은 별개 — 그건 keyword_search 승인이 필요하고, 하지 않는다.)

실행:
  python threads_replies.py                 # 초안만 출력(기본)
  python threads_replies.py --send          # 실제 발송
  python threads_replies.py --limit 5
환경변수: THREADS_ACCESS_TOKEN, THREADS_USER_ID, (GEMINI_API_KEY / _PAID)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import time
from pathlib import Path

import requests

import llm_fallback as llm

BASE = Path(__file__).resolve().parent
STATE = BASE / "threads_replied.json"
GRAPH = "https://graph.threads.net/v1.0"

DAILY_CAP = 10          # 하루 상한. 이걸 넘기면 자동화 신호가 커진다
LOOKBACK_POSTS = 8      # 최근 글 몇 개까지 훑을지

# 답하지 않는 댓글 — 정치·종교·비방·광고는 건드리지 않는다. 잘못 답하면 계정이 다친다.
SKIP_WORDS = ["정치", "대통령", "좌파", "우파", "종교", "교회", "절에", "목사", "스님",
              "사기", "환불", "고소", "신고", "광고", "홍보", "디엠", "DM", "http"]

PROMPT = """스레드(SNS)에서 내 글에 달린 댓글에 답글을 단다. 자연스러운 답글 한 줄을 써라.

내 글: {post}
받은 댓글: {comment}

규칙:
- **반말.** 존댓말("~습니다", "~세요") 쓰지 마라. 친근하게 툭 던지듯.
- 한 문장, 길어도 두 문장. 길면 영업 티가 난다.
- 댓글 내용에 실제로 반응해라. "감사합니다" 같은 복사붙여넣기 답변 금지.
- 운세를 단정하지 마라("무조건 잘 된다" 금지). 그날 흐름 정도로만.
- 링크·해시태그·이모지 남발 금지. 이모지는 써도 하나까지.
- 사주를 팔려고 들지 마라. 궁금해하면 프로필 얘기만 한 번 꺼낼 수 있다.
- 결과 문장만 출력한다."""


def log(m: str):
    print(f"[replies] {m}", flush=True)


def _env():
    import os
    return os.environ["THREADS_USER_ID"], os.environ["THREADS_ACCESS_TOKEN"]


def _done() -> set:
    try:
        return set(json.loads(STATE.read_text(encoding="utf-8"))["ids"])
    except Exception:
        return set()


def _mark(reply_id: str, text: str):
    d = {"ids": [], "log": []}
    try:
        d = json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        pass
    d.setdefault("ids", []).append(reply_id)
    d.setdefault("log", []).append(
        {"at": dt.datetime.now().isoformat(timespec="seconds"),
         "reply_to": reply_id, "text": text})
    d["ids"] = d["ids"][-500:]
    d["log"] = d["log"][-150:]
    STATE.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def my_posts(uid: str, tok: str) -> list[dict]:
    r = requests.get(f"{GRAPH}/{uid}/threads", timeout=30, params={
        "fields": "id,text,timestamp", "limit": LOOKBACK_POSTS,
        "access_token": tok})
    return r.json().get("data", [])


def replies_of(media_id: str, tok: str) -> list[dict]:
    r = requests.get(f"{GRAPH}/{media_id}/replies", timeout=30, params={
        "fields": "id,text,username,timestamp,is_reply_owned_by_me",
        "access_token": tok})
    j = r.json()
    if "error" in j:
        log(f"[WARN] 댓글 조회 실패({media_id}): "
            f"{str(j['error'].get('message'))[:80]}")
        return []
    return j.get("data", [])


def draft(post_text: str, comment: str) -> str | None:
    t = llm.ask(PROMPT.format(post=post_text[:180], comment=comment[:180]),
                max_tokens=300, temperature=0.9)
    if not t:
        return None
    t = re.sub(r"[#*`]", "", t).strip().strip('"')
    # 로컬 폴백(qwen2.5)은 한자가 샌다 — 그대로 나가면 자동 생성물 티가 크게 난다
    if re.search(r"[一-鿿぀-ヿ]", t) or len(t) > 120:
        log("[GATE] 답글 초안 폐기(외국 문자 또는 과다 길이)")
        return None
    return t


def send_reply(uid: str, tok: str, reply_to_id: str, text: str) -> str:
    j = requests.post(f"{GRAPH}/{uid}/threads", timeout=30, data={
        "media_type": "TEXT", "text": text,
        "reply_to_id": reply_to_id, "access_token": tok}).json()
    cid = j.get("id")
    if not cid:
        raise SystemExit(f"[FAIL] reply container: {j}")
    time.sleep(3)
    j = requests.post(f"{GRAPH}/{uid}/threads_publish", timeout=30, data={
        "creation_id": cid, "access_token": tok}).json()
    pid = j.get("id")
    if not pid:
        raise SystemExit(f"[FAIL] reply publish: {j}")
    return pid


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--send", action="store_true", help="실제 발송(기본은 초안만)")
    ap.add_argument("--limit", type=int, default=DAILY_CAP)
    a = ap.parse_args()

    uid, tok = _env()
    done = _done()
    posts = my_posts(uid, tok)
    log(f"최근 글 {len(posts)}개 확인")

    n = 0
    for p in posts:
        if n >= a.limit:
            break
        for c in replies_of(p["id"], tok):
            if n >= a.limit:
                break
            rid, ctext = c.get("id"), (c.get("text") or "").strip()
            if not rid or not ctext or rid in done:
                continue
            if c.get("is_reply_owned_by_me"):
                continue                      # 내가 쓴 답글에 또 답하지 않는다
            if any(w in ctext for w in SKIP_WORDS):
                log(f"[SKIP] 민감/광고 댓글 — 건드리지 않음: {ctext[:24]}")
                continue
            d = draft(p.get("text", ""), ctext)
            if not d:
                continue
            print("-" * 52)
            print(f"@{c.get('username','?')}: {ctext[:70]}")
            print(f"  → {d}")
            if a.send:
                pid = send_reply(uid, tok, rid, d)
                _mark(rid, d)
                log(f"발송: {pid}")
                time.sleep(8)
            n += 1
    print("-" * 52)
    if not a.send:
        log(f"[초안] {n}건 — 발송하지 않았습니다. 실제로 보내려면 --send")
    else:
        log(f"발송 완료 {n}건 (상한 {a.limit})")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
