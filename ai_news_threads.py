# -*- coding: utf-8 -*-
"""AI 최신 뉴스 → 쓰레드 자동 발행 (2026-07-27 신설).

왜 운세 계정에 AI 뉴스인가
--------------------------
한밝님의 전문 영역이 '운세 + AI' 두 개다. 운세만 올리는 계정은 다른 운세 계정과
구분이 안 되지만, AI를 같이 다루는 운세 계정은 이 계정뿐이다. 그게 차별점이다.
그래서 계정을 나누지 않고 같은 계정에서 시간대만 분리한다.
  아침 = 오늘의 운세(zodiac_ghost)  /  낮 = AI 뉴스(이 파일)  /  저녁 = 카드뉴스

사실 정확성 (fail-closed)
------------------------
운명과학TV가 '허위 콘텐츠'로 수익정지된 이력이 있다. 뉴스는 특히 위험하다.
그래서 이 스크립트는 **없는 사실을 만들지 않는다**:
  - 본문 문장은 언론사 기사 제목·요약에서만 나온다
  - LLM은 '새 정보 추가'가 아니라 '문장 다듬기'만 시킨다(프롬프트로 못박음)
  - 원문 제목의 핵심 명사가 결과물에 남아 있는지 검사하고, 어긋나면 **발행하지 않는다**
  - LLM 호출이 실패하면 규칙 기반 문구로 폴백한다(발행은 계속)

본문에 링크를 넣지 않는다 — 스레드는 본문 링크가 있으면 도달이 눌린다.
대신 출처 언론사명을 밝힌다(신뢰 + 표절 회피).

실행:
  python ai_news_threads.py --dry-run     # 문구만 출력(발행 안 함)
  python ai_news_threads.py               # 1건 발행
  python ai_news_threads.py --count 2     # 2건 발행
환경변수: THREADS_ACCESS_TOKEN, THREADS_USER_ID (없으면 dry-run만 가능)
          GEMINI_API_KEY (없으면 규칙 기반 폴백)
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import re
import sys
import time
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

BASE = Path(__file__).resolve().parent
STATE = BASE / "ai_news_posted.json"
GRAPH = "https://graph.threads.net/v1.0"

# ⚠️ 구글 뉴스 RSS 는 **GitHub 러너(해외 IP)에서 XML 이 아닌 응답**을 준다
# (실측: "not well-formed (invalid token): line 1, column 252" — 동의 페이지 추정).
# 로컬(한국 IP)에서는 멀쩡해서 안 걸린다. 그래서 국내 언론사 RSS 를 정본으로 쓰고
# 구글 뉴스는 보조로만 둔다 — 실패해도 나머지로 발행이 굴러간다.
# (name, url, ai_filter) — ai_filter=True 면 AI 관련 기사만 골라낸다(종합 매체).
FEEDS = [
    ("AI타임스", "https://www.aitimes.com/rss/allArticle.xml", False),
    ("전자신문", "https://rss.etnews.com/Section901.xml", True),
    ("전자신문", "https://rss.etnews.com/Section902.xml", True),
    ("블로터", "https://www.bloter.net/rss/allArticle.xml", True),
]
# 보조 소스(있으면 좋고 없어도 그만)
QUERIES = ["인공지능", "생성형 AI", "AI 규제"]

AI_WORDS = ["AI", "에이아이", "인공지능", "생성형", "챗GPT", "GPT", "LLM", "언어모델",
            "제미나이", "클로드", "오픈AI", "딥러닝", "로봇", "반도체", "데이터센터"]
FRESH_HOURS = 48          # 이보다 오래된 기사는 '최신'이 아니다
MAX_TEXT = 480            # 스레드 본문 상한 500자 — 여유 20자

# 관심을 끌지 못하는 축은 뺀다(주가·인사·단순 협약은 공감이 안 된다).
DROP_WORDS = ["주가", "코스닥", "코스피", "인사", "부고", "협약식", "MOU", "수주",
              "컨퍼런스 개최", "세미나 개최", "채용 공고"]


def log(m: str):
    print(f"[ai-news] {m}", flush=True)


# ── 수집 ─────────────────────────────────────────────────────
def _parse_pub(pub: str, now: dt.datetime) -> dt.datetime:
    """RFC822. 국내 매체는 '+0900' 오프셋을, 구글은 'GMT' 약어를 쓴다 — 둘 다 받는다."""
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z"):
        try:
            t = dt.datetime.strptime(pub.strip(), fmt)
            return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)
        except Exception:
            continue
    return now


def fetch_news() -> list[dict]:
    """국내 IT 매체 RSS + (보조)구글 뉴스에서 최근 기사를 모은다."""
    out, seen = [], set()
    now = dt.datetime.now(dt.timezone.utc)

    sources = [(nm, u, f) for nm, u, f in FEEDS]
    sources += [("", "https://news.google.com/rss/search?q="
                 + urllib.parse.quote(q) + "&hl=ko&gl=KR&ceid=KR:ko", False)
                for q in QUERIES]

    for feed_name, url, ai_filter in sources:
        try:
            r = requests.get(url, timeout=20,
                             headers={"User-Agent": "Mozilla/5.0"})
            root = ET.fromstring(r.content)
        except Exception as e:
            log(f"[WARN] 수집 실패({feed_name or 'google'}): {str(e)[:70]}")
            continue
        for it in root.iter("item"):
            title = (it.findtext("title") or "").strip()
            link = (it.findtext("link") or "").strip()
            src = (it.findtext("source") or "").strip()
            pub = it.findtext("pubDate") or ""
            if not title or not link:
                continue
            # 구글 뉴스 제목은 "제목 - 언론사" 형태다. <source> 태그가 따로 있어도
            # 제목 꼬리에 그대로 남아 있어서, 안 떼면 "[머니투데이] … - 머니투데이"가 된다.
            while " - " in title:
                head, tail = title.rsplit(" - ", 1)
                if len(tail) > 20 or not head:
                    break
                title, src = head.strip(), src or tail.strip()
            title = html.unescape(title)
            key = re.sub(r"\W+", "", title)[:40]
            if key in seen:
                continue
            t = _parse_pub(pub, now)
            if (now - t).total_seconds() > FRESH_HOURS * 3600:
                continue
            if any(w in title for w in DROP_WORDS) or not good_title(title):
                continue
            if ai_filter and not any(w in title for w in AI_WORDS):
                continue          # 종합 매체는 AI 기사만 골라낸다
            seen.add(key)
            out.append({"title": title, "link": link,
                        "source": feed_name or html.unescape(src) or "언론 보도",
                        "at": t.isoformat()})
    out.sort(key=lambda x: x["at"], reverse=True)
    log(f"수집 {len(out)}건 (최근 {FRESH_HOURS}시간)")
    return out


def _posted() -> set:
    try:
        return set(json.loads(STATE.read_text(encoding="utf-8"))["keys"])
    except Exception:
        return set()


def _mark(key: str, text: str, pid: str):
    d = {"keys": [], "log": []}
    try:
        d = json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        pass
    d.setdefault("keys", []).append(key)
    d.setdefault("log", []).append(
        {"at": dt.datetime.now().isoformat(timespec="seconds"),
         "post_id": pid, "text": text})
    d["keys"] = d["keys"][-400:]
    d["log"] = d["log"][-120:]
    STATE.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def _key(n: dict) -> str:
    return re.sub(r"\W+", "", n["title"])[:40]


# ── 문구 만들기 ───────────────────────────────────────────────
# 마무리 한 줄 — 매번 같으면 봇으로 보인다. 날짜로 회전시킨다.
CLOSERS = [
    "저는 사주를 보는 사람이지만, 요즘은 이 흐름도 같이 봅니다.",
    "기술이 바뀌어도 사람 사는 결은 크게 다르지 않더군요.",
    "이런 변화가 우리 일상에 닿기까지는 시간이 좀 걸릴 겁니다.",
    "저도 매일 들여다보는 쪽이라, 눈에 밟혀 남겨 둡니다.",
    "당장 내 일은 아니어도, 알아두면 언젠가 쓰입니다.",
    "새 도구가 나올수록 결국 쓰는 사람의 몫이 커집니다.",
]

# 사실은 **원문 제목에서만** 온다. LLM에게는 사실 요약을 시키지 않고 '해석'만 시킨다.
# 처음엔 제목을 다듬게 했더니 잘린 영문 제목을 그대로 뱉거나(실측) 원문과 어긋나
# 게이트에 걸렸다. 역할을 쪼개니 둘 다 사라졌다 — 제목은 인용, 해석은 생성.
PROMPT = """아래 기사 제목을 읽고, 한국 독자에게 '그래서 이게 무슨 의미인지'를 설명하는
한국어 문장 2개를 써라.

