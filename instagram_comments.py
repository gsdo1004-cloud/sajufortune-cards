# -*- coding: utf-8 -*-
"""Safe Instagram inbound comment replies for the 운명과학 account.

Official Instagram API with Instagram Login only (graph.instagram.com).
No browser automation, no outreach comments on other accounts, no links/sales CTA.
Default is dry-run; --send enables at most the configured cap.
"""
from __future__ import annotations

import argparse
import datetime as dt
import difflib
import json
import os
import re
from pathlib import Path
from typing import Any

import requests

BASE = Path(__file__).resolve().parent
STATE = BASE / "instagram_comments_state.json"
REPORT = BASE / "instagram_comments_report.md"
CONFIG = BASE / "instagram_comments_config.json"
API_VERSION = os.environ.get("INSTAGRAM_API_VERSION", "v21.0").strip() or "v21.0"
GRAPH = f"https://graph.instagram.com/{API_VERSION}"

DEFAULT_CONFIG = {
    "schema": 1,
    "account_username": "gsdo10042026",
    "recent_media_limit": 12,
    "max_comment_age_hours": 96,
    "daily_cap": 5,
    "per_run_cap": 1,
    "blocked_terms": [
        "http://", "https://", "www.", "프로필 링크", "구매", "결제", "상담 신청",
        "카톡", "텔레그램", "오픈채팅", "DM 주세요", "디엠 주세요"
    ],
    "skip_comment_terms": ["광고", "홍보", "맞팔", "선팔", "코인", "도박", "대출"],
}


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def cfg() -> dict[str, Any]:
    c = load_json(CONFIG, {})
    return {**DEFAULT_CONFIG, **(c if isinstance(c, dict) else {})}


def env() -> tuple[str, str]:
    uid = os.environ.get("INSTAGRAM_USER_ID", "").strip()
    tok = os.environ.get("INSTAGRAM_ACCESS_TOKEN", "").strip()
    if not uid or not tok:
        raise RuntimeError("INSTAGRAM_USER_ID / INSTAGRAM_ACCESS_TOKEN missing")
    return uid, tok


def api_get(path: str, params: dict[str, Any]) -> dict[str, Any]:
    r = requests.get(f"{GRAPH}/{path.lstrip('/')}", params=params, timeout=30)
    try:
        data = r.json()
    except Exception:
        raise RuntimeError(f"GET {path}: HTTP {r.status_code} non-json")
    if r.status_code >= 400 or data.get("error"):
        err = data.get("error") or {}
        raise RuntimeError(f"GET {path}: code={err.get('code')} {str(err.get('message') or data)[:250]}")
    return data


def api_post(path: str, data: dict[str, Any]) -> dict[str, Any]:
    r = requests.post(f"{GRAPH}/{path.lstrip('/')}", data=data, timeout=30)
    try:
        out = r.json()
    except Exception:
        raise RuntimeError(f"POST {path}: HTTP {r.status_code} non-json")
    if r.status_code >= 400 or out.get("error"):
        err = out.get("error") or {}
        raise RuntimeError(f"POST {path}: code={err.get('code')} {str(err.get('message') or out)[:250]}")
    return out


def parse_ts(s: str | None) -> dt.datetime | None:
    if not s:
        return None
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def recent_enough(ts: str | None, hours: int) -> bool:
    t = parse_ts(ts)
    if not t:
        return True
    if not t.tzinfo:
        t = t.replace(tzinfo=dt.timezone.utc)
    return (dt.datetime.now(dt.timezone.utc) - t.astimezone(dt.timezone.utc)).total_seconds() <= hours * 3600


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def safe_reply(comment: str, username: str) -> str:
    text = norm(comment)
    # Keep replies conversational and non-commercial. No fortune claims or diagnosis.
    if any(k in text for k in ["감사", "고마"]):
        return "댓글 남겨주셔서 감사합니다 😊 오늘도 편안한 하루 보내세요."
    if any(k in text for k in ["재물", "돈", "금전"]):
        return "재물운은 한 가지 신호보다 시기와 선택을 함께 보는 게 중요해요. 요즘 가장 궁금한 부분이 수입, 지출, 기회 중 어느 쪽인가요?"
    if any(k in text for k in ["궁합", "연애", "사랑"]):
        return "관계운은 상대와의 흐름을 같이 볼 때 해석이 더 풍부해져요. 요즘 가장 신경 쓰이는 부분이 소통인지, 시기인지 궁금합니다."
    if any(k in text for k in ["직장", "취업", "사업", "이직"]):
        return "일운은 변화 시점과 실제 선택지를 함께 보는 게 좋아요. 지금은 유지와 변화 중 어느 쪽을 더 고민하고 계신가요?"
    if "?" in comment or "？" in comment or any(k in text for k in ["어떻게", "언제", "왜", "뭔가", "궁금"]):
        return "좋은 질문이에요. 한 가지로 단정하기보다 지금 상황과 시기를 같이 보는 게 좋습니다. 어떤 부분이 가장 궁금하신가요?"
    return "의견 남겨주셔서 감사합니다 😊 이 주제에서 가장 궁금했던 부분이 무엇인지 한 말씀 더 남겨주셔도 좋아요."


def quality_ok(reply: str, c: dict[str, Any], history: list[str]) -> tuple[bool, str]:
    t = norm(reply)
    if not t or len(t) < 12 or len(t) > 220:
        return False, "length"
    for word in c.get("blocked_terms", []):
        if norm(word) in t:
            return False, f"blocked:{word}"
    for old in history[-30:]:
        if difflib.SequenceMatcher(None, t, norm(old)).ratio() >= 0.90:
            return False, "near_duplicate"
    return True, "ok"


