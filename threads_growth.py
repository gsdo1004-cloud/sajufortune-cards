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
import math
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

try:
    from threads_fortune_public import (
        public_reply as public_fortune_reply,
        has_birth_detail as public_birth_detail,
    )
except Exception:
    public_fortune_reply = None
    public_birth_detail = None

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

URL_RE = re.compile(r"(?:https?://|www\.|\b(?:[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?\.)+(?:[a-z]{2,24}|xn--[a-z0-9-]{2,59})(?:/[^\s]*)?)", re.I)
MENTION_RE = re.compile(r"@[A-Za-z0-9._]+")
HASHTAG_RE = re.compile(r"#[^\s#]+")
MULTISPACE_RE = re.compile(r"\s+")
KOREAN_OR_ALNUM_RE = re.compile(r"[가-힣A-Za-z0-9]")


class APIError(RuntimeError):
    def __init__(self, message: str, *, code: int | None = None, subcode: int | None = None,
                 status: int | None = None, response_json_valid: bool | None = None):
        super().__init__(message)
        self.code = code
        self.subcode = subcode
        self.status = status
        self.response_json_valid = response_json_valid


class StateCorruption(RuntimeError):
    pass


class PublishHeld(APIError):
    pass


class CandidateScanError(RuntimeError):
    pass


class LocationMismatch(RuntimeError):
    def __init__(self, message: str, reply_id: str = ""):
        super().__init__(message)
        self.reply_id = str(reply_id or "")


class UncertainPublish(RuntimeError):
    """POST returned an id, but final placement/visibility could not be verified."""
    def __init__(self, reply_id: str, message: str):
        super().__init__(message)
        self.reply_id = str(reply_id or "")


class WriterLockBusy(RuntimeError):
    pass


class _WriterLock:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.handle = None

    def __enter__(self):
        try:
            import fcntl
        except ImportError as exc:
            raise WriterLockBusy("writer lock unavailable on this platform") from exc
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, OSError) as exc:
            self.handle.close()
            self.handle = None
            raise WriterLockBusy("another live writer is active") from exc
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.handle is None:
            return False
        try:
            import fcntl
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        finally:
            self.handle.close()
            self.handle = None
        return False


def writer_lock(path: Path | None = None) -> _WriterLock:
    return _WriterLock(path or (BASE / "threads_growth.lock"))


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
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    with tmp.open("w", encoding="utf-8") as f:
        f.write(payload)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    # Linux/GitHub Actions에서는 rename 자체까지 디렉터리 메타데이터로 내구화한다.
    # 여기서 실패하면 발송 예약이 durable하다고 보장할 수 없으므로 POST 전에 실패를 전파한다.
    if os.name == "posix":
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        dfd = os.open(str(path.parent), flags)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)


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
        "external_growth": {"stage_index": 0, "stage_started_kst": None, "history": []},
        "last_run_at": None,
    }


def load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return default_state()
    try:
        s = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        raise StateCorruption(f"state parse failed: {type(exc).__name__}") from exc
    if not isinstance(s, dict) or s.get("schema") != 1:
        raise StateCorruption("state schema invalid")

    # 이 키들은 구버전 상태에도 존재하던 안전 카운터/영수증이다. 파일이 있는데
    # 이들이 사라졌다면 빈 상태로 재구성하지 않고 손상으로 간주한다.
    required_core = {"handled_inbound_ids", "external_target_ids", "sent", "days", "last_run_at"}
    missing = sorted(required_core - set(s))
    if missing:
        raise StateCorruption("state core fields missing: " + ",".join(missing))
    if not isinstance(s.get("handled_inbound_ids"), list) or not isinstance(s.get("external_target_ids"), list):
        raise StateCorruption("state id lists invalid")
    if not isinstance(s.get("sent"), list) or not isinstance(s.get("days"), dict):
        raise StateCorruption("state structure invalid")

    count_keys = {
        "external", "inbound", "nested", "total", "external_measured", "external_engaged",
        "external_replies", "external_likes", "external_errors", "external_safety_stops",
        "external_insight_failures",
    }
    core_day_fields = {"external", "inbound", "nested", "total", "per_target"}
    for day, bucket in s["days"].items():
        if not isinstance(day, str) or not isinstance(bucket, dict):
            raise StateCorruption("day bucket invalid")
        missing_day = sorted(core_day_fields - set(bucket))
        if missing_day:
            raise StateCorruption("day bucket core fields missing: " + ",".join(missing_day))
        if not isinstance(bucket.get("per_target"), dict):
            raise StateCorruption("per_target invalid")
        for key in count_keys:
            if key in bucket:
                value = bucket.get(key)
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    raise StateCorruption(f"day counter invalid: {key}")
        for value in (bucket.get("per_target") or {}).values():
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise StateCorruption("per_target counter invalid")

    allowed_effects = {"PENDING", "UNKNOWN", "CONFIRMED"}
    for row in s["sent"]:
        if not isinstance(row, dict):
            raise StateCorruption("sent receipt invalid")
        effect = row.get("effect")
        if effect is not None and effect not in allowed_effects:
            raise StateCorruption("sent receipt effect invalid")

    growth = s.get("external_growth")
    if growth is None:
        s["external_growth"] = dict(default_state()["external_growth"])
    elif not isinstance(growth, dict):
        raise StateCorruption("external_growth invalid")
    else:
        idx = growth.get("stage_index", 0)
        if isinstance(idx, bool) or not isinstance(idx, int) or idx < 0:
            raise StateCorruption("external_growth stage invalid")
        hist = growth.get("history", [])
        if not isinstance(hist, list):
            raise StateCorruption("external_growth history invalid")
        growth.setdefault("stage_index", 0)
        growth.setdefault("stage_started_kst", None)
        growth.setdefault("history", [])
    return s


def trim_state(s: dict[str, Any]) -> None:
    s["handled_inbound_ids"] = s.get("handled_inbound_ids", [])[-2000:]
    s["external_target_ids"] = s.get("external_target_ids", [])[-2000:]
    s["sent"] = s.get("sent", [])[-1500:]
    # 최근 45일만 유지
    keys = sorted((s.get("days") or {}).keys())
    for k in keys[:-45]:
        s["days"].pop(k, None)


def _ensure_day_bucket(bucket: dict[str, Any]) -> dict[str, Any]:
    defaults = {
        "external": 0, "inbound": 0, "nested": 0, "total": 0, "per_target": {},
        "external_measured": 0, "external_engaged": 0, "external_replies": 0,
        "external_likes": 0, "external_errors": 0, "external_safety_stops": 0,
        "external_insight_failures": 0,
    }
    for key, value in defaults.items():
        bucket.setdefault(key, value.copy() if isinstance(value, dict) else value)
    return bucket