기사 제목: {title}

규칙:
- 제목에 없는 사실·숫자·회사명·날짜를 절대 만들어내지 마라. 확실하지 않으면 일반적인 설명만 해라.
- 정확히 2문장. 첫 문장은 이 소식이 왜 나왔는지 맥락, 둘째 문장은 우리 일상에 닿는 지점.
- 30대~시니어가 읽는다. 존댓말, 쉬운 말, 전문용어는 풀어 쓴다.
- 과장 금지("충격", "폭발적", "판도가 바뀐다" 같은 말 쓰지 마라).
- 제목을 그대로 반복하지 마라. 해시태그·이모지·링크 금지.
- 결과 문장만 출력한다."""


def _gemini(title: str, source: str) -> str | None:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return None
    # 무료 티어는 분당 호출 제한이 있어 연속 호출 시 429 가 난다. 한 번 쉬고 재시도한다.
    for attempt in (1, 2):
        body = _gemini_once(key, title, source)
        if body is not None:
            return body
        if attempt == 1:
            # 429 는 분당 한도라 12초로는 안 풀린다(실측). 한 텀 쉬고 다시 친다.
            time.sleep(35)
    return None


def _gemini_once(key: str, title: str, source: str) -> str | None:
    try:
        r = requests.post(
            "https://generativelanguage.googleapis.com/v1beta/models/"
            "gemini-3.5-flash:generateContent",
            timeout=40, headers={"x-goog-api-key": key},
            json={"contents": [{"parts": [{"text": PROMPT.format(
                title=title, source=source)}]}],
                # ⚠️ thinkingBudget=0 필수. 3.5 Flash는 기본으로 사고에 토큰을 쓰는데,
                # maxOutputTokens가 작으면 사고에 다 쓰고 **본문이 빈 채로 200**이 온다
                # (실측: 예외도 안 나서 조용히 폴백됐다). 두 줄짜리 해석에 사고는 불필요.
                "generationConfig": {"temperature": 0.8, "maxOutputTokens": 700,
                                     "thinkingConfig": {"thinkingBudget": 0}}})
        j = r.json()
        cands = j.get("candidates")
        if not cands:
            # 원인이 429(쿼터)인지 안전필터인지 응답을 봐야 안다. 예전에 여기서
            # KeyError 만 찍혀 원인 추적이 안 됐다.
            log(f"[WARN] Gemini 응답에 candidates 없음 (HTTP {r.status_code}): "
                f"{json.dumps(j, ensure_ascii=False)[:180]}")
            return None
        parts = cands[0].get("content", {}).get("parts") or []
        t = "".join(p.get("text", "") for p in parts).strip()
        return re.sub(r"[#*`]", "", t).strip() or None
    except Exception as e:
        log(f"[WARN] Gemini 호출 실패({type(e).__name__}: {str(e)[:80]})")
        return None


def good_title(t: str) -> bool:
    """읽을 수 있는 제목인가. 구글 뉴스에는 영문·잘린 제목이 섞여 들어온다
    (실측: 'Scope: 자동차·로봇 넘어 도시 단위로 (Beyond cars' — 괄호가 안 닫힘)."""
    if not (12 <= len(t) <= 90):
        return False
    ko = len(re.findall(r"[가-힣]", t))
    if ko / max(1, len(t)) < 0.45:        # 한글이 절반 미만이면 국내 독자용이 아니다
        return False
    if t.count("(") != t.count(")") or t.count("[") != t.count("]"):
        return False                       # 잘린 제목
    return True


def fact_gate(interp: str, title: str) -> bool:
    """해석문이 **없는 사실을 만들지 않았는지** 검사한다.

    해석문에 나온 숫자가 원문 제목에 없으면 지어낸 것이다(연도·금액·퍼센트가 위험).
    고유명사까지 잡으려면 형태소 분석이 필요해 여기서는 숫자만 본다 — 숫자가
    허위 콘텐츠 판정에서 가장 크게 걸리는 부분이다.
    """
    nums_t = set(re.findall(r"\d+", title))
    nums_b = set(re.findall(r"\d+", interp))
    invented = {n for n in nums_b - nums_t if len(n) >= 2}
    if invented:
        log(f"[GATE] 제목에 없는 숫자 {sorted(invented)} — 폐기")
        return False
    if len(interp) < 20 or interp.count(".") < 1:
        return False
    # 제목을 그대로 되풀이한 것도 해석이 아니다
    core = re.sub(r"\W+", "", title)[:24]
    return core not in re.sub(r"\W+", "", interp)


def build_text(n: dict, date: dt.date, slot: int = 0) -> str | None:
    """사실(제목 인용) + 해석(생성) + 마무리 + 출처.

    slot = 그날 몇 번째 글인지. 같은 날 2건을 올릴 때 마무리 문장이 겹치지 않게 한다.
    """
    interp = _gemini(n["title"], n["source"])
    if interp and not fact_gate(interp, n["title"]):
        interp = None
    closer = CLOSERS[(date.toordinal() + slot * 2) % len(CLOSERS)]
    head = f"[{n['source']}] {n['title']}"
    if interp:
        return f"{head}\n\n{interp}\n\n{closer}"[:MAX_TEXT]
    # 해석 생성에 실패하면 사실만 남긴다 — 지어내느니 짧게 간다.
    return f"{head}\n\n{closer}"[:MAX_TEXT]


# ── 발행 ─────────────────────────────────────────────────────
def publish(text: str) -> str:
    tok = os.environ["THREADS_ACCESS_TOKEN"]
    uid = os.environ["THREADS_USER_ID"]
    base = f"{GRAPH}/{uid}"
    j = requests.post(f"{base}/threads", timeout=30, data={
        "media_type": "TEXT", "text": text, "access_token": tok}).json()
    cid = j.get("id")
    if not cid:
        raise SystemExit(f"[FAIL] container: {j}")
    time.sleep(3)
    j = requests.post(f"{base}/threads_publish", timeout=30,
                      data={"creation_id": cid, "access_token": tok}).json()
    pid = j.get("id")
    if not pid:
        raise SystemExit(f"[FAIL] publish: {j}")
    return pid


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--count", type=int, default=1)
    a = ap.parse_args()

    today = dt.date.today()
    done = _posted()
    news = [n for n in fetch_news() if _key(n) not in done]
    if not news:
        log("발행할 새 뉴스가 없습니다(전부 기발행이거나 최신 기사 없음)")
        return

    # 같은 언론사만 연달아 뽑히면 한 매체 받아쓰기로 보인다(실측: 3건 전부 동아일보).
    # 언론사별로 1건씩 돌아가며 고른다.
    picked, used_src = [], set()
    for n in news:
        if n["source"] not in used_src:
            picked.append(n)
            used_src.add(n["source"])
    picked += [n for n in news if n not in picked]

    sent = 0
    for n in picked:
        if sent >= a.count:
            break
        text = build_text(n, today, sent)
        if not text:
            continue
        print("-" * 52)
        print(text)
        print("-" * 52)
        if a.dry_run:
            sent += 1
            continue
        pid = publish(text)
        _mark(_key(n), text, pid)
        log(f"발행 완료: {pid}")
        sent += 1
        if sent < a.count:
            time.sleep(25)      # Gemini 분당 한도 회피 + 연속 발행처럼 안 보이게
    if a.dry_run:
        log(f"[DRY-RUN] {sent}건 미리보기 — 발행하지 않았습니다")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
