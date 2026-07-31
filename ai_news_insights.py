# -*- coding: utf-8 -*-
"""쓰레드 발행글 성과 수집 (P0 — 측정 루프).

지금까지 이 계정은 **발행만 하고 성과를 한 번도 읽지 않았다.** 그래서 "AI 뉴스가
안 먹힌다"는 판단조차 체감일 뿐 데이터가 없었다. 이 스크립트가 그 자를 만든다.

같은 계정 안의 네 채널을 **같은 잣대로** 잰다 — 이게 핵심이다.
AI 뉴스만 재면 "낮다"의 기준이 없다. 운세 유령글·띠별 카드뉴스와 나란히 놓아야
"AI 글이 운세 글의 몇 %인가"를 말할 수 있다.

  ai_news   = ai_news_posted.json         (낮, AI 뉴스)
  ghost     = cards/{d}/threads_pub_ghost.json     (아침, 운세 유령글)
  carousel  = cards/{d}/threads_pub_carousel.json  (저녁, 띠별 카드뉴스)
  reels     = cards/{d}/threads_pub_reels.json     (저녁, 릴스)

사용법:
  python ai_news_insights.py              # 수집 + 리포트
  python ai_news_insights.py --report     # 저장된 것만 출력(API 호출 없음)
  python ai_news_insights.py --dry-run    # 대상만 나열
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

import requests

BASE = Path(__file__).resolve().parent
STORE = BASE / "threads_insights.json"     # 글별 성과 시계열
ACCOUNT = BASE / "threads_account.json"    # 계정 단위(팔로워·인구통계)

# 발행 코드(ai_news_threads.py)와 같은 호스트를 쓴다. 공식 문서는 graph.threads.com 이지만
# 현재 발행이 .net 으로 멀쩡히 돌고 있어 기본값은 .net 으로 두고, 실패하면 .com 으로 한 번 더 친다.
HOSTS = [
    os.environ.get("THREADS_GRAPH", "https://graph.threads.net/v1.0"),
    "https://graph.threads.com/v1.0",
]

METRICS = "views,likes,replies,reposts,quotes,shares"
MAX_AGE_DAYS = 14      # 이보다 오래된 글은 더 재지 않는다(수치가 굳는다)
MAX_POSTS = 60         # 한 번에 재는 글 수 상한 — 쿼터 폭주 방지
SNAP_MIN_GAP_H = 20    # 같은 글은 하루 한 번만 스냅샷


def log(m: str) -> None:
    print(m, flush=True)


def _get(path: str, params: dict) -> dict:
    """graph 호출. 첫 호스트가 죽으면 두 번째로 한 번 더 시도한다."""
    last = {}
    for host in HOSTS:
        try:
            r = requests.get(f"{host}/{path}", params=params, timeout=30)
            j = r.json()
        except Exception as e:                      # 네트워크·JSON 파싱 실패
            last = {"error": {"message": f"{type(e).__name__}: {e}"}}
            continue
        if "error" not in j:
            return j
        last = j
    return last


# ── 대상 수집 ────────────────────────────────────────────────
def targets() -> list[dict]:
    """발행 기록 파일들을 훑어 (post_id, channel) 목록을 만든다.

    ⚠️ 마커 중에는 실제 발행 없이 중복 방지용으로 선주입된 것이 섞여 있다
    (예: 'legacy-dawn-2026-07-21'). 숫자가 아닌 id 는 API 에 던지면 에러만 나므로 거른다.
    """
    out: list[dict] = []
    seen: set[str] = set()

    state = BASE / "ai_news_posted.json"
    if state.exists():
        d = json.loads(state.read_text(encoding="utf-8"))
        for e in d.get("log", []):
            pid = str(e.get("post_id") or "")
            if pid.isdigit() and pid not in seen:
                seen.add(pid)
                out.append({"post_id": pid, "channel": "ai_news",
                            "head": (e.get("text") or "")[:70]})

    for name, ch in (("threads_pub_ghost.json", "ghost"),
                     ("threads_pub_carousel.json", "carousel"),
                     ("threads_pub_reels.json", "reels")):
        for p in sorted((BASE / "cards").glob(f"*/{name}")):
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            pid = str(d.get("post_id") or "")
            if pid.isdigit() and pid not in seen:
                seen.add(pid)
                out.append({"post_id": pid, "channel": ch,
                            "head": (d.get("text") or "")[:70]})
    return out


# ── 저장소 ───────────────────────────────────────────────────
def load_store() -> dict:
    if STORE.exists():
        try:
            return json.loads(STORE.read_text(encoding="utf-8"))
        except Exception:
            log("[WARN] threads_insights.json 파손 — 새로 만듭니다")
    return {"posts": {}}


def save_store(d: dict) -> None:
    STORE.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def _parse_ts(s: str) -> dt.datetime | None:
    """Threads 는 '2026-07-27T04:55:10+0000' 형태로 준다."""
    if not s:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z"):
        try:
            return dt.datetime.strptime(s, fmt)
        except ValueError:
            pass
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def collect(tok: str, dry: bool = False) -> dict:
    store = load_store()
    posts = store.setdefault("posts", {})
    now = dt.datetime.now(dt.timezone.utc)
    todo = targets()
    log(f"[대상] 발행 기록에서 {len(todo)}건 확인")

    done = skip = fail = 0
    for t in reversed(todo):                       # 최근 것부터
        if done >= MAX_POSTS:
            log(f"[중단] 상한 {MAX_POSTS}건 도달 — 나머지는 다음 실행에서")
            break
        pid = t["post_id"]
        rec = posts.setdefault(pid, {"channel": t["channel"], "head": t["head"],
                                     "snapshots": []})
        if not rec.get("head"):
            rec["head"] = t["head"]

        # 1) 게시 시각은 API 가 준 timestamp 가 정본이다.
        #    발행 로그의 시각은 tz 가 없고, 카드뉴스 마커는 아예 시각이 없다.
        if not rec.get("timestamp") and not dry:
            j = _get(pid, {"fields": "timestamp,permalink", "access_token": tok})
            if "error" in j:
                fail += 1
                log(f"  [FAIL] {pid} meta: {str(j['error'])[:90]}")
                continue
            rec["timestamp"] = j.get("timestamp", "")
            rec["permalink"] = j.get("permalink", "")

        ts = _parse_ts(rec.get("timestamp", ""))
        age_h = (now - ts).total_seconds() / 3600 if ts else None

        if age_h is not None and age_h > MAX_AGE_DAYS * 24:
            rec["closed"] = True                   # 다 자란 글 — 더 안 잰다
            skip += 1
            continue

        snaps = rec["snapshots"]
        if snaps and age_h is not None:
            if age_h - snaps[-1].get("age_h", -999) < SNAP_MIN_GAP_H:
                skip += 1                          # 오늘 이미 쟀다
                continue

        if dry:
            log(f"  [DRY] {t['channel']:<9} {pid} age={age_h}")
            done += 1
            continue

        # 2) 성과 지표
        j = _get(f"{pid}/insights", {"metric": METRICS, "access_token": tok})
        if "error" in j:
            fail += 1
            log(f"  [FAIL] {pid} insights: {str(j['error'])[:90]}")
            continue

        snap = {"t": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "age_h": round(age_h, 1) if age_h is not None else None}
        for item in j.get("data", []):
            vals = item.get("values") or [{}]
            snap[item.get("name", "?")] = vals[0].get("value", 0)
        snaps.append(snap)
        done += 1
        log(f"  [OK] {rec['channel']:<9} age {snap['age_h']}h "
            f"views={snap.get('views', '-')} likes={snap.get('likes', '-')} "
            f"replies={snap.get('replies', '-')}")

    log(f"[수집] 신규 {done} / 스킵 {skip} / 실패 {fail}")
    if not dry:
        save_store(store)
    return store


# ── 계정 단위 ────────────────────────────────────────────────
def collect_account(tok: str, uid: str) -> None:
    """팔로워 수·연령·성별. **AI 글을 이 계정에 계속 둘지의 근거**가 된다.
    인구통계는 팔로워 100명 이상이라야 나온다 — 안 되면 조용히 넘어간다."""
    out = {"at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}

    j = _get(f"{uid}/threads_insights",
             {"metric": "followers_count", "access_token": tok})
    if "error" in j:
        log(f"[WARN] followers_count: {str(j['error'])[:90]}")
    else:
        for item in j.get("data", []):
            out[item.get("name", "?")] = item.get("total_value", {}).get("value")

    for bd in ("age", "gender", "country"):
        j = _get(f"{uid}/threads_insights",
                 {"metric": "follower_demographics", "breakdown": bd,
                  "access_token": tok})
        if "error" in j:
            log(f"[WARN] demographics({bd}): {str(j['error'])[:80]}")
            continue
        for item in j.get("data", []):
            tv = item.get("total_value", {})
            out[f"demo_{bd}"] = {r.get("dimension_values", ["?"])[0]: r.get("value")
                                 for r in tv.get("breakdowns", [{}])[0].get("results", [])}

    hist = []
    if ACCOUNT.exists():
        try:
            prev = json.loads(ACCOUNT.read_text(encoding="utf-8"))
            hist = prev.get("history", [])[-30:]
        except Exception:
            pass
    hist.append(out)
    ACCOUNT.write_text(json.dumps({"latest": out, "history": hist},
                                  ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"[계정] followers={out.get('followers_count', '?')} "
        f"연령분포={'있음' if 'demo_age' in out else '없음(팔로워 100명 미만이면 안 나옴)'}")


# ── 리포트 ───────────────────────────────────────────────────
def _near(snaps: list, hours: float, floor_h: float = 12.0) -> dict | None:
    """목표 시각에 가장 가까운 스냅샷.

    ⚠️ 아직 어린 글(발행 3시간)을 24시간 칸에 넣으면 평균이 통째로 깎인다.
    실측 첫 회에 3.7h 글 2건이 섞여 ai_news 평균을 끌어내렸다 — floor 로 막는다.
    """
    cand = [s for s in snaps
            if s.get("age_h") is not None and s["age_h"] >= floor_h]
    return min(cand, key=lambda s: abs(s["age_h"] - hours)) if cand else None


def report(store: dict) -> None:
    posts = store.get("posts", {})
    if not posts:
        log("\n아직 수집된 성과가 없습니다. 토큰을 넣고 한 번 실행해 주십시오.")
        return

    by_ch: dict[str, list] = {}
    for pid, r in posts.items():
        s = _near(r.get("snapshots", []), 24)
        if s and s.get("views") is not None:
            by_ch.setdefault(r.get("channel", "?"), []).append((s, r, pid))

    log("\n=== 채널별 24시간 성과 (같은 계정, 같은 잣대) ===")
    log(f"{'채널':<10}{'건수':>5}{'평균조회':>10}{'평균좋아요':>11}{'평균댓글':>10}")
    base = None
    for ch in ("ghost", "carousel", "reels", "ai_news"):
        rows = by_ch.get(ch) or []
        if not rows:
            continue
        n = len(rows)
        av = sum(s.get("views", 0) for s, _, _ in rows) / n
        al = sum(s.get("likes", 0) for s, _, _ in rows) / n
        ar = sum(s.get("replies", 0) for s, _, _ in rows) / n
        if ch == "ghost":
            base = av
        log(f"{ch:<10}{n:>5}{av:>10.0f}{al:>11.1f}{ar:>10.1f}")
    ai = by_ch.get("ai_news") or []
    if ai and base:
        av = sum(s.get("views", 0) for s, _, _ in ai) / len(ai)
        log(f"\n→ AI 뉴스는 운세 유령글의 {av / base * 100:.0f}% 수준입니다.")

    if ai:
        log("\n=== AI 뉴스 글별 (조회 많은 순) ===")
        for s, r, _ in sorted(ai, key=lambda x: -x[0].get("views", 0)):
            log(f"  {s.get('views', 0):>6}회 / 좋아요 {s.get('likes', 0):>3} "
                f"/ 댓글 {s.get('replies', 0):>2}  {r.get('head', '')[:52]}")
        log("\n조회 상위·하위의 **제목 형태**가 다음 주제 선정의 근거입니다.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true", help="저장분만 출력(API 호출 없음)")
    ap.add_argument("--dry-run", action="store_true", help="대상만 나열")
    a = ap.parse_args()

    if a.report:
        report(load_store())
        return 0

    tok = os.environ.get("THREADS_ACCESS_TOKEN", "")
    uid = os.environ.get("THREADS_USER_ID", "")
    if not tok and not a.dry_run:
        log("[FAIL] THREADS_ACCESS_TOKEN 이 없습니다. (--dry-run 은 토큰 없이 됩니다)")
        return 1

    store = collect(tok, dry=a.dry_run)
    if not a.dry_run and uid:
        collect_account(tok, uid)
    report(store)
    return 0


if __name__ == "__main__":
    sys.exit(main())