def day_bucket(state: dict[str, Any], key: str) -> dict[str, Any]:
    return _ensure_day_bucket(state.setdefault("days", {}).setdefault(key, {}))


def today_bucket(state: dict[str, Any], now: dt.datetime | None = None) -> dict[str, Any]:
    return day_bucket(state, date_key(now))


def text_hash(text: str) -> str:
    norm = MULTISPACE_RE.sub(" ", text.strip().lower())
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:20]


def normalize_username(value: Any) -> str:
    """Threads username comparison key: trim spaces, optional leading @, case-insensitive."""
    return str(value or "").strip().lstrip("@").strip().lower()


def display_username(value: Any) -> str:
    return str(value or "").strip().lstrip("@").strip()


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
            raise APIError(f"HTTP {r.status_code}: non-json response", status=r.status_code,
                           response_json_valid=False)
        if r.status_code >= 400 or "error" in j:
            e = j.get("error") or {}
            raise APIError(safe_error_payload(j), code=e.get("code"),
                           subcode=e.get("error_subcode"), status=r.status_code,
                           response_json_valid=True)
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
    source_query: str = ""
    search_type: str = ""
    relevance: int = 0
    conversation_signal: float = 0.0


def is_skippable_text(text: str, cfg: dict[str, Any]) -> bool:
    low = text.lower()
    return any(w.lower() in low for w in cfg.get("skip_keywords", []))


def relevant_score(text: str, cfg: dict[str, Any]) -> int:
    low = text.lower()
    return sum(1 for w in cfg.get("topic_keywords", []) if w.lower() in low)



def conversation_signal_score(text: str, cfg: dict[str, Any]) -> float:
    """질문/고민처럼 실제 대화가 이어질 글은 올리고, 광고·맞팔 미끼는 내린다."""
    low = (text or "").lower()
    score = 0.0
    if "?" in text or "？" in text:
        score += 3.0
    for word in cfg.get("external_conversation_keywords", ["궁금", "왜", "어떻게", "고민", "생각"]):
        if str(word).lower() in low:
            score += 1.5
    if 35 <= len(text) <= 320:
        score += 1.0
    for word in cfg.get("external_bait_keywords", ["이벤트", "할인", "구매", "맞팔", "선팔"]):
        if str(word).lower() in low:
            score -= 4.0
    return max(-20.0, min(20.0, score))


def rank_external_candidates(rows: list[Candidate]) -> list[Candidate]:
    """점수순 정렬 후 같은 작성자는 최고 후보 하나만 남긴다."""
    ranked = sorted(rows, key=lambda c: (c.score, c.timestamp, c.id), reverse=True)
    out: list[Candidate] = []
    seen_authors: set[str] = set()
    for candidate in ranked:
        author = (candidate.username or candidate.id).strip().lower()
        if author in seen_authors:
            continue
        seen_authors.add(author)
        out.append(candidate)
    return out


def _growth_state(state: dict[str, Any], now: dt.datetime | None = None) -> dict[str, Any]:
    growth = state.setdefault("external_growth", {})
    growth.setdefault("stage_index", 0)
    growth.setdefault("stage_started_kst", None)
    growth.setdefault("history", [])
    if not growth.get("stage_started_kst"):
        growth["stage_started_kst"] = date_key(now)
    return growth


def _growth_stages(cfg: dict[str, Any]) -> list[int]:
    raw = cfg.get("external_growth_stages") or [int(cfg.get("external_daily_cap", 0))]
    stages = [max(0, int(x)) for x in raw]
    return stages or [0]


def effective_external_daily_cap(cfg: dict[str, Any], state: dict[str, Any],
                                 now: dt.datetime | None = None) -> int:
    growth = _growth_state(state, now)
    stages = _growth_stages(cfg)
    idx = max(0, min(int(growth.get("stage_index", 0)), len(stages) - 1))
    growth["stage_index"] = idx
    return stages[idx]


def _completed_growth_window(state: dict[str, Any], now: dt.datetime, days: int) -> list[dict[str, Any]]:
    today = dt.date.fromisoformat(date_key(now))
    rows = []
    for offset in range(days, 0, -1):
        key = (today - dt.timedelta(days=offset)).isoformat()
        rows.append(day_bucket(state, key))
    return rows


def maybe_advance_external_stage(cfg: dict[str, Any], state: dict[str, Any],
                                 now: dt.datetime | None = None, *,
                                 telemetry_available: bool = True) -> dict[str, Any]:
    """7일 안전/성과 게이트를 통과할 때만 8→12→20으로 한 단계 올린다."""
    now = now or utcnow()
    growth = _growth_state(state, now)
    stages = _growth_stages(cfg)
    idx = max(0, min(int(growth.get("stage_index", 0)), len(stages) - 1))
    started = dt.date.fromisoformat(str(growth.get("stage_started_kst") or date_key(now)))
    today = dt.date.fromisoformat(date_key(now))
    stage_days = max(1, int(cfg.get("external_growth_stage_days", 7)))
    window = _completed_growth_window(state, now, stage_days)
    sent = sum(int(x.get("external", 0)) for x in window)
    measured = sum(int(x.get("external_measured", 0)) for x in window)
    engaged = sum(int(x.get("external_engaged", 0)) for x in window)
    errors = sum(int(x.get("external_errors", 0)) for x in window)
    safety_stops = sum(int(x.get("external_safety_stops", 0)) for x in window)
    insight_failures = sum(int(x.get("external_insight_failures", 0)) for x in window)
    engagement_rate = engaged / max(1, measured)
    error_rate = errors / max(1, sent + errors)
    insight_failure_rate = insight_failures / max(1, measured + insight_failures)
    unresolved = len(unresolved_sends(state))
    require_telemetry = bool(cfg.get("external_growth_require_insights", True))
    promoted = False
    eligible_age = (today - started).days >= stage_days
    if idx < len(stages) - 1 and eligible_age:
        healthy = (
            sent >= int(cfg.get("external_growth_min_stage_sends", 14))
            and measured >= int(cfg.get("external_growth_min_measured", 8))
            and engagement_rate >= float(cfg.get("external_growth_min_engagement_rate", 0.02))
            and error_rate <= float(cfg.get("external_growth_max_error_rate", 0.05))
            and insight_failure_rate <= float(cfg.get("external_growth_max_insight_failure_rate", 0.0))
            and (telemetry_available or not require_telemetry)
            and unresolved == 0
            and safety_stops == 0
        )
        if healthy:
            old_cap = stages[idx]
            idx += 1
            growth["stage_index"] = idx
            growth["stage_started_kst"] = today.isoformat()
            growth.setdefault("history", []).append({
                "at": now.isoformat(), "from_cap": old_cap, "to_cap": stages[idx],
                "sent": sent, "measured": measured, "engaged": engaged,
                "engagement_rate": round(engagement_rate, 4), "error_rate": round(error_rate, 4),
                "insight_failure_rate": round(insight_failure_rate, 4),
            })
            growth["history"] = growth["history"][-20:]
            promoted = True
    return {
        "stage_index": idx, "daily_cap": stages[idx], "promoted": promoted,
        "stage_started_kst": growth.get("stage_started_kst"), "sent": sent,
        "measured": measured, "engaged": engaged, "errors": errors,
        "safety_stops": safety_stops, "insight_failures": insight_failures,
        "engagement_rate": round(engagement_rate, 4), "error_rate": round(error_rate, 4),
        "insight_failure_rate": round(insight_failure_rate, 4),
        "telemetry_available": bool(telemetry_available), "unresolved": unresolved,
    }


