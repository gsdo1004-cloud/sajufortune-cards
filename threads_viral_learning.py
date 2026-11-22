# -*- coding: utf-8 -*-
"""Threads Viral Learning Engine.

내 계정의 실제 Threads insights + 발행 원문을 결합해 잘 먹힌 '구조'만 학습한다.
원문 복제는 하지 않는다. 외부 샘플은 threads_viral_samples.jsonl 로 선택적으로 받는다.

CLI:
  py -3 threads_viral_learning.py --learn
  py -3 threads_viral_learning.py --report
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import re
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

BASE = Path(__file__).resolve().parent
INSIGHTS = BASE / "threads_insights.json"
AI_LOG = BASE / "ai_news_posted.json"
MODEL = BASE / "threads_viral_model.json"
SAMPLES = BASE / "threads_viral_samples.jsonl"

HOOK_TYPES = {
    "question": ["?", "왜 ", "어떻게 ", "혹시 ", "너라면", "당신이라면"],
    "contrast": ["그런데", "하지만", "반대로", "오히려", "아닌", "보다", "반반"],
    "risk_gain": ["돈", "가격", "무료", "월급", "연봉", "일자리", "밥그릇", "손해", "이득", "몸값"],
    "number": ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"],
    "personal": ["나는", "내가", "내 ", "우리", "살면서", "보니", "느꼈"],
    "curiosity": ["사실", "이상하게", "의외", "생각보다", "정작", "결국", "먼저"],
}
TOPIC_WORDS = [
    "챗GPT", "ChatGPT", "GPT", "제미나이", "Gemini", "클로드", "Claude", "AI", "인공지능",
    "사주", "운세", "타로", "심리", "관계", "돈", "가격", "무료", "직장", "일자리", "건강",
    "부모", "자녀", "노후", "학교", "취업", "월급", "연봉", "로봇", "유튜브", "브라우저",
]
BANNED = ["100%", "무조건", "반드시", "보장", "확실히", "절대"]


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"https?://\S+", "", s or "")).strip()


def features(text: str) -> dict:
    t = _norm(text)
    lines = [x.strip() for x in t.splitlines() if x.strip()]
    first = lines[0] if lines else t
    return {
        "chars": len(t),
        "lines": len(lines),
        "question": "?" in t,
        "question_end": t.endswith("?"),
        "first_chars": len(first),
        "hook_types": [k for k, needles in HOOK_TYPES.items() if any(n.lower() in first.lower() for n in needles)],
        "topics": [w for w in TOPIC_WORDS if w.lower() in t.lower()],
        "source_quote": bool(re.search(r"\[[^\]]{2,20}\]", t)),
    }


def _near24(snaps: list[dict]) -> dict | None:
    cand = [s for s in snaps if s.get("age_h") is not None and s.get("age_h", 0) >= 12]
    return min(cand, key=lambda s: abs(float(s.get("age_h", 999)) - 24)) if cand else None


def engagement_score(s: dict) -> float:
    """작은 계정에서도 0/1 반응 차이를 학습하도록 rate + log views 혼합."""
    v = max(1, int(s.get("views") or 0))
    likes = int(s.get("likes") or 0)
    replies = int(s.get("replies") or 0)
    reposts = int(s.get("reposts") or 0)
    quotes = int(s.get("quotes") or 0)
    shares = int(s.get("shares") or 0)
    rate = (likes * 1.0 + replies * 3.5 + reposts * 3.0 + quotes * 2.5 + shares * 2.0) / v
    return round(math.log1p(v) * 10.0 + rate * 100.0, 4)


def _texts_by_id() -> dict[str, str]:
    d = _load(AI_LOG, {})
    return {str(x.get("post_id")): x.get("text", "") for x in d.get("log", []) if x.get("post_id")}


def _external_rows() -> list[dict]:
    out = []
    if not SAMPLES.exists():
        return out
    for ln in SAMPLES.read_text(encoding="utf-8").splitlines():
        try:
            x = json.loads(ln)
            if x.get("text") and x.get("score") is not None:
                out.append({"text": x["text"], "score": float(x["score"]), "source": "external"})
        except Exception:
            pass
    return out


def learn() -> dict:
    ins = _load(INSIGHTS, {"posts": {}})
    texts = _texts_by_id()
    rows = []
    for pid, rec in (ins.get("posts") or {}).items():
        text = texts.get(str(pid)) or rec.get("head") or ""
        snap = _near24(rec.get("snapshots") or [])
        if not text or not snap:
            continue
        rows.append({"post_id": str(pid), "channel": rec.get("channel", "?"), "text": text,
                     "score": engagement_score(snap), "views": snap.get("views", 0),
                     "likes": snap.get("likes", 0), "replies": snap.get("replies", 0),
                     "features": features(text)})
    rows.extend({**r, "features": features(r["text"])} for r in _external_rows())

    buckets: dict[str, list[float]] = defaultdict(list)
    topics: dict[str, list[float]] = defaultdict(list)
    lengths: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        f = r["features"]
        for h in f["hook_types"] or ["plain"]:
            buckets[h].append(r["score"])
        for w in f["topics"]:
            topics[w].append(r["score"])
        n = f["chars"]
        band = "short" if n < 140 else "medium" if n < 280 else "long"
        lengths[band].append(r["score"])

    def avgmap(d):
        return {k: {"n": len(v), "avg": round(sum(v) / len(v), 3)} for k, v in d.items() if v}

    ranked = sorted(rows, key=lambda x: x["score"], reverse=True)
    model = {
        "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "sample_count": len(rows),
        "hook_types": avgmap(buckets),
        "topics": avgmap(topics),
        "length_bands": avgmap(lengths),
        "top_examples": [
            {"post_id": r.get("post_id", ""), "score": r["score"], "views": r.get("views"),
             "replies": r.get("replies"), "features": r["features"],
             "preview": _norm(r["text"])[:180]} for r in ranked[:8]
        ],
    }
    MODEL.write_text(json.dumps(model, ensure_ascii=False, indent=2), encoding="utf-8")
    return model


def load_model() -> dict:
    m = _load(MODEL, {})
    return m if m.get("sample_count") else learn()


def _rank_items(d: dict, min_n: int = 2) -> list[tuple[str, float, int]]:
    arr = [(k, float(v.get("avg", 0)), int(v.get("n", 0))) for k, v in (d or {}).items() if int(v.get("n", 0)) >= min_n]
    return sorted(arr, key=lambda x: (x[1], x[2]), reverse=True)


def guidance() -> str:
    m = load_model()
    hooks = _rank_items(m.get("hook_types"), 2)[:3]
    topics = _rank_items(m.get("topics"), 2)[:5]
    lens = _rank_items(m.get("length_bands"), 2)[:2]
    h = ", ".join(x[0] for x in hooks) or "curiosity, question"
    t = ", ".join(x[0] for x in topics) or "생활에 직접 닿는 주제"
    l = ", ".join(x[0] for x in lens) or "medium"
    return (
        f"내 계정 실측 학습({m.get('sample_count', 0)}건): 성과가 상대적으로 좋은 훅={h}; "
        f"주제={t}; 길이={l}. 이 구조만 참고하고 과거 문장을 복사하지 마라. "
        "첫 문장은 자기관련성/호기심을 만들고 마지막은 구체적인 양자택일 질문으로 끝내라. "
        "연속글은 2~3편 이내로 각 편마다 독립적으로 유용한 정보를 담고, 같은 링크나 답글 요구를 반복하지 마라."
    )


def topic_bonus(title: str) -> float:
    m = load_model()
    score = 0.0
    low = title.lower()
    vals = [float(v.get("avg", 0)) for v in (m.get("topics") or {}).values() if v.get("n", 0)]
    baseline = (sum(vals) / len(vals)) if vals else 0.0
    for w, v in (m.get("topics") or {}).items():
        if w.lower() in low and int(v.get("n", 0)) >= 2:
            score += max(-2.0, min(4.0, (float(v.get("avg", 0)) - baseline) / 5.0))
    return round(score, 3)


def text_quality(text: str) -> float:
    f = features(text)
    m = load_model()
    score = 50.0
    if f["question_end"]: score += 10
    if f["question"]: score += 4
    if 90 <= f["chars"] <= 420: score += 8
    if 2 <= f["lines"] <= 9: score += 5
    if any(x in f["hook_types"] for x in ("curiosity", "contrast", "personal", "risk_gain")): score += 8
    if any(b in text for b in BANNED): score -= 30
    if "http" in text or "www." in text: score -= 12
    # learned hook lift, capped because samples are still small
    ranked = _rank_items(m.get("hook_types"), 2)
    if ranked:
        best = {x[0] for x in ranked[:2]}
        if best.intersection(f["hook_types"]): score += 5
    return round(max(0, min(100, score)), 1)


def similarity_guard(candidate: str, threshold: float = 0.78) -> tuple[bool, float]:
    """과거 고성과 문장을 그대로 베끼는 것을 막는다."""
    m = load_model()
    c = _norm(candidate)[:300]
    worst = 0.0
    for x in m.get("top_examples", []):
        p = _norm(x.get("preview", ""))[:300]
        if p:
            worst = max(worst, SequenceMatcher(None, c, p).ratio())
    return worst < threshold, round(worst, 3)



# Read-only selective adoption: never changes posting times, link placement, or permissions.
def _aware_timestamp(value):
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None else None
    except (ValueError, TypeError, OverflowError):
        return None


def publication_window(timestamp):
    """Publication-time observation bins in Korea Standard Time, not proven peak hours."""
    published = _aware_timestamp(timestamp)
    if published is None:
        return "unknown"
    h = published.astimezone(dt.timezone(dt.timedelta(hours=9))).hour
    if 6 <= h < 9:
        return "morning_06_09"
    if 12 <= h < 14:
        return "lunch_12_14"
    if 21 <= h < 24:
        return "evening_21_24"
    return "other"


def slot_evidence(insights, now=None, lookback_days=14, min_per_slot=5):
    """Compare age-matched 12-36h snapshots only. No schedule mutation or winner selection."""
    now = now or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    posts = (insights or {}).get("posts") or {}
    snapshots = [ts for rec in posts.values() for snap in (rec.get("snapshots") or [])
                 if (ts := _aware_timestamp(snap.get("t"))) is not None]
    latest = max(snapshots, default=None)
    if latest is None:
        return {"status": "HOLD_NO_INSIGHTS", "slots": {}}
    if latest > now + dt.timedelta(hours=1):
        return {"status": "HOLD_FUTURE_DATA", "slots": {}}
    if now - latest > dt.timedelta(days=3):
        return {"status": "HOLD_STALE", "latest_snapshot": latest.isoformat(), "slots": {}}
    buckets = defaultdict(list)
    for rec in posts.values():
        published = _aware_timestamp(rec.get("timestamp"))
        if published is None or published > now or published < now - dt.timedelta(days=lookback_days):
            continue
        snap = _near24(rec.get("snapshots") or [])
        if snap is None:
            continue
        try:
            age = float(snap.get("age_h"))
            views = float(snap.get("views") or 0)
            replies = float(snap.get("replies") or 0)
        except (TypeError, ValueError):
            continue
        if not (12 <= age <= 36) or views <= 0:
            continue
        key = (str(rec.get("channel") or "unknown"), publication_window(rec.get("timestamp")))
        buckets[key].append((views, replies))
    summary = {f"{channel}/{slot}": {
        "n": len(rows),
        "avg_views_24h": round(sum(v for v, _ in rows) / len(rows), 2),
        "replies_per_1k_views": round(1000 * sum(r for _, r in rows) / sum(v for v, _ in rows), 2)}
        for (channel, slot), rows in sorted(buckets.items())}
    # Comparisons require two time windows WITHIN the same channel.
    channel_slots = defaultdict(int)
    for (channel, _), rows in buckets.items():
        if len(rows) >= min_per_slot:
            channel_slots[channel] += 1
    enough = any(count >= 2 for count in channel_slots.values())
    return {"status": "OBSERVE_ONLY" if enough else "HOLD_LOW_SAMPLE",
            "latest_snapshot": latest.isoformat(), "slots": summary}


def link_placement_evidence(insights, conversion_events, min_per_arm=5):
    """Only independently tagged, first-party verified arm outcomes may be compared."""
    posts = (insights or {}).get("posts") or {}
    by_post = {}
    duplicate = set()
    for event in conversion_events or []:
        pid = str(event.get("post_id") or "")
        if not pid or event.get("source_verified") is not True:
            continue
        if pid in by_post:
            duplicate.add(pid)
        else:
            by_post[pid] = event
    stats = {"body": {"n": 0, "site_sessions": 0, "orders": 0},
             "comment": {"n": 0, "site_sessions": 0, "orders": 0}}
    for pid, rec in posts.items():
        arm = rec.get("link_placement")
        if arm not in stats or rec.get("placement_verified") is not True:
            continue
        event = by_post.get(str(pid))
        if event is None or str(pid) in duplicate:
            continue
        try:
            sessions = int(event.get("site_sessions"))
            orders = int(event.get("orders"))
        except (TypeError, ValueError):
            continue
        if sessions < 0 or orders < 0:
            continue
        stats[arm]["n"] += 1
        stats[arm]["site_sessions"] += sessions
        stats[arm]["orders"] += orders
    enough = all(x["n"] >= min_per_arm for x in stats.values())
    return {"status": "OBSERVE_ONLY" if enough else "HOLD_UNVERIFIED_ARMS",
            "arms": stats}


def selective_evidence_report(insights=None, conversion_events=None, now=None):
    insights = _load(INSIGHTS, {"posts": {}}) if insights is None else insights
    if conversion_events is None:
        conversion_events = []
        p = BASE / "threads_conversions.jsonl"
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                try:
                    conversion_events.append(json.loads(line))
                except (ValueError, TypeError):
                    continue
    slots = slot_evidence(insights, now=now)
    links = link_placement_evidence(insights, conversion_events)
    return f"Selective experiments: publication_slots={slots['status']}, link_placement={links['status']} (shadow/read-only)"


def report(m: dict | None = None) -> str:
    m = m or load_model()
    lines = [f"Threads viral model: {m.get('sample_count', 0)} samples", f"updated: {m.get('updated_at', '-')}"]
    for label, key in (("hooks", "hook_types"), ("topics", "topics"), ("lengths", "length_bands")):
        arr = _rank_items(m.get(key), 1)[:8]
        lines.append(label + ": " + ", ".join(f"{k}={a:.1f}(n{n})" for k, a, n in arr))
    lines.append("guidance: " + guidance())
    lines.append(selective_evidence_report())
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--learn", action="store_true")
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args()
    m = learn() if a.learn or not MODEL.exists() else load_model()
    print(report(m))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# ---- active zodiac-signal adapter -------------------------------------------------
def signal_caption(story: dict, fallback: str) -> str:
    """성과 모델이 충분할 때만 활성 signal 캡션을 압축·재구성한다.

    새로운 운세 사실을 만들지 않고 story에 이미 계산된 값만 재배열한다.
    표본이 적으면 기존 캡션을 그대로 반환한다.
    """
    m = load_model()
    # signal 실측이 최소 4건 쌓이기 전에는 다른 장르(AI 뉴스)의 문법을 억지로 이식하지 않는다.
    signal_n = 0
    ins = _load(INSIGHTS, {"posts": {}})
    for rec in (ins.get("posts") or {}).values():
        if str(rec.get("channel", "")).startswith("signal_") and _near24(rec.get("snapshots") or []):
            signal_n += 1
    if signal_n < 4:
        return fallback

    hooks = _rank_items(m.get("hook_types"), 2)
    preferred = hooks[0][0] if hooks else "curiosity"
    sign = story.get("sign_ko", "오늘")
    focus_label = story.get("focus_label", "오늘의 흐름")
    hook = story.get("hook", "")
    focus = story.get("focus", "")
    action = story.get("action", "")
    lucky = story.get("lucky", "")

    if preferred == "number":
        first = f"{sign}, 오늘 볼 건 딱 2가지. {focus_label}과 행동 하나."
    elif preferred == "contrast":
        first = f"{sign}, 오늘은 좋은 운·나쁜 운보다 어디에 힘을 쓸지가 더 중요해."
    elif preferred == "personal":
        first = f"{sign}라면 오늘 이 한 가지는 한번 체크해봐."
    else:
        first = hook or f"{sign}, 오늘 흐름에서 먼저 볼 신호가 있어."

    body = f"{focus_label}: {focus}\n오늘의 실천: {action}"
    if lucky:
        body += f"\n{lucky}"
    question = f"{sign}인 사람들, 오늘은 밀어붙이는 쪽이야 아니면 속도를 조절하는 쪽이야?"
    text = f"{first}\n\n{body}\n\n{question}"
    ok, _ = similarity_guard(text)
    return text if ok and text_quality(text) >= 62 else fallback