def get_replies(comment_id: str, tok: str) -> list[dict[str, Any]]:
    try:
        return (api_get(f"{comment_id}/replies", {"fields": "id,text,username,timestamp", "limit": 50, "access_token": tok}).get("data") or [])
    except Exception:
        return []


def discover() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    uid, tok = env()
    c = cfg()
    profile = api_get(uid, {"fields": "id,username,account_type,media_count", "access_token": tok})
    username = str(profile.get("username") or c["account_username"]).lower()
    media = api_get(f"{uid}/media", {
        "fields": "id,caption,media_type,permalink,timestamp,comments_count",
        "limit": int(c["recent_media_limit"]), "access_token": tok,
    }).get("data") or []
    candidates: list[dict[str, Any]] = []
    state = load_json(STATE, {"replied_comment_ids": [], "reply_texts": [], "days": {}})
    done = set(str(x) for x in state.get("replied_comment_ids", []))
    for m in media:
        mid = str(m.get("id") or "")
        if not mid:
            continue
        try:
            comments = api_get(f"{mid}/comments", {
                "fields": "id,text,username,timestamp",
                "limit": 50, "access_token": tok,
            }).get("data") or []
        except Exception:
            continue
        for cm in comments:
            cid = str(cm.get("id") or "")
            author = str(cm.get("username") or "").lower()
            text = str(cm.get("text") or "").strip()
            if not cid or cid in done or author == username:
                continue
            if not recent_enough(cm.get("timestamp"), int(c["max_comment_age_hours"])):
                continue
            if any(norm(k) in norm(text) for k in c.get("skip_comment_terms", [])):
                continue
            replies = get_replies(cid, tok)
            if any(str(r.get("username") or "").lower() == username for r in replies):
                done.add(cid)
                continue
            candidates.append({
                "comment_id": cid, "media_id": mid, "username": author,
                "text": text, "timestamp": cm.get("timestamp"), "permalink": m.get("permalink"),
            })
    candidates.sort(key=lambda x: x.get("timestamp") or "", reverse=True)
    return profile, candidates


def run(send: bool = False) -> int:
    c = cfg()
    uid, tok = env()
    profile, candidates = discover()
    state = load_json(STATE, {"replied_comment_ids": [], "reply_texts": [], "days": {}})
    today = dt.datetime.now(dt.timezone.utc).astimezone(dt.timezone(dt.timedelta(hours=9))).date().isoformat()
    day = state.setdefault("days", {}).setdefault(today, {"sent": 0})
    sent = int(day.get("sent", 0))
    history = list(state.get("reply_texts", []))
    actions = []
    for item in candidates:
        if len(actions) >= int(c["per_run_cap"]) or sent >= int(c["daily_cap"]):
            break
        reply = safe_reply(item["text"], item["username"])
        ok, why = quality_ok(reply, c, history)
        if not ok:
            continue
        rec = {**item, "reply": reply, "mode": "send" if send else "dry_run"}
        if send:
            out = api_post(f"{item['comment_id']}/replies", {"message": reply, "access_token": tok})
            rid = str(out.get("id") or "")
            if not rid:
                raise RuntimeError("Instagram reply returned no id")
            # Verify the reply exists under the intended comment before recording success.
            replies = get_replies(item["comment_id"], tok)
            if not any(str(r.get("id") or "") == rid for r in replies):
                raise RuntimeError("Instagram reply verification failed")
            rec["reply_id"] = rid
            state.setdefault("replied_comment_ids", []).append(item["comment_id"])
            state.setdefault("reply_texts", []).append(reply)
            sent += 1
            day["sent"] = sent
            save_json(STATE, state)
        actions.append(rec)
    lines = [
        f"# Instagram 댓글 자동화 보고 — {today}", "",
        f"- 계정: `{profile.get('username','?')}`",
        f"- 모드: {'실전 발송' if send else '드라이런'}",
        f"- 후보: {len(candidates)}건",
        f"- 이번 처리: {len(actions)}건",
        f"- 오늘 발송: {sent}/{c['daily_cap']}", "",
    ]
    if actions:
        lines += ["## 후보/처리", ""]
        for a in actions:
            lines += [f"- @{a['username']}: {a['text'][:100]}", f"  - 답글: {a['reply']}"]
    else:
        lines += ["- 처리할 새 댓글이 없습니다."]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


def preflight() -> int:
    uid, tok = env()
    p = api_get(uid, {"fields": "id,username,account_type,media_count", "access_token": tok})
    media = api_get(f"{uid}/media", {"fields": "id", "limit": 1, "access_token": tok}).get("data") or []
    comments_ok = False
    detail = "no media"
    if media:
        try:
            api_get(f"{media[0]['id']}/comments", {"fields": "id,text,username,timestamp", "limit": 1, "access_token": tok})
            comments_ok = True
            detail = "comments read OK"
        except Exception as e:
            detail = str(e)[:300]
    out = {"username": p.get("username"), "basic": bool(p.get("id")), "comments_read": comments_ok, "detail": detail}
    save_json(BASE / "instagram_comments_capabilities.json", out)
    print(json.dumps(out, ensure_ascii=False))
    return 0 if comments_ok else 2


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--send", action="store_true")
    ap.add_argument("--preflight", action="store_true")
    args = ap.parse_args()
    raise SystemExit(preflight() if args.preflight else run(args.send))