def source_performance_bonus(state: dict[str, Any], source_query: str, search_type: str) -> float:
    """이미 측정된 외부 댓글 성과를 다음 후보 점수에 작은 보너스로 반영한다."""
    measured = 0
    points = 0.0
    for row in state.get("sent", [])[-500:]:
        if row.get("kind") != "external":
            continue
        if str(row.get("source_query") or "") != str(source_query or ""):
            continue
        if str(row.get("search_type") or "") != str(search_type or ""):
            continue
        metrics = row.get("external_metrics")
        if not isinstance(metrics, dict):
            continue
        measured += 1
        points += min(12.0, float(metrics.get("replies", 0) or 0) * 6.0
                      + float(metrics.get("likes", 0) or 0) * 1.0
                      + float(metrics.get("quotes", 0) or 0) * 2.0
                      + float(metrics.get("reposts", 0) or 0) * 2.0
                      + float(metrics.get("shares", 0) or 0) * 2.0)
    return min(12.0, points / max(1, measured)) if measured else 0.0


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
    max_len = 120 if external else 480
    if len(t) > max_len:
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
    if external:
        for phrase in cfg.get("external_promo_block_phrases", ["프로필", "상담", "무료운세", "링크", "구매", "결제", "할인", "이벤트", "설치", "다운로드", "dm", "디엠", "문의"]):
            if str(phrase).lower() in low:
                return False, f"promotion:{phrase}"
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
    """Capped inbound conversion CTA. External conversations are never promotional."""
    if candidate.kind == "external":
        return text, False
    used_total = revenue_used_today(state)
    if used_total >= int(cfg.get("revenue_daily_cap", 3)):
        return text, False
    high_intent = revenue_intent(candidate, cfg)
    if high_intent and revenue_used_today(state) < int(cfg.get("revenue_link_daily_cap", 1)):
        share = float(cfg.get("revenue_share_target", 0.30))
        bucket = int(hashlib.sha256((candidate.id + "|revenue").encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
        if bucket < share:
            from threads_conversion import tracked_url
            url = tracked_url("reply", date_key())
            return text.rstrip() + "\n내 사주 기준으로 직접 확인하려면 여기서 무료로 먼저 볼 수 있어요. " + url, True
    # Warm/general inbound: a softer profile CTA, separately capped, no direct URL.
    profile_used = sum(1 for x in state.get("sent", []) if x.get("date_kst") == date_key() and x.get("revenue_cta") and "프로필 첫 버튼" in str(x.get("text", "")))
    if profile_used >= int(cfg.get("revenue_profile_daily_cap", 0)):
        return text, False
    share = float(cfg.get("revenue_profile_share_target", 0.0))
    bucket = int(hashlib.sha256((candidate.id + "|profile").encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    if bucket < share:
        return text.rstrip() + "\n더 궁금하시면 프로필 첫 버튼에서 가볍게 확인해보실 수 있어요.", True
    return text, False


def generate_reply(candidate: Candidate, cfg: dict[str, Any], state: dict[str, Any]) -> str | None:
    # 내 글의 띠/출생연도 댓글은 LLM보다 정본 띠엔진을 먼저 사용한다.
    # 생년월일·출생시간이 공개 댓글에 있으면 원문을 되풀이하지 않고 상세 공개풀이한다.
    if candidate.kind != "external" and public_fortune_reply is not None:
        special = public_fortune_reply(candidate.text, date_key())
        if special:
            # 공개 사주 정밀풀이는 6~9줄 가독성을 유지한다.
            special = special.strip().replace("```", "")
            ok, reason = quality_gate(special, cfg, state, external=False)
            if ok:
                return special
            log(f"공개 띠풀이 게이트 폐기({reason}): {special[:80]}")
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
        except (APIError, requests.RequestException) as e:
            log(f"conversation 조회 실패 {pid}: {e}")
            raise CandidateScanError(f"conversation scan failed for {pid}: {e}") from e
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
    own_username = normalize_username(cfg.get("account_username"))
    targets = [display_username(x) for x in cfg.get("target_accounts", [])
               if display_username(x) and normalize_username(x) != own_username]
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
            except (APIError, requests.RequestException) as e:
                record_external_error(state)
                log(f"profile_posts @{username} 조회 실패: {e}")
                raise CandidateScanError(f"profile_posts scan failed for @{username}: {e}") from e
            for p in j.get("data", []):
                post_username = display_username(p.get("username") or username)
                if own_username and normalize_username(post_username) == own_username:
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
                conv = conversation_signal_score(text, cfg)
                perf = source_performance_bonus(state, username, "PROFILE")
                score = 100.0 - age + rel * 15 - rank * 0.5 + (8 if p.get("has_replies") else 0) + conv * 4 + perf
                out[pid] = Candidate(id=pid, username=post_username, text=text,
                                     timestamp=str(p.get("timestamp") or ""), permalink=str(p.get("permalink") or ""),
                                     kind="external", score=score, source_query=username, search_type="PROFILE",
                                     relevance=rel, conversation_signal=conv)

    # profile_posts 권한이 없거나 후보가 적으면 keyword_search 공식 API로 보완.
    if caps.get("keyword_search") and len(out) < 5:
        allowed = {normalize_username(x) for x in targets}
        discovery = bool(cfg.get("keyword_discovery_enabled", True))
        search_types = list(cfg.get("keyword_search_types", ["TOP", "RECENT"]))
        for q in cfg.get("topic_keywords", [])[:6]:
            for search_type in search_types:
                try:
                    j = api.get("keyword_search", {"q": q, "search_type": search_type,
                                                   "fields": THREAD_FIELDS, "limit": 25})
                except (APIError, requests.RequestException) as e:
                    record_external_error(state)
                    log(f"keyword_search '{q}'/{search_type} 조회 실패: {e}")
                    raise CandidateScanError(f"keyword search failed for {q}/{search_type}: {e}") from e
                for p in j.get("data", []):
                    username = display_username(p.get("username"))
                    if own_username and normalize_username(username) == own_username:
                        continue
                    if not discovery and normalize_username(username) not in allowed:
                        continue
                    pid = str(p.get("id") or "")
                    text = (p.get("text") or "").strip()
                    if not pid or pid in seen or not text or len(text) < 30 or p.get("is_reply"):
                        continue
                    age = age_hours(p.get("timestamp"))
                    if age > max_age or is_skippable_text(text, cfg):
                        continue
                    rel = relevant_score(text, cfg)
                    min_rel = int(cfg.get("keyword_discovery_min_relevance", 2 if discovery else 1))
                    if rel < min_rel:
                        continue
                    # TOP 결과는 Threads가 제공하는 인기/관련성 신호로 활용한다.
                    # 공개 API가 제공하지 않는 조회수/팔로워 수를 추정해서 만들지는 않는다.
                    top_bonus = float(cfg.get("keyword_top_bonus", 18)) if search_type == "TOP" else 0.0
                    conv = conversation_signal_score(text, cfg)
                    perf = source_performance_bonus(state, q, search_type)
                    score = 95.0 - age + rel * 15 + (8 if p.get("has_replies") else 0) + top_bonus + conv * 4 + perf
                    cur = out.get(pid)
                    if cur is None or score > cur.score:
                        out[pid] = Candidate(id=pid, username=username, text=text,
                                             timestamp=str(p.get("timestamp") or ""), permalink=str(p.get("permalink") or ""),
                                             kind="external", score=score, source_query=q, search_type=search_type,
                                             relevance=rel, conversation_signal=conv)
    return rank_external_candidates(list(out.values()))


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
            raise LocationMismatch(f"reply {match.get('id')} replied_to={actual}, expected={target_id}", str(match.get("id") or reply_id))
        return match
    raise APIError(f"post-publish verification failed: {last_error}")


def pause(reason: str, detail: dict[str, Any] | None = None) -> None:
    save_json(PAUSE_PATH, {"paused_at": utcnow().isoformat(), "reason": reason, "detail": detail or {}})
    log(f"🚨 자동발송 정지: {reason}")


def publish_reply(api: ThreadsAPI, candidate: Candidate, text: str) -> dict[str, Any]:
    # 대상이 실제로 존재하는지 발송 직전 재확인한다.
    verify_target(api, candidate.id)
    # preflight GET 사이에 다른 경로가 PAUSE를 만들었을 수 있으므로 POST 직전에 다시 확인한다.
    if PAUSE_PATH.exists():
        raise PublishHeld("paused_before_post", status=409)
    try:
        j = api.post("me/threads", {"media_type": "TEXT", "text": text,
                                    "reply_to_id": candidate.id, "auto_publish_text": "true"})
    except requests.RequestException as exc:
        pause("reply_publish_request_uncertain", {"expected": candidate.id, "error": str(exc)})
        raise UncertainPublish("", str(exc)) from exc
    except APIError as exc:
        # 파싱 가능한 JSON 4xx만 서버의 명시적 거부로 확정한다. non-JSON 4xx/5xx/상태불명은
        # 서버가 이미 썼을 가능성을 배제할 수 없어 UNKNOWN으로 잠근다.
        if (exc.status is not None and 400 <= int(exc.status) < 500
                and exc.response_json_valid is True):
            raise
        pause("reply_publish_api_uncertain", {"expected": candidate.id, "status": exc.status,
                                              "json_valid": exc.response_json_valid,
                                              "error": str(exc)})
        raise UncertainPublish("", str(exc)) from exc
    rid = str(j.get("id") or "")
    if not rid:
        detail = f"reply publish returned no id: {safe_error_payload(j)}"
        pause("reply_publish_id_uncertain", {"expected": candidate.id, "error": detail})
        raise UncertainPublish("", detail)
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
    except (APIError, requests.RequestException) as e:
        # POST는 이미 성공했을 수 있다. 재시도하면 중복 발송 위험이 있으므로 UNKNOWN으로 잠근다.
        pause("reply_verification_uncertain", {"expected": candidate.id, "reply_id": rid, "error": str(e)})
        raise UncertainPublish(rid, str(e)) from e
    return verified


def can_send_external(cfg: dict[str, Any], state: dict[str, Any], username: str,
                      now: dt.datetime | None = None) -> bool:
    b = today_bucket(state, now)
    if b.get("total", 0) >= int(cfg.get("total_daily_cap", 30)):
        return False
    if b.get("external", 0) >= effective_external_daily_cap(cfg, state, now):
        return False
    if (b.get("per_target") or {}).get(username.lower(), 0) >= int(cfg.get("per_target_daily_cap", 1)):
        return False
    return True


def can_send_inbound(cfg: dict[str, Any], state: dict[str, Any]) -> bool:
    b = today_bucket(state)
    return (b.get("total", 0) < int(cfg.get("total_daily_cap", 10)) and
            b.get("inbound", 0) + b.get("nested", 0) < int(cfg.get("inbound_daily_cap", 8)))


def public_saju_required_delay_minutes(candidate: Candidate, cfg: dict[str, Any]) -> int:
    """공개 생년월일 사주 댓글은 즉답하지 않고 사람다운 검토 시간을 둔다.

    지연값은 댓글 ID에서 결정적으로 계산해 재실행 때도 바뀌지 않는다.
    일반 댓글/대화는 기존 응답 속도를 유지한다.
    """
    if candidate.kind == "external" or public_birth_detail is None:
        return 0
    try:
        if not public_birth_detail(candidate.text):
            return 0
    except Exception:
        return 0
    lo = max(0, int(cfg.get("public_saju_reply_min_delay_minutes", 5)))
    hi = max(lo, int(cfg.get("public_saju_reply_max_delay_minutes", 5)))
    if hi == lo:
        return lo
    seed = int(hashlib.sha256((candidate.id + "|public-saju-delay").encode("utf-8")).hexdigest()[:8], 16)
    return lo + (seed % (hi - lo + 1))


def public_saju_ready(candidate: Candidate, cfg: dict[str, Any]) -> tuple[bool, int, int]:
    required = public_saju_required_delay_minutes(candidate, cfg)
    if required <= 0:
        return True, 0, int(age_hours(candidate.timestamp) * 60)
    age_min = int(age_hours(candidate.timestamp) * 60)
    return age_min >= required, required, age_min


def inbound_inter_reply_pause_seconds(candidate: Candidate, cfg: dict[str, Any]) -> int:
    """한 실행에서 여러 공개풀이가 초 단위로 연속 발행되는 패턴을 피한다."""
    if public_birth_detail is None:
        return 0
    try:
        if not public_birth_detail(candidate.text):
            return 0
    except Exception:
        return 0
    lo = max(0, int(cfg.get("public_saju_inter_reply_min_seconds", 70)))
    hi = max(lo, int(cfg.get("public_saju_inter_reply_max_seconds", 150)))
    if hi == lo:
        return lo
    seed = int(hashlib.sha256((candidate.id + "|public-saju-gap").encode("utf-8")).hexdigest()[:8], 16)
    return lo + (seed % (hi - lo + 1))


def record_send(state: dict[str, Any], candidate: Candidate, text: str, reply: dict[str, Any], *,
                dry_run: bool, now: dt.datetime | None = None, effect: str = "CONFIRMED") -> None:
    if dry_run:
        return
    now = now or utcnow()
    b = today_bucket(state, now)
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
        "at": now.isoformat(), "date_kst": date_key(now), "kind": candidate.kind,
        "target_id": candidate.id, "target_username": candidate.username,
        "reply_id": str(reply.get("id") or ""), "text_hash": text_hash(text), "text": text,
        "verified_replied_to": str((reply.get("replied_to") or {}).get("id") or ""),
        "source_query": candidate.source_query, "search_type": candidate.search_type,
        "candidate_score": round(float(candidate.score), 3), "relevance": int(candidate.relevance),
        "conversation_signal": round(float(candidate.conversation_signal), 3),
        "effect": str(effect or "CONFIRMED"),
    })


def reserve_send(state: dict[str, Any], candidate: Candidate, text: str, *,
                 now: dt.datetime | None = None, persist: bool = True) -> dict[str, Any]:
    """POST 전에 PENDING 예약을 저장해 crash/동시 실행 시 cap을 보수적으로 지킨다."""
    now = now or utcnow()
    record_send(state, candidate, text, {"id": "", "replied_to": {}},
                dry_run=False, now=now, effect="PENDING")
    row = state["sent"][-1]
    if persist:
        save_json(STATE_PATH, state)
    return row


def finalize_reserved_send(state: dict[str, Any], row: dict[str, Any], reply: dict[str, Any], *,
                           effect: str = "CONFIRMED", persist: bool = True) -> None:
    row["reply_id"] = str(reply.get("id") or row.get("reply_id") or "")
    row["verified_replied_to"] = str((reply.get("replied_to") or {}).get("id") or "")
    row["effect"] = str(effect or "CONFIRMED")
    row["finalized_at"] = utcnow().isoformat()
    if persist:
        save_json(STATE_PATH, state)


def release_reserved_send(state: dict[str, Any], row: dict[str, Any], *, persist: bool = True) -> None:
    """POST가 확실히 일어나지 않은 경우에만 PENDING 예약을 되돌린다."""
    if row.get("effect") != "PENDING":
        return
    key = str(row.get("date_kst") or date_key())
    b = day_bucket(state, key)
    kind = str(row.get("kind") or "")
    b["total"] = max(0, int(b.get("total", 0)) - 1)
    if kind == "external":
        b["external"] = max(0, int(b.get("external", 0)) - 1)
        author = str(row.get("target_username") or "").lower()
        pt = b.setdefault("per_target", {})
        if author in pt:
            pt[author] = max(0, int(pt.get(author, 0)) - 1)
            if pt[author] == 0:
                pt.pop(author, None)
        tid = str(row.get("target_id") or "")
        ids = state.setdefault("external_target_ids", [])
        for i in range(len(ids) - 1, -1, -1):
            if str(ids[i]) == tid:
                ids.pop(i)
                break
    elif kind in {"inbound", "nested"}:
        b[kind] = max(0, int(b.get(kind, 0)) - 1)
        tid = str(row.get("target_id") or "")
        ids = state.setdefault("handled_inbound_ids", [])
        for i in range(len(ids) - 1, -1, -1):
            if str(ids[i]) == tid:
                ids.pop(i)
                break
    sent = state.setdefault("sent", [])
    try:
        sent.remove(row)
    except ValueError:
        pass
    if persist:
        save_json(STATE_PATH, state)


def pending_sends(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [x for x in state.get("sent", []) if x.get("effect") == "PENDING"]


def unresolved_sends(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [x for x in state.get("sent", []) if x.get("effect") in {"PENDING", "UNKNOWN"}]


def record_external_error(state: dict[str, Any], *, safety_stop: bool = False,
                          now: dt.datetime | None = None) -> None:
    b = today_bucket(state, now)
    b["external_errors"] = int(b.get("external_errors", 0)) + 1
    if safety_stop:
        b["external_safety_stops"] = int(b.get("external_safety_stops", 0)) + 1


def record_external_insights(state: dict[str, Any], sent_row: dict[str, Any], metrics: dict[str, Any], *,
                             now: dt.datetime | None = None) -> None:
    """한 외부 댓글의 누적 insights를 원 발송일 버킷에 멱등 반영한다."""
    if sent_row.get("kind") != "external":
        return
    now = now or utcnow()
    send_key = str(sent_row.get("date_kst") or "")
    if not send_key:
        ts = parse_ts(str(sent_row.get("at") or ""))
        send_key = date_key(ts or now)
    b = day_bucket(state, send_key)
    names = ("views", "likes", "replies", "reposts", "quotes", "shares")
    reported = {name: max(0, int(float(metrics.get(name, 0) or 0))) for name in names}
    previous = sent_row.get("external_metrics") if isinstance(sent_row.get("external_metrics"), dict) else None
    previous = previous or {}
    # Threads 집계값이 일시적으로 감소해도 누적 학습치는 되돌리지 않는다.
    current = {name: max(int(previous.get(name, 0) or 0), reported[name]) for name in names}
    if not sent_row.get("external_metrics_measured"):
        b["external_measured"] = int(b.get("external_measured", 0)) + 1
        sent_row["external_metrics_measured"] = True
    old_engaged = bool(sent_row.get("external_engagement_counted"))
    new_engaged = sum(current[x] for x in ("likes", "replies", "reposts", "quotes", "shares")) > 0
    if new_engaged and not old_engaged:
        b["external_engaged"] = int(b.get("external_engaged", 0)) + 1
        sent_row["external_engagement_counted"] = True
    old_replies = int(previous.get("replies", 0) or 0)
    old_likes = int(previous.get("likes", 0) or 0)
    b["external_replies"] = int(b.get("external_replies", 0)) + max(0, current["replies"] - old_replies)
    b["external_likes"] = int(b.get("external_likes", 0)) + max(0, current["likes"] - old_likes)
    sent_row["external_metrics"] = current
    sent_row["insights_checked_at"] = now.isoformat()




def _metric_value(item: dict[str, Any]) -> int | None:
    missing = object()
    raw: Any = missing
    values = item.get("values")
    if isinstance(values, list) and values and isinstance(values[-1], dict) and "value" in values[-1]:
        raw = values[-1].get("value")
    elif isinstance(item.get("total_value"), dict) and "value" in (item.get("total_value") or {}):
        raw = (item.get("total_value") or {}).get("value")
    elif "value" in item:
        raw = item.get("value")
    if raw is missing or raw is None or isinstance(raw, bool):
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value) or value < 0:
        return None
    return int(value)


def record_external_insight_failure(state: dict[str, Any], row: dict[str, Any]) -> None:
    if row.get("external_insight_failure_counted"):
        return
    key = str(row.get("date_kst") or date_key(parse_ts(str(row.get("at") or "")) or utcnow()))
    b = day_bucket(state, key)
    b["external_insight_failures"] = int(b.get("external_insight_failures", 0)) + 1
    row["external_insight_failure_counted"] = True


def clear_external_insight_failure(state: dict[str, Any], row: dict[str, Any]) -> None:
    if not row.get("external_insight_failure_counted"):
        return
    key = str(row.get("date_kst") or date_key(parse_ts(str(row.get("at") or "")) or utcnow()))
    b = day_bucket(state, key)
    b["external_insight_failures"] = max(0, int(b.get("external_insight_failures", 0)) - 1)
    row["external_insight_failure_counted"] = False


def collect_external_insights(api: ThreadsAPI, cfg: dict[str, Any], state: dict[str, Any], *,
                              now: dt.datetime | None = None) -> dict[str, int]:
    """최근 외부 댓글의 공식 insights만 제한적으로 읽어 다음 후보/단계 판단에 쓴다."""
    now = now or utcnow()
    min_age = float(cfg.get("external_insights_min_age_hours", 2))
    refresh = float(cfg.get("external_insights_refresh_hours", 12))
    max_age = float(cfg.get("external_insights_max_age_days", 8)) * 24
    limit = max(0, int(cfg.get("external_insights_per_run", 8)))
    result = {"attempted": 0, "measured": 0, "failed": 0, "skipped": 0}
    for row in reversed(state.get("sent", [])):
        if result["attempted"] >= limit:
            break
        if row.get("kind") != "external":
            continue
        reply_id = str(row.get("reply_id") or "")
        sent_at = parse_ts(str(row.get("at") or ""))
        if not reply_id or reply_id == "dry" or sent_at is None:
            result["skipped"] += 1
            continue
        if sent_at.tzinfo is None:
            sent_at = sent_at.replace(tzinfo=dt.timezone.utc)
        age = max(0.0, (now - sent_at.astimezone(dt.timezone.utc)).total_seconds() / 3600)
        if age < min_age or age > max_age:
            result["skipped"] += 1
            continue
        checked = parse_ts(str(row.get("insights_checked_at") or ""))
        if checked is not None:
            if checked.tzinfo is None:
                checked = checked.replace(tzinfo=dt.timezone.utc)
            if (now - checked.astimezone(dt.timezone.utc)).total_seconds() / 3600 < refresh:
                result["skipped"] += 1
                continue
        result["attempted"] += 1
        try:
            payload = api.get(f"{reply_id}/insights", {
                "metric": "views,likes,replies,reposts,quotes,shares"
            })
        except (APIError, requests.RequestException) as exc:
            # 성과 측정은 학습용 보조 경로다. 오류는 발송을 막지 않되 승급 신뢰도에는 반영한다.
            result["failed"] += 1
            record_external_insight_failure(state, row)
            log(f"외부댓글 insights 건너뜀 {reply_id}: {exc}")
            row["insights_checked_at"] = now.isoformat()
            continue
        metrics = {name: 0 for name in ("views", "likes", "replies", "reposts", "quotes", "shares")}
        seen_metrics: set[str] = set()
        invalid_metrics: set[str] = set()
        for item in payload.get("data", []) if isinstance(payload, dict) else []:
            name = str(item.get("name") or "")
            if name in metrics:
                value = _metric_value(item)
                if value is None:
                    invalid_metrics.add(name)
                else:
                    metrics[name] = value
                    seen_metrics.add(name)
        required = {"views", "likes", "replies"}
        if invalid_metrics or not required.issubset(seen_metrics):
            result["failed"] += 1
            record_external_insight_failure(state, row)
            row["insights_checked_at"] = now.isoformat()
            log(f"외부댓글 insights 무효/부분 응답 {reply_id}: seen={sorted(seen_metrics)} invalid={sorted(invalid_metrics)}")
            continue
        clear_external_insight_failure(state, row)
        record_external_insights(state, row, metrics, now=now)
        result["measured"] += 1
    return result


def mark_inbound_handled(state: dict[str, Any], cid: str) -> None:
    state.setdefault("handled_inbound_ids", []).append(cid)


def run_growth(api: ThreadsAPI, cfg: dict[str, Any], state: dict[str, Any], caps: dict[str, Any],
               *, send: bool, do_external: bool, do_inbound: bool) -> dict[str, Any]:
    actions: list[dict[str, Any]] = []
    publisher_backend = str(cfg.get("publisher_backend", "api")).lower()
    hold_reason = ""
    if send and publisher_backend != "api":
        hold_reason = "publisher_backend_not_api"
        log(f"HOLD: Threads 성장 자동화는 공식 API 발송만 허용합니다 (backend={publisher_backend})")
        send = False
    if PAUSE_PATH.exists() and send:
        p = load_json(PAUSE_PATH, {})
        log(f"PAUSED 파일 존재 — 실제 발송 안 함: {p.get('reason')}")
        send = False
    unknown = [x for x in state.get("sent", []) if x.get("effect") == "UNKNOWN"]
    if send and unknown:
        hold_reason = "unresolved_send_requires_reconcile"
        log("HOLD: 이전 UNKNOWN 발송이 남아 있어 근거 기반 확인 전 자동발송을 차단합니다")
        send = False
        do_external = False
        do_inbound = False
    elif send and pending_sends(state):
        hold_reason = "pending_send_requires_reconcile"
        log("HOLD: 이전 PENDING 발송이 남아 있어 자동 재시도를 차단합니다")
        send = False
        do_external = False
        do_inbound = False
    # PAUSE/PENDING 판정 뒤에 계산해야 정지 상태에서 실제 API 발송이 새지 않는다.
    api_send = bool(send and publisher_backend == "api")

    growth_state = _growth_state(state)
    growth_status = {
        "stage_index": int(growth_state.get("stage_index", 0)),
        "daily_cap": effective_external_daily_cap(cfg, state),
        "promoted": False,
    }
    insight_status = {"attempted": 0, "measured": 0, "failed": 0, "skipped": 0}
    telemetry_available = "threads_manage_insights" in set(caps.get("token_scopes") or [])
    if do_external and send and telemetry_available:
        insight_status = collect_external_insights(api, cfg, state)
    if do_external and not PAUSE_PATH.exists():
        growth_status = maybe_advance_external_stage(cfg, state, telemetry_available=telemetry_available)
        if growth_status.get("promoted"):
            log(f"외부 대화 단계 승급 → 일 {growth_status.get('daily_cap')}개")

    # 1) 내 글 댓글/대댓글 우선. 이미 들어온 사람과 대화를 이어가는 게 가장 안전하다.
    if do_inbound and caps.get("read_replies"):
        try:
            candidates = inbound_candidates(api, cfg, state)
            if cfg.get("_birth_only"):
                candidates = [
                    x for x in candidates
                    if public_birth_detail is not None and public_birth_detail(x.text)
                ]
            root_contains = str(os.environ.get("PUBLIC_SAJU_ROOT_TEXT_CONTAINS", "")).strip()
            if root_contains:
                candidates = [x for x in candidates if root_contains in (x.root_text or "")]
            start_raw = str(os.environ.get("PUBLIC_SAJU_COMMENT_START_UTC", "")).strip()
            cutoff_raw = str(os.environ.get("PUBLIC_SAJU_COMMENT_CUTOFF_UTC", "")).strip()
            start_dt = parse_ts(start_raw) if start_raw else None
            cutoff_dt = parse_ts(cutoff_raw) if cutoff_raw else None
            if start_dt or cutoff_dt:
                kept = []
                for x in candidates:
                    ts = parse_ts(x.timestamp)
                    if ts is None:
                        continue
                    ts = ts if ts.tzinfo else ts.replace(tzinfo=dt.timezone.utc)
                    ts = ts.astimezone(dt.timezone.utc)
                    if start_dt is not None:
                        s = start_dt if start_dt.tzinfo else start_dt.replace(tzinfo=dt.timezone.utc)
                        if ts < s.astimezone(dt.timezone.utc):
                            continue
                    if cutoff_dt is not None:
                        z = cutoff_dt if cutoff_dt.tzinfo else cutoff_dt.replace(tzinfo=dt.timezone.utc)
                        if ts > z.astimezone(dt.timezone.utc):
                            continue
                    kept.append(x)
                candidates = kept
        except (CandidateScanError, APIError, requests.RequestException) as e:
            candidates = []
            if send and not hold_reason:
                hold_reason = "inbound_scan_error"
            do_external = False
            log(f"inbound scan 실패 — 추가 발송 차단: {e}")
        n = 0
        for c in candidates:
            if n >= int(cfg.get("inbound_per_run", 3)) or not can_send_inbound(cfg, state):
                break
            ready, required_delay, age_min = public_saju_ready(c, cfg)
            if not ready:
                log(f"공개사주 답변 대기 @{c.username}: 댓글 {age_min}분 경과 / 목표 {required_delay}분")
                continue
            text = generate_reply(c, cfg, state)
            if not text:
                # 같은 댓글을 다음 실행마다 무한 재시도하지 않게 품질 실패도 처리완료로 기록
                mark_inbound_handled(state, c.id)
                continue
            text, revenue_cta = maybe_add_revenue_cta(text, c, cfg, state)
            log(f"{('[SEND]' if api_send else '[DRY]')} {c.kind} @{c.username}: {text}")
            reply = {"id": "dry", "replied_to": {"id": c.id}}
            reservation = None
            if api_send:
                # 같은 실행에서 공개사주 답글이 연달아 몇 초 간격으로 달리지 않도록 간격을 둔다.
                if n > 0:
                    pause_s = inbound_inter_reply_pause_seconds(c, cfg)
                    if pause_s > 0:
                        log(f"공개사주 연속답글 간격 {pause_s}초")
                        time.sleep(pause_s)
                if PAUSE_PATH.exists():
                    log("PAUSED 감지 — 추가 발송 중단")
                    break
                reservation = reserve_send(state, c, text, persist=True)
                reservation["revenue_cta"] = bool(revenue_cta)
                save_json(STATE_PATH, state)
                if PAUSE_PATH.exists():
                    release_reserved_send(state, reservation, persist=True)
                    log("PAUSED 감지 — 예약 취소 후 발송 중단")
                    break
                try:
                    reply = publish_reply(api, c, text)
                except UncertainPublish as e:
                    if not PAUSE_PATH.exists():
                        pause("reply_verification_uncertain", {"expected": c.id, "reply_id": e.reply_id, "error": str(e)})
                    finalize_reserved_send(state, reservation, {"id": e.reply_id, "replied_to": {}}, effect="UNKNOWN", persist=True)
                    log(f"발송 불확실({c.kind}) — 전체 실행 정지: {e}")
                    break
                except LocationMismatch as e:
                    if not PAUSE_PATH.exists():
                        pause("reply_location_mismatch", {"expected": c.id, "reply_id": e.reply_id, "error": str(e)})
                    finalize_reserved_send(state, reservation, {"id": e.reply_id, "replied_to": {}}, effect="UNKNOWN", persist=True)
                    log(f"발송 위치 불일치({c.kind}) — 전체 실행 정지: {e}")
                    break
                except (APIError, requests.RequestException) as e:
                    release_reserved_send(state, reservation, persist=True)
                    hold_reason = "inbound_publish_error"
                    log(f"발송 실패({c.kind}): {e}")
                    break
                finalize_reserved_send(state, reservation, reply, effect="CONFIRMED", persist=True)
            actions.append({"kind": c.kind, "target": c.id, "username": c.username,
                            "text": text, "sent": bool(api_send), "ui_required": False, "revenue_cta": bool(revenue_cta)})
            n += 1

    # 2) 외부 큰 계정 댓글. 실행 도중 PAUSE가 생기면 외부 단계로 절대 넘어가지 않는다.
    if PAUSE_PATH.exists():
        do_external = False
    if do_external and (caps.get("profile_posts") or caps.get("keyword_search")):
        try:
            candidates = external_candidates(api, cfg, state, caps)
        except (CandidateScanError, APIError, requests.RequestException) as e:
            candidates = []
            # CandidateScanError 내부에서 이미 오류를 카운트했다면 이중 카운트하지 않는다.
            if not isinstance(e, CandidateScanError):
                record_external_error(state)
            if send and not hold_reason:
                hold_reason = "external_scan_error"
            log(f"external scan 실패 — 이번 실행 발송 없음: {e}")
        n = 0
        for c in candidates:
            if n >= int(cfg.get("external_per_run", 1)):
                break
            if not can_send_external(cfg, state, c.username):
                continue
            text = generate_reply(c, cfg, state)
            if not text:
                continue
            ok, reason = quality_gate(text, cfg, state, external=True)
            if not ok:
                log(f"외부 댓글 발송경계 차단 @{c.username}: {reason}")
                continue
            log(f"{('[SEND]' if api_send else '[DRY]')} external @{c.username}: {text}")
            reply = {"id": "dry", "replied_to": {"id": c.id}}
            reservation = None
            if api_send:
                if PAUSE_PATH.exists():
                    log("PAUSED 감지 — 외부 발송 중단")
                    break
                reservation = reserve_send(state, c, text, persist=True)
                if PAUSE_PATH.exists():
                    release_reserved_send(state, reservation, persist=True)
                    log("PAUSED 감지 — 외부 예약 취소 후 중단")
                    break
                try:
                    reply = publish_reply(api, c, text)
                except UncertainPublish as e:
                    if not PAUSE_PATH.exists():
                        pause("reply_verification_uncertain", {"expected": c.id, "reply_id": e.reply_id, "error": str(e)})
                    finalize_reserved_send(state, reservation, {"id": e.reply_id, "replied_to": {}}, effect="UNKNOWN", persist=True)
                    record_external_error(state, safety_stop=True)
                    save_json(STATE_PATH, state)
                    log(f"외부 댓글 발송 불확실 — 전체 실행 정지: {e}")
                    break
                except LocationMismatch as e:
                    if not PAUSE_PATH.exists():
                        pause("reply_location_mismatch", {"expected": c.id, "reply_id": e.reply_id, "error": str(e)})
                    finalize_reserved_send(state, reservation, {"id": e.reply_id, "replied_to": {}}, effect="UNKNOWN", persist=True)
                    record_external_error(state, safety_stop=True)
                    save_json(STATE_PATH, state)
                    log(f"외부 댓글 위치 불일치 — 전체 실행 정지: {e}")
                    break
                except (APIError, requests.RequestException) as e:
                    release_reserved_send(state, reservation, persist=True)
                    record_external_error(state, safety_stop=False)
                    save_json(STATE_PATH, state)
                    hold_reason = "external_publish_error"
                    log(f"외부 댓글 발송 실패: {e}")
                    break
                finalize_reserved_send(state, reservation, reply, effect="CONFIRMED", persist=True)
            actions.append({"kind": "external", "target": c.id, "username": c.username,
                            "permalink": c.permalink, "timestamp": c.timestamp, "text": text,
                            "sent": bool(api_send), "ui_required": False,
                            "source_query": c.source_query, "search_type": c.search_type,
                            "candidate_score": round(float(c.score), 3)})
            n += 1
    elif do_external:
        log("외부댓글 기능은 공식 profile_posts/keyword_search 권한이 없어 비활성 상태")

    state["last_run_at"] = utcnow().isoformat()
    trim_state(state)
    if send:
        save_json(STATE_PATH, state)
    return {"at": utcnow().isoformat(), "date_kst": date_key(), "send": send,
            "capabilities": {k: v for k, v in caps.items() if k != "errors"},
            "actions": actions, "day": today_bucket(state), "paused": PAUSE_PATH.exists(),
            "external_growth": growth_status, "external_insights": insight_status,
            "hold_reason": hold_reason}


def write_report(result: dict[str, Any], caps: dict[str, Any]) -> None:
    lines = [
        f"# Threads 성장 자동화 보고 — {result['date_kst']}", "",
        f"- 실행: {'실제 발송' if result.get('send') else '드라이런/점검'}",
        f"- PAUSED: {result.get('paused')}",
        f"- 오늘 카운트: `{json.dumps(result.get('day', {}), ensure_ascii=False)}`",
        f"- 외부 대화 단계: `{json.dumps(result.get('external_growth', {}), ensure_ascii=False)}`",
        f"- 외부 댓글 성과측정: `{json.dumps(result.get('external_insights', {}), ensure_ascii=False)}`",
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
    ap.add_argument("--birth-only", action="store_true", help="생년월일이 공개된 댓글만 자동답변")
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
    cfg["_birth_only"] = bool(a.birth_only)
    event_cap = os.environ.get("PUBLIC_SAJU_EVENT_CAP", "").strip()
    if event_cap.isdigit():
        cap = max(1, int(event_cap))
        cfg["inbound_daily_cap"] = cap
        cfg["total_daily_cap"] = cap
    event_per_run = os.environ.get("PUBLIC_SAJU_PER_RUN", "").strip()
    if event_per_run.isdigit():
        cfg["inbound_per_run"] = max(1, min(6, int(event_per_run)))

    api = ThreadsAPI(tok)
    caps = api_capabilities(api, cfg)
    log("capabilities: " + json.dumps({k: v for k, v in caps.items() if k != "errors"}, ensure_ascii=False))

    def _load_or_fail() -> dict[str, Any] | None:
        try:
            return load_state()
        except StateCorruption as exc:
            pause("state_corrupt", {"error": str(exc)})
            log(f"[FAIL] Threads 상태파일 손상 — 자동발송 차단: {exc}")
            return None

    if not caps.get("basic"):
        state = _load_or_fail()
        if state is None:
            return 6
        write_report({"date_kst": date_key(), "send": False, "day": today_bucket(state),
                      "actions": [], "paused": PAUSE_PATH.exists()}, caps)
        return 3

    if a.preflight:
        state = _load_or_fail()
        if state is None:
            return 6
        write_report({"date_kst": date_key(), "send": False, "day": today_bucket(state),
                      "actions": [], "paused": PAUSE_PATH.exists()}, caps)
        return 0

    if a.send:
        try:
            # LIVE에서는 반드시 writer lock을 먼저 잡고 그 안에서 최신 상태를 읽는다.
            # lock은 run_growth의 최종 state persistence와 report 작성까지 유지한다.
            with writer_lock():
                state = _load_or_fail()
                if state is None:
                    return 6
                result = run_growth(api, cfg, state, caps, send=True,
                                    do_external=not a.no_external, do_inbound=not a.no_inbound)
                write_report(result, caps)
                if result.get("paused") or result.get("hold_reason"):
                    return 8
                return 0
        except WriterLockBusy as exc:
            log(f"HOLD: {exc}")
            return 7
        except LocationMismatch as exc:
            log(str(exc))
            return 5

    state = _load_or_fail()
    if state is None:
        return 6
    result = run_growth(api, cfg, state, caps, send=False,
                        do_external=not a.no_external, do_inbound=not a.no_inbound)
    write_report(result, caps)
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    raise SystemExit(main())
