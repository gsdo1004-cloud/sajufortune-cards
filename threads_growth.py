# -*- coding: utf-8 -*-
"""Threads 대화 성장 자동화 — 공식 Threads API 전용 안전모드.

목표
----
1) 큰 사주/명리 계정의 최근 글에 저빈도·비홍보성 댓글로 실제 대화에 참여한다.
2) 내 글에 달린 댓글과 대댓글에는 맥락에 맞는 답글을 빠르게 이어간다.
3) 모든 발송은 /me/replies 의 replied_to.id 로 목적지를 사후 검증한다.
4) 목적지 불일치, 권한/보안 오류, 반복문구 등 위험신호가 나오면 즉시 발송을 정지한다.

금지
----
- 브라우저 스크래핑/자동 클릭 폴백 없음.
- 링크/사이트/상담 홍보 댓글 자동발송 없음.
- 동일문구 복붙 없음.
- 공식 API 권한이 없으면 해당 기능은 조용히 건너뛴다.

환경변수: THREADS_ACCESS_TOKEN, THREADS_USER_ID, GEMINI_API_KEY(/_PAID)
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import difflib
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

try:
    import llm_fallback as llm
except Exception:
    llm = None

BASE = Path(__file__).resolve().parent
GRAPH = os.environ.get("THREADS_GRAPH", "https://graph.threads.net/v1.0").rstrip("/")
CONFIG_PATH = BASE / "threads_growth_config.json"
STATE_PATH = BASE / "threads_growth_state.json"
REPORT_PATH = BASE / "threads_growth_report.md"
CAP_PATH = BASE / "threads_growth_capabilities.json"
PAUSE_PATH = BASE / "threads_growth_PAUSED.json"

THREAD_FIELDS = "id,text,timestamp,username,permalink,is_reply,has_replies"
REPLY_FIELDS = (
    "id,text,timestamp,username,permalink,is_reply,is_reply_owned_by_me,"
    "root_post,replied_to,hide_status,has_replies"
)

URL_RE = re.compile(r"(?:https?://|www\.)", re.I)
MENTION_RE = re.compile(r"@[A-Za-z0-9._]+")
HASHTAG_RE = re.compile(r"#[^\s#]+")
MULTISPACE_RE = re.compile(r"\s+")
KOREAN_OR_ALNUM_RE = re.compile(r"[가-힣A-Za-z0-9]")


class APIError(RuntimeError):
    def __init__(self, message: str, *, code: int | None = None, subcode: int | None = None,
                 status: int | None = None):
        super().__init__(message)
        self.code = code
        self.subcode = subcode
        self.status = status


class LocationMismatch(RuntimeError):
    pass


def log(msg: str) -> None:
    print(f"[threads-growth] {msg}", flush=True)


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def date_key(now: dt.datetime | None = None) -> str:
    # KST 기준 일일 상한
    now = now or utcnow()
    return (now + dt.timedelta(hours=9)).date().isoformat()


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, data: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def load_config() -> dict[str, Any]:
    cfg = load_json(CONFIG_PATH, {})
    if not cfg:
        raise SystemExit(f"[FAIL] config missing: {CONFIG_PATH}")
    return cfg


def default_state() -> dict[str, Any]:
    return {
        "schema": 1,
        "handled_inbound_ids": [],
        "external_target_ids": [],
        "sent": [],
        "days": {},
        "last_run_at": None,
    }


def load_state() -> dict[str, Any]:
    s = load_json(STATE_PATH, default_state())
    for k, v in default_state().items():
        s.setdefault(k, v)
    return s


def trim_state(s: dict[str, Any]) -> None:
    s["handled_inbound_ids"] = s.get("handled_inbound_ids", [])[-2000:]
    s["external_target_ids"] = s.get("external_target_ids", [])[-2000:]
    s["sent"] = s.get("sent", [])[-1500:]
    # 최근 45일만 유지
    keys = sorted((s.get("days") or {}).keys())
    for k in keys[:-45]:
        s["days"].pop(k, None)


def today_bucket(state: dict[str, Any], now: dt.datetime | None = None) -> dict[str, Any]:
    k = date_key(now)
    days = state.setdefault("days", {})
    return days.setdefault(k, {"external": 0, "inbound": 0, "nested": 0,
                               "total": 0, "per_target": {}})


def text_hash(text: str) -> str:
    norm = MULTISPACE_RE.sub(" ", text.strip().lower())
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:20]


def parse_ts(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00").replace("+0000", "+00:00"))
    except Exception:
        return None


def age_hours(ts: str | None, now: dt.datetime | None = None) -> float:
    t = parse_ts(ts)
    if not t:
        return 999999.0
    now = now or utcnow()
    if t.tzinfo is None:
        t = t.replace(tzinfo=dt.timezone.utc)
    return max(0.0, (now - t.astimezone(dt.timezone.utc)).total_seconds() / 3600)


def safe_error_payload(j: Any) -> str:
    if isinstance(j, dict) and isinstance(j.get("error"), dict):
        e = j["error"]
        return f"{e.get('type','API')} code={e.get('code')} subcode={e.get('error_subcode')}: {str(e.get('message',''))[:220]}"
    return str(j)[:260]


class ThreadsAPI:
    def __init__(self, token: str):
        self.token = token
        self.session = requests.Session()

    def _json(self, r: requests.Response) -> dict[str, Any]:
        try:
            j = r.json()
        except Exception:
            raise APIError(f"HTTP {r.status_code}: non-json response", status=r.status_code)
        if r.status_code >= 400 or "error" in j:
            e = j.get("error") or {}
            raise APIError(safe_error_payload(j), code=e.get("code"),
                           subcode=e.get("error_subcode"), status=r.status_code)
        return j

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        p = dict(params or {})
        p["access_token"] = self.token
        r = self.session.get(f"{GRAPH}/{path.lstrip('/')}", params=p, timeout=30)
        return self._json(r)

    def post(self, path: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        p = dict(data or {})
        p["access_token"] = self.token
        r = self.session.post(f"{GRAPH}/{path.lstrip('/')}", data=p, timeout=30)
        return self._json(r)

    def delete(self, path: str) -> dict[str, Any]:
        r = self.session.delete(f"{GRAPH}/{path.lstrip('/')}", params={"access_token": self.token}, timeout=30)
        return self._json(r)


@dataclass
class Candidate:
    id: str
    username: str
    text: str
    timestamp: str
    permalink: str = ""
    root_post_id: str = ""
    replied_to_id: str = ""
    kind: str = "external"  # external | inbound | nested
    root_text: str = ""
    score: float = 0.0


def is_skippable_text(text: str, cfg: dict[str, Any]) -> bool:
    low = text.lower()
    return any(w.lower() in low for w in cfg.get("skip_keywords", []))


def relevant_score(text: str, cfg: dict[str, Any]) -> int:
    low = text.lower()
    return sum(1 for w in cfg.get("topic_keywords", []) if w.lower() in low)


def clean_model_text(text: str) -> str:
    t = text.strip().strip('"').strip("'")
    t = re.sub(r"^[-*•]\s*", "", t)
    t = t.replace("```", "")
    t = MULTISPACE_RE.sub(" ", t).strip()
    return t


def quality_gate(text: str, cfg: dict[str, Any], state: dict[str, Any], *, external: bool) -> tuple[bool, str]:
    t = clean_model_text(text)
    if len(t) < 10:
        return False, "too_short"
    if len(t) > 120:
        return False, "too_long"
    if not KOREAN_OR_ALNUM_RE.search(t):
        return False, "no_content"
    if URL_RE.search(t):
        return False, "url"
    if MENTION_RE.search(t):
        return False, "mention"
    if HASHTAG_RE.search(t):
        return False, "hashtag"
    low = t.lower()
    for w in cfg.get("sales_words_blocked_in_auto_reply", []):
        if w.lower() in low:
            return False, f"sales:{w}"
    # 과장/단정 자동문구 차단
    for w in ["무조건", "100%", "반드시 대박", "확실히 돈", "당첨", "보장합니다"]:
        if w.lower() in low:
            return False, f"claim:{w}"
    h = text_hash(t)
    recent = state.get("sent", [])[-500:]
    recent_hashes = {x.get("text_hash") for x in recent}
    if h in recent_hashes:
        return False, "duplicate"
    # 문장 일부만 바꾼 복붙도 차단한다.
    norm = MULTISPACE_RE.sub(" ", t.lower()).strip()
    for old in recent[-120:]:
        prev = MULTISPACE_RE.sub(" ", str(old.get("text") or "").lower()).strip()
        if prev and difflib.SequenceMatcher(None, norm, prev).ratio() >= 0.82:
            return False, "near_duplicate"
    if external and ("프로필" in t or "상담" in t or "무료운세" in t):
        return False, "promotion"
    return True, "ok"


def revenue_intent(candidate: Candidate, cfg: dict[str, Any]) -> bool:
    """Only inbound users who explicitly show fortune-reading intent may receive a soft CTA."""
    if candidate.kind == "external":
        return False
    low = (candidate.text or "").lower()
    return any(str(w).lower() in low for w in cfg.get("revenue_intent_keywords", []))


def revenue_used_today(state: dict[str, Any]) -> int:
    d = date_key()
    return sum(1 for x in state.get("sent", []) if x.get("date_kst") == d and x.get("revenue_cta"))


def maybe_add_revenue_cta(text: str, candidate: Candidate, cfg: dict[str, Any], state: dict[str, Any]) -> tuple[str, bool]:
    """Growth first: at most a small capped share of high-intent inbound replies gets a tracked link."""
    if not revenue_intent(candidate, cfg):
        return text, False
    if revenue_used_today(state) >= int(cfg.get("revenue_link_daily_cap", 1)):
        return text, False
    # Stable 30% gate by target id; prevents every eligible conversation from becoming promotional.
    share = float(cfg.get("revenue_share_target", 0.30))
    bucket = int(hashlib.sha256((candidate.id + "|revenue").encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    if bucket >= share:
        return text, False
    from threads_conversion import tracked_url
    url = tracked_url("reply", date_key())
    return text.rstrip() + "\n내 사주 기준으로 직접 확인하려면 여기서 무료로 먼저 볼 수 있어요. " + url, True


def generate_reply(candidate: Candidate, cfg: dict[str, Any], state: dict[str, Any]) -> str | None:
    if llm is None:
        return None
    if candidate.kind == "external":
        prompt = f"""당신은 Threads의 사주·명리 대화에 참여하는 '현담' 계정의 편집자다.
상대 글을 읽고 자연스러운 한국어 답글 1개만 써라.

상대 계정: @{candidate.username}
상대 글: {candidate.text[:700]}

목표:
- 상대 글에 없는 유용한 관점 하나를 보태거나, 글쓴이가 답하고 싶어지는 구체적 질문 하나를 한다.
- 사주/명리 전문가끼리 대화하듯 차분하고 자연스럽게 쓴다.

필수 규칙:
- 20~90자, 1~2문장.
- 링크, 해시태그, @멘션, 사이트/앱/상담/구매/프로필 홍보 금지.
- '좋은 글 감사합니다', '공감합니다' 같은 빈말만 쓰지 않는다.
- 실제 경험을 지어내지 않는다('저도 같은 일주인데' 같은 허위 경험 금지).
- 미래를 단정하거나 공포를 조장하지 않는다.
- 시비조/교정질/우월감 금지. 다른 해석이면 부드럽게 표현한다.
- 답글 문장만 출력한다."""
    else:
        prompt = f"""Threads에서 내 글에 달린 댓글에 답글을 쓴다.
내 계정: @gsdo10042026 (현담)
내 원글: {candidate.root_text[:600]}
받은 댓글: {candidate.text[:600]}

규칙:
- 댓글 내용에 실제로 반응하는 자연스러운 한국어 1~2문장, 15~100자.
- 상대가 이어서 말하기 쉬운 짧은 질문을 넣어도 좋다.
- 링크/해시태그/@멘션/판매/상담 유도 금지.
- 운세를 단정하거나 공포를 조장하지 않는다.
- 댓글이 존댓말이면 존댓말, 짧은 반말이면 부드러운 반말로 맞춘다.
- 답글 문장만 출력한다."""
    out = llm.ask(prompt, max_tokens=160, temperature=0.72, retry_gemini=False)
    if not out:
        return None
    out = clean_model_text(out)
    ok, reason = quality_gate(out, cfg, state, external=(candidate.kind == "external"))
    if not ok:
        log(f"품질게이트 폐기({reason}): {out[:80]}")
        return None
    return out


def api_capabilities(api: ThreadsAPI, cfg: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {"checked_at": utcnow().isoformat(), "basic": False,
                              "read_replies": False, "profile_posts": False,
                              "keyword_search": False, "mentions": False, "token_app_id": None,
                              "token_scopes": [], "missing_recommended_scopes": [],
                              "errors": {}}
    # Access Token Debugger: user token itself is used as caller credential.
    # Persist only app_id/scopes; never persist or print the token value.
    try:
        dbg = api.get("debug_token", {"input_token": api.token})
        data = dbg.get("data") or {}
        result["token_app_id"] = data.get("app_id")
        scopes = sorted(set(data.get("scopes") or []))
        result["token_scopes"] = scopes
        recommended = {
            "threads_basic", "threads_content_publish", "threads_read_replies",
            "threads_manage_replies", "threads_manage_insights", "threads_keyword_search",
            "threads_manage_mentions", "threads_delete", "threads_profile_discovery"
        }
        result["missing_recommended_scopes"] = sorted(recommended - set(scopes))
    except APIError as e:
        result["errors"]["debug_token"] = str(e)[:300]
    probes = [
        ("basic", "me", {"fields": "id,username,name"}),
        ("read_replies", "me/replies", {"fields": "id,text,timestamp,replied_to,root_post", "limit": 1}),
        ("profile_posts", "profile_posts", {"username": cfg["target_accounts"][0],
                                             "fields": THREAD_FIELDS, "limit": 1}),
        ("keyword_search", "keyword_search", {"q": "사주", "search_type": "RECENT",
                                                "fields": THREAD_FIELDS, "limit": 1}),
        ("mentions", "me/mentions", {"fields": THREAD_FIELDS, "limit": 1}),
    ]
    for name, path, params in probes:
        try:
            api.get(path, params)
            result[name] = True
        except APIError as e:
            result["errors"][name] = str(e)[:300]
    save_json(CAP_PATH, result)
    return result


def my_recent_posts(api: ThreadsAPI, cfg: dict[str, Any]) -> list[dict[str, Any]]:
    j = api.get("me/threads", {"fields": "id,text,timestamp,username,permalink,has_replies",
                               "limit": int(cfg.get("recent_own_posts", 12))})
    return j.get("data", [])


def inbound_candidates(api: ThreadsAPI, cfg: dict[str, Any], state: dict[str, Any]) -> list[Candidate]:
    handled = set(state.get("handled_inbound_ids", []))
    out: list[Candidate] = []
    for post in my_recent_posts(api, cfg):
        if not post.get("has_replies"):
            continue
        pid = str(post.get("id") or "")
        if not pid:
            continue
        try:
            j = api.get(f"{pid}/conversation", {"fields": REPLY_FIELDS, "reverse": "true", "limit": 50})
        except APIError as e:
            log(f"conversation 조회 실패 {pid}: {e}")
            continue
        rows = j.get("data", [])
        owned_ids = {str(r.get("id") or "") for r in rows if r.get("is_reply_owned_by_me")}
        my_username = str(cfg.get("account_username") or "").lower()
        for r in rows:
            rid = str(r.get("id") or "")
            text = (r.get("text") or "").strip()
            username = str(r.get("username") or "")
            if (not rid or rid in handled or not text or r.get("is_reply_owned_by_me") or
                    (my_username and username.lower() == my_username)):
                continue
            if is_skippable_text(text, cfg):
                continue
            replied_to = r.get("replied_to") or {}
            root = r.get("root_post") or {}
            replied_to_id = str(replied_to.get("id") or "")
            root_id = str(root.get("id") or pid)
            if replied_to_id in {"", pid}:
                kind = "inbound"
            elif replied_to_id in owned_ids:
                kind = "nested"
            else:
                # 다른 사용자끼리 이어가는 대화에는 자동으로 끼어들지 않는다.
                continue
            out.append(Candidate(id=rid, username=username, text=text,
                                 timestamp=str(r.get("timestamp") or ""), permalink=str(r.get("permalink") or ""),
                                 root_post_id=root_id, replied_to_id=replied_to_id, kind=kind,
                                 root_text=str(post.get("text") or ""),
                                 score=max(0.0, 1000.0 - age_hours(r.get("timestamp")))))
    out.sort(key=lambda c: c.score, reverse=True)
    return out


def external_candidates(api: ThreadsAPI, cfg: dict[str, Any], state: dict[str, Any], caps: dict[str, Any]) -> list[Candidate]:
    seen = set(state.get("external_target_ids", []))
    targets = list(cfg.get("target_accounts", []))
    out: dict[str, Candidate] = {}
    max_age = float(cfg.get("max_target_age_hours", 36))

    # 날짜별 회전: 매일 시작 계정을 달리해 같은 곳에 몰리지 않게 한다.
    if targets:
        shift = int(hashlib.sha256(date_key().encode()).hexdigest()[:4], 16) % len(targets)
        targets = targets[shift:] + targets[:shift]

    if caps.get("profile_posts"):
        for rank, username in enumerate(targets[:10]):
            try:
                j = api.get("profile_posts", {"username": username, "fields": THREAD_FIELDS, "limit": 8})
            except APIError as e:
                log(f"profile_posts @{username} 건너뜀: {e}")
                continue
            for p in j.get("data", []):
                pid = str(p.get("id") or "")
                text = (p.get("text") or "").strip()
                if not pid or pid in seen or not text or len(text) < 30 or p.get("is_reply"):
                    continue
                age = age_hours(p.get("timestamp"))
                if age > max_age or is_skippable_text(text, cfg):
                    continue
                rel = relevant_score(text, cfg)
                if rel <= 0:
                    continue
                score = 100.0 - age + rel * 15 - rank * 0.5 + (8 if p.get("has_replies") else 0)
                out[pid] = Candidate(id=pid, username=str(p.get("username") or username), text=text,
                                     timestamp=str(p.get("timestamp") or ""), permalink=str(p.get("permalink") or ""),
                                     kind="external", score=score)

    # profile_posts 권한이 없거나 후보가 적으면 keyword_search 공식 API로 보완.
    if caps.get("keyword_search") and len(out) < 5:
        allowed = {x.lower() for x in targets}
        for q in cfg.get("topic_keywords", [])[:6]:
            try:
                j = api.get("keyword_search", {"q": q, "search_type": "RECENT",
                                               "fields": THREAD_FIELDS, "limit": 25})
            except APIError as e:
                log(f"keyword_search '{q}' 건너뜀: {e}")
                continue
            for p in j.get("data", []):
                username = str(p.get("username") or "")
                if username.lower() not in allowed:
                    continue
                pid = str(p.get("id") or "")
                text = (p.get("text") or "").strip()
                if not pid or pid in seen or not text or len(text) < 30 or p.get("is_reply"):
                    continue
                age = age_hours(p.get("timestamp"))
                if age > max_age or is_skippable_text(text, cfg):
                    continue
                rel = relevant_score(text, cfg)
                if rel <= 0:
                    continue
                score = 95.0 - age + rel * 15 + (8 if p.get("has_replies") else 0)
                cur = out.get(pid)
                if cur is None or score > cur.score:
                    out[pid] = Candidate(id=pid, username=username, text=text,
                                         timestamp=str(p.get("timestamp") or ""), permalink=str(p.get("permalink") or ""),
                                         kind="external", score=score)
    return sorted(out.values(), key=lambda c: c.score, reverse=True)


def verify_target(api: ThreadsAPI, target_id: str) -> dict[str, Any]:
    j = api.get(target_id, {"fields": "id,text,timestamp,username,permalink,is_reply"})
    if str(j.get("id") or "") != str(target_id):
        raise APIError("target id preflight mismatch")
    return j


def verify_published_reply(api: ThreadsAPI, reply_id: str, target_id: str, text: str) -> dict[str, Any]:
    last_error = "not found"
    for delay in (2, 4, 7):
        time.sleep(delay)
        try:
            j = api.get("me/replies", {"fields": REPLY_FIELDS, "limit": 50})
        except APIError as e:
            last_error = str(e)
            continue
        rows = j.get("data", [])
        match = next((r for r in rows if str(r.get("id") or "") == str(reply_id)), None)
        if match is None:
            h = text_hash(text)
            match = next((r for r in rows if text_hash(str(r.get("text") or "")) == h), None)
        if not match:
            last_error = "published reply not visible in me/replies"
            continue
        actual = str((match.get("replied_to") or {}).get("id") or "")
        if actual != str(target_id):
            raise LocationMismatch(f"reply {match.get('id')} replied_to={actual}, expected={target_id}")
        return match
    raise APIError(f"post-publish verification failed: {last_error}")


def pause(reason: str, detail: dict[str, Any] | None = None) -> None:
    save_json(PAUSE_PATH, {"paused_at": utcnow().isoformat(), "reason": reason, "detail": detail or {}})
    log(f"🚨 자동발송 정지: {reason}")


def publish_reply(api: ThreadsAPI, candidate: Candidate, text: str) -> dict[str, Any]:
    # 대상이 실제로 존재하는지 발송 직전 재확인한다.
    verify_target(api, candidate.id)
    j = api.post("me/threads", {"media_type": "TEXT", "text": text,
                                "reply_to_id": candidate.id, "auto_publish_text": "true"})
    rid = str(j.get("id") or "")
    if not rid:
        raise APIError(f"reply publish returned no id: {safe_error_payload(j)}")
    try:
        verified = verify_published_reply(api, rid, candidate.id, text)
    except LocationMismatch as e:
        # 잘못 달린 답글은 가능한 경우 즉시 삭제하고 전체 자동화를 잠근다.
        try:
            api.delete(rid)
        except Exception:
            pass
        pause("reply_location_mismatch", {"expected": candidate.id, "reply_id": rid, "error": str(e)})
        raise
    return verified


def can_send_external(cfg: dict[str, Any], state: dict[str, Any], username: str) -> bool:
    b = today_bucket(state)
    if b.get("total", 0) >= int(cfg.get("total_daily_cap", 10)):
        return False
    if b.get("external", 0) >= int(cfg.get("external_daily_cap", 3)):
        return False
    if (b.get("per_target") or {}).get(username.lower(), 0) >= int(cfg.get("per_target_daily_cap", 1)):
        return False
    return True


def can_send_inbound(cfg: dict[str, Any], state: dict[str, Any]) -> bool:
    b = today_bucket(state)
    return (b.get("total", 0) < int(cfg.get("total_daily_cap", 10)) and
            b.get("inbound", 0) + b.get("nested", 0) < int(cfg.get("inbound_daily_cap", 8)))


def record_send(state: dict[str, Any], candidate: Candidate, text: str, reply: dict[str, Any], *, dry_run: bool) -> None:
    if dry_run:
        return
    b = today_bucket(state)
    b["total"] = int(b.get("total", 0)) + 1
    if candidate.kind == "external":
        b["external"] = int(b.get("external", 0)) + 1
        pt = b.setdefault("per_target", {})
        key = candidate.username.lower()
        pt[key] = int(pt.get(key, 0)) + 1
        state.setdefault("external_target_ids", []).append(candidate.id)
    else:
        b[candidate.kind] = int(b.get(candidate.kind, 0)) + 1
        state.setdefault("handled_inbound_ids", []).append(candidate.id)
    state.setdefault("sent", []).append({
        "at": utcnow().isoformat(), "kind": candidate.kind, "target_id": candidate.id,
        "target_username": candidate.username, "reply_id": str(reply.get("id") or ""),
        "text_hash": text_hash(text), "text": text,
        "verified_replied_to": str((reply.get("replied_to") or {}).get("id") or ""),
    })


def mark_inbound_handled(state: dict[str, Any], cid: str) -> None:
    state.setdefault("handled_inbound_ids", []).append(cid)


def run_growth(api: ThreadsAPI, cfg: dict[str, Any], state: dict[str, Any], caps: dict[str, Any],
               *, send: bool, do_external: bool, do_inbound: bool) -> dict[str, Any]:
    actions: list[dict[str, Any]] = []
    if PAUSE_PATH.exists() and send:
        p = load_json(PAUSE_PATH, {})
        log(f"PAUSED 파일 존재 — 실제 발송 안 함: {p.get('reason')}")
        send = False

    # 1) 내 글 댓글/대댓글 우선. 이미 들어온 사람과 대화를 이어가는 게 가장 안전하다.
    if do_inbound and caps.get("read_replies"):
        try:
            candidates = inbound_candidates(api, cfg, state)
        except APIError as e:
            candidates = []
            log(f"inbound scan 실패: {e}")
        n = 0
        for c in candidates:
            if n >= int(cfg.get("inbound_per_run", 3)) or not can_send_inbound(cfg, state):
                break
            text = generate_reply(c, cfg, state)
            if not text:
                # 같은 댓글을 다음 실행마다 무한 재시도하지 않게 품질 실패도 처리완료로 기록
                mark_inbound_handled(state, c.id)
                continue
            text, revenue_cta = maybe_add_revenue_cta(text, c, cfg, state)
            log(f"{('[SEND]' if send else '[DRY]')} {c.kind} @{c.username}: {text}")
            reply = {"id": "dry", "replied_to": {"id": c.id}}
            if send:
                try:
                    reply = publish_reply(api, c, text)
                except (APIError, LocationMismatch) as e:
                    log(f"발송 실패({c.kind}): {e}")
                    # 권한/대상 오류가 반복되는 것을 막기 위해 이 실행은 중단
                    break
            record_send(state, c, text, reply, dry_run=not send)
            if state.get("sent"):
                state["sent"][-1]["revenue_cta"] = bool(revenue_cta)
                state["sent"][-1]["date_kst"] = date_key()
            actions.append({"kind": c.kind, "target": c.id, "username": c.username,
                            "text": text, "sent": bool(send), "revenue_cta": bool(revenue_cta)})
            n += 1

    # 2) 외부 큰 계정 댓글. 공식 discovery/search 권한이 있을 때만.
    if do_external and (caps.get("profile_posts") or caps.get("keyword_search")):
        try:
            candidates = external_candidates(api, cfg, state, caps)
        except APIError as e:
            candidates = []
            log(f"external scan 실패: {e}")
        n = 0
        for c in candidates:
            if n >= int(cfg.get("external_per_run", 1)):
                break
            if not can_send_external(cfg, state, c.username):
                continue
            text = generate_reply(c, cfg, state)
            if not text:
                continue
            log(f"{('[SEND]' if send else '[DRY]')} external @{c.username}: {text}")
            reply = {"id": "dry", "replied_to": {"id": c.id}}
            if send:
                try:
                    reply = publish_reply(api, c, text)
                except LocationMismatch:
                    raise
                except APIError as e:
                    log(f"외부 댓글 발송 실패: {e}")
                    break
            record_send(state, c, text, reply, dry_run=not send)
            actions.append({"kind": "external", "target": c.id, "username": c.username,
                            "permalink": c.permalink, "text": text, "sent": bool(send)})
            n += 1
    elif do_external:
        log("외부댓글 기능은 공식 profile_posts/keyword_search 권한이 없어 비활성 상태")

    state["last_run_at"] = utcnow().isoformat()
    trim_state(state)
    if send:
        save_json(STATE_PATH, state)
    return {"at": utcnow().isoformat(), "date_kst": date_key(), "send": send,
            "capabilities": {k: v for k, v in caps.items() if k != "errors"},
            "actions": actions, "day": today_bucket(state), "paused": PAUSE_PATH.exists()}


def write_report(result: dict[str, Any], caps: dict[str, Any]) -> None:
    lines = [
        f"# Threads 성장 자동화 보고 — {result['date_kst']}", "",
        f"- 실행: {'실제 발송' if result.get('send') else '드라이런/점검'}",
        f"- PAUSED: {result.get('paused')}",
        f"- 오늘 카운트: `{json.dumps(result.get('day', {}), ensure_ascii=False)}`",
        "",
        "## API 기능", "",
    ]
    for k in ["basic", "read_replies", "profile_posts", "keyword_search", "mentions"]:
        lines.append(f"- {k}: {'✅' if caps.get(k) else '❌'}")
    if caps.get("token_app_id"):
        lines.append(f"- token app id: `{caps.get('token_app_id')}`")
    if caps.get("token_scopes"):
        lines.append("- token scopes: `" + ", ".join(caps.get("token_scopes") or []) + "`")
    if caps.get("missing_recommended_scopes"):
        lines.append("- 추가 권장 scope: `" + ", ".join(caps.get("missing_recommended_scopes") or []) + "`")
    if caps.get("errors"):
        lines += ["", "## 미지원/권한 오류", ""]
        for k, v in caps["errors"].items():
            lines.append(f"- {k}: `{str(v)[:240]}`")
    lines += ["", "## 이번 실행", ""]
    acts = result.get("actions") or []
    if not acts:
        lines.append("- 발송/초안 대상 없음")
    else:
        for a in acts:
            lines.append(f"- {a.get('kind')} @{a.get('username')}: {a.get('text')} ({'sent' if a.get('sent') else 'dry'})")
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--preflight", action="store_true")
    ap.add_argument("--send", action="store_true", help="실제 발송. 없으면 드라이런")
    ap.add_argument("--no-external", action="store_true")
    ap.add_argument("--no-inbound", action="store_true")
    ap.add_argument("--clear-pause", action="store_true")
    a = ap.parse_args()

    if a.clear_pause:
        PAUSE_PATH.unlink(missing_ok=True)
        log("PAUSED 해제")
        if not (a.preflight or a.send):
            return 0

    tok = os.environ.get("THREADS_ACCESS_TOKEN", "").strip()
    uid = os.environ.get("THREADS_USER_ID", "").strip()
    if not tok or not uid:
        log("[FAIL] THREADS_ACCESS_TOKEN/THREADS_USER_ID 없음")
        return 2
    cfg = load_config()
    state = load_state()
    api = ThreadsAPI(tok)

    caps = api_capabilities(api, cfg)
    log("capabilities: " + json.dumps({k: v for k, v in caps.items() if k != "errors"}, ensure_ascii=False))
    if not caps.get("basic"):
        write_report({"date_kst": date_key(), "send": False, "day": today_bucket(state),
                      "actions": [], "paused": PAUSE_PATH.exists()}, caps)
        return 3
    if a.preflight:
        write_report({"date_kst": date_key(), "send": False, "day": today_bucket(state),
                      "actions": [], "paused": PAUSE_PATH.exists()}, caps)
        return 0

    try:
        result = run_growth(api, cfg, state, caps, send=a.send,
                            do_external=not a.no_external, do_inbound=not a.no_inbound)
    except LocationMismatch as e:
        log(str(e))
        return 5
    write_report(result, caps)
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    raise SystemExit(main())
