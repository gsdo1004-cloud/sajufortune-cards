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

import llm_fallback as llm

BASE = Path(__file__).resolve().parent
STATE = BASE / "ai_news_posted.json"
GRAPH = "https://graph.threads.net/v1.0"

# ── 소스 (2026-07-27 전면 교체) ───────────────────────────────
# 처음엔 국내 종합 언론 RSS 를 썼는데, 나오는 게 "수원시 플랫폼 구축", "OO기업 투자 유치"
# 같은 **지역 행정·기업 재무 뉴스**였다. 사람들이 스레드에서 보고 싶은 건 그게 아니다.
# **내가 지금 쓰는 도구의 새 소식** — 새 모델, 새 오픈소스, 새 기능이다.
#
# 그래서 개발자·AI 실사용자가 실제로 보는 곳으로 바꿨다. 셋 다 **인기순**이라
# 그 자체가 "사람들이 관심 있는 것"의 신호가 된다(우리가 인기도를 따로 계산할 필요가 없다).
#   긱뉴스   = 한국 개발자 커뮤니티. 한국어. 추천 많은 순
#   HN       = 해커뉴스 100점 이상만. 영어지만 업계 최대 신호
#   깃허브   = 그날 뜬 저장소(영상자동화·AI 도구가 여기서 먼저 뜬다)
#   공식블로그 = OpenAI·HuggingFace 1차 출처
# (name, url, need_ai_filter, is_english)
# ── 2026-07-31 전환: 개발자 소스 → 한국어 대중 소스 ──────────
# 실측이 뒤집었다. 7/27~7/31 발행 11건 24시간 조회 평균 6회, 9건 중 8건이 댓글 0.
# **유일하게 반응이 붙은 글(좋아요2·댓글2)이 한국어 종합 언론 기사**였고
# 나머지 Show HN·GitHub 트렌딩은 0~13회였다.
# 데이터랩도 같은 방향이다 — 한국인은 AI 를 '개념'이 아니라 **제품 이름**으로 검색한다
# (제미나이 85 / 클로드 83 vs "AI 부업" 0.011 / "AI 일자리" 0.002, 4자릿수 차).
#
# ⚠️ 구글 뉴스 RSS 는 쓰지 않는다 — 러너에서 XML 이 아닌 응답이 온다(기존 실측, 73행 참조).
#    발행사 RSS 를 직접 친다.
FEEDS_MASS = [
    ("AI타임스", "https://www.aitimes.com/rss/allArticle.xml", False, False),
    ("ZDNet", "https://feeds.feedburner.com/zdkorea", True, False),
    ("전자신문", "https://rss.etnews.com/Section902.xml", True, False),
    ("아이뉴스24", "https://www.inews24.com/rss/news_it.xml", True, False),
]
# 구 소스. 롤백용으로 남긴다 — AI_NEWS_MODE=dev 로 되돌릴 수 있다.
FEEDS_DEV = [
    ("긱뉴스", "https://feeds.feedburner.com/geeknews-feed", False, False),
    ("Hacker News", "https://hnrss.org/frontpage?points=100", False, True),
    ("Hacker News", "https://hnrss.org/show?points=50", False, True),
    ("GitHub 트렌딩", "https://mshibanami.github.io/GitHubTrendingRSS/daily/python.xml",
     False, True),
    ("OpenAI", "https://openai.com/blog/rss.xml", False, True),
    ("Hugging Face", "https://huggingface.co/blog/feed.xml", False, True),
]
FEEDS = FEEDS_DEV if os.environ.get("AI_NEWS_MODE") == "dev" else FEEDS_MASS
QUERIES: list[str] = []      # 구글 뉴스 보조 소스는 폐지(러너에서 XML 이 아닌 응답)

AI_WORDS = ["AI", "에이아이", "인공지능", "생성형", "챗GPT", "GPT", "LLM", "언어모델",
            "제미나이", "클로드", "오픈AI", "딥러닝", "로봇", "반도체", "데이터센터"]

# 관심 축 — 이 단어가 들어간 글을 우선한다.
# 축이 바뀌었다: '개발자가 쓸 도구'가 아니라 **아는 이름 + 내 삶의 손익 + 숫자**다.
# 실제로 터진 한국 헤드라인의 골격이 전부 이 셋이었다
# ("AI 못 다루면 승진 못한다"·"의사 고액연봉 딱 3년 남았다"·"챗GPT가 추천한 라면은").
BOOST_WORDS = [
    # ① 아는 이름(검색량의 99%가 여기 몰린다)
    "챗GPT", "ChatGPT", "GPT", "제미나이", "Gemini", "클로드", "Claude",
    "오픈AI", "OpenAI", "소라", "코파일럿", "뤼튼", "퍼플렉시티", "네이버 AI",
    # ② 내 삶의 손익
    "요금", "가격", "무료", "인하", "월급", "연봉", "승진", "채용", "일자리",
    "학생", "학교", "자녀", "아이", "노후", "건강", "병원", "시험", "취업",
    "직장인", "생활", "일상", "부모", "어르신",
    # ③ 운세 계정과의 접점(이 계정의 차별점)
    # ⚠️ "점" 같은 한 글자는 넣지 마라 — 관점·시점·장점에 전부 걸려 가점이 무의미해진다.
    "사주", "운세", "타로", "관상", "심리", "성격", "궁합",
]
FRESH_HOURS = 48          # 이보다 오래된 기사는 '최신'이 아니다
MAX_TEXT = 480            # 스레드 본문 상한 500자 — 여유 20자

# 사람들이 안 궁금해하는 축은 뺀다. 지역 행정·기업 재무 뉴스가 특히 그렇다
# ("수원시 플랫폼 구축", "네이버 100억달러 유치" 류 — 실제로 이런 게 뽑혀 나왔다).
DROP_WORDS = ["주가", "코스닥", "코스피", "인사", "부고", "협약식", "MOU", "수주",
              "컨퍼런스 개최", "세미나 개최", "채용 공고",
              "시장", "군수", "구청", "지자체", "시청", "도청", "의회", "국비",
              "유치", "착공", "준공", "간담회", "출범식", "위원회", "포럼 개최",
              # 2026-07-31 추가 — 대중 매체로 옮기면 B2B·실적 기사가 대량으로 딸려온다.
              # 실측 표본에서 LG CNS 컨콜 기사만 3건이 연달아 나왔다.
              "컨콜", "실적", "영업익", "영업이익", "매출", "분기", "상장", "IPO",
              "투자 유치", "인수", "합병", "지분", "공시", "배당", "증권",
              "구축 사업", "도입 계약", "공급 계약", "레퍼런스", "파트너십 체결",
              "기업용", "엔터프라이즈", "솔루션 출시", "B2B",
              # 임원 인사 기사. 첫 dry-run 에서 "몬드리안에이아이 CSO 영입"이 2번째로 뽑혔다 —
              # 기존 "인사" 한 단어로는 '영입·선임' 표현을 못 잡는다.
              "영입", "선임", "임명", "취임", "승진 인사", "조직 개편", "대표 내정"]


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

    for feed_name, url, ai_filter, is_en in FEEDS:
        try:
            r = requests.get(url, timeout=20,
                             headers={"User-Agent": "Mozilla/5.0"})
            root = ET.fromstring(r.content)
        except Exception as e:
            log(f"[WARN] 수집 실패({feed_name}): {str(e)[:70]}")
            continue
        rank = 0
        for it in root.iter("item"):
            rank += 1
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
            if any(w in title for w in DROP_WORDS) or not good_title(title, is_en):
                continue
            if ai_filter and not any(w in title for w in AI_WORDS):
                continue          # 종합 매체는 AI 기사만 골라낸다
            seen.add(key)
            low = title.lower()
            out.append({"title": title, "link": link,
                        "source": feed_name or html.unescape(src) or "언론 보도",
                        "at": t.isoformat(), "rank": rank, "is_en": is_en,
                        "boost": sum(1 for w in BOOST_WORDS if w.lower() in low)})
    # 소스가 전부 인기순이라 **RSS 순서 자체가 사람들의 관심 신호**다.
    # 시간순으로 재정렬하면 그 신호를 버리게 된다 — 관심축 가점 → 원래 순위 순으로 본다.
    out.sort(key=lambda x: (-x["boost"], x["rank"]))
    log(f"수집 {len(out)}건 (최근 {FRESH_HOURS}시간, 관심축 매칭 "
        f"{sum(1 for x in out if x['boost'])}건)")
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
# 마무리 한 줄도 반말. 매번 같으면 봇 티가 나니 날짜로 돌린다.
# 마무리를 **감상에서 질문으로** 바꿨다(2026-07-31).
# 실측: 발행 9건 중 8건 댓글 0. 감상으로 끝나면 답글 달 이유가 없다.
# 쓰레드는 업로드 직후 10분 반응 속도가 최종 도달을 결정하는데, 지금은 반응할 이유를 안 줬다.
# LLM 이 질문을 못 만들었을 때만 쓰는 폴백이다 — 되도록 기사에 맞는 질문이 낫다.
# ⚠️ 폴백 질문은 **어떤 기사에 붙어도 말이 되어야 한다.**
# 첫 시험에서 "주변에 이미 쓰는 사람 있나?"가 딥페이크 소송 기사에 붙어 문맥이 깨졌다.
# 도구를 전제한 질문(써봤나·쓸 건가)은 여기 두지 않는다.
CLOSERS = [
    "이 소식, 반가운 쪽인가 불안한 쪽인가?",
    "나는 반반이다. 당신은 어느 쪽인가?",
    "이게 5년 뒤에도 지금처럼 보일까?",
    "이걸 반기는 사람과 못 미더워하는 사람, 어느 쪽에 서겠나?",
    "당신이라면 이걸 어느 쪽으로 받아들이겠나?",
    "이런 흐름, 막을 수 있다고 보나 못 막는다고 보나?",
    "한 줄만 남겨달라. 어떻게 보고 있나?",
]

# 사실은 **원문 제목에서만** 온다. LLM에게는 사실 요약을 시키지 않고 '해석'만 시킨다.
# 처음엔 제목을 다듬게 했더니 잘린 영문 제목을 그대로 뱉거나(실측) 원문과 어긋나
# 게이트에 걸렸다. 역할을 쪼개니 둘 다 사라졌다 — 제목은 인용, 해석은 생성.
# 말투 — 스레드는 존댓말을 거의 안 쓴다. 블로그 문체로 쓰면 광고처럼 읽히고 반응이 죽는다.
# 그래서 여기서만 반말을 쓴다(한밝님과의 대화·블로그·유튜브는 그대로 존댓말).
PROMPT = """아래 뉴스를 스레드(SNS)에 올릴 짧은 글로 바꿔라.

제목: {title}

너는 사주·운세를 보는 사람이고, AI 도 매일 쓴다. 읽는 사람은 **개발자가 아니라
운세를 보러 온 보통 사람**이다. 그 사람이 자기 삶과 연결지어 읽게 써라.

**정확히 3줄**로 출력한다. 줄바꿈으로만 구분하고 번호·기호를 붙이지 마라.

1줄 = 훅. 한 문장. 스크롤을 멈추게 하는 역설이나 뒤집기.
       ("AI 요금이 내려갔다는데, 나는 이게 반가운 소식으로 안 읽힌다")
2줄 = 해석. 1~2문장. 이게 **보통 사람 삶에 뭐가 달라지는지**.
       ⚠️ 사주·운·명리 비유는 **정말 자연스럽게 붙을 때만** 쓴다. 기사와 상관없는데
       "대운이 바뀌듯", "내 사주에 AI를 이식하면" 같은 걸 억지로 갖다 붙이지 마라.
       열에 아홉은 그냥 담백하게 쓰는 게 낫다.
3줄 = 질문. 한 문장, 반드시 물음표로 끝낸다. **찬반이 갈리는 것**을 물어라.
       "어떻게 생각하나?" 같은 맹탕 말고, 둘 중 하나를 고르게 하는 질문.

말투:
- **반말.** "~다", "~네", "~더라", "~인 듯". 존댓말("~습니다", "~세요") 절대 금지.
- 혼잣말하듯, 툭 던지듯. 뉴스 앵커 말투·기사체 금지("주목받고 있다", "전망이다").
- 광고 문구 금지. 사주 서비스 홍보 절대 금지.

내용:
- **제목에 없는 숫자·금액·연도·회사명을 지어내지 마라.** 모르면 숫자를 아예 쓰지 마라.
- 영어 제목이면 한국어로 옮기되 제품·회사 이름은 원문 그대로 둔다.
- "인공지능이란 무엇인가" 식 교과서 설명 금지.
- 해시태그·이모지·링크 금지.
- 3줄 외에 아무것도 출력하지 마라."""


def _gemini(title: str, source: str) -> str | None:
    """해석문 생성. Gemini 가 429 로 막히면 로컬 Ollama 로 넘어간다(llm_fallback).

    2026-07-27: 무료 쿼터 429 로 2건째부터 해석문이 통째로 빠지는 일이 있었다.
    집 PC 의 Ollama 는 쿼터가 없어 그 구멍을 메운다. 러너에는 Ollama 가 없으니
    거기서는 Gemini 만 쓰고, 실패하면 아래 build_text 가 사실만 발행한다.
    """
    t = llm.ask(PROMPT.format(title=title, source=source),
                max_tokens=700, temperature=0.8)
    return re.sub(r"[#*`]", "", t).strip() or None if t else None


def good_title(t: str, is_en: bool = False) -> bool:
    """읽을 수 있는 제목인가. 잘린 제목·너무 짧거나 긴 제목을 거른다."""
    if not (10 <= len(t) <= 110):
        return False
    if not is_en:
        ko = len(re.findall(r"[가-힣]", t))
        if ko / max(1, len(t)) < 0.3:     # 한국어 소스인데 한글이 거의 없으면 이상하다
            return False
    if t.count("(") != t.count(")") or t.count("[") != t.count("]"):
        return False                       # 잘린 제목
    return True


def sane_gate(interp: str) -> bool:
    """생성문 위생 검사 — 사람이 쓴 것처럼 보이는가.

    로컬 폴백(qwen2.5:14b)이 중국 모델이라 한국어 출력에 **한자와 잡음이 샌다.**
    실측으로 나온 것들:
      '廉價安全  Camera - Linux용 가벼운 CCTV네'   ← 중국어 혼입
      '쉬워질 듯nego'                              ← 꼬리에 잡음 문자
    이런 게 그대로 나가면 자동 생성물 티가 가장 크게 난다.
    """
    if re.search(r"[一-鿿]", interp):          # 한자
        log("[GATE] 한자 혼입 — 폐기")
        return False
    if re.search(r"[぀-ヿЀ-ӿ]", interp):   # 일본어 가나·키릴
        log("[GATE] 외국 문자 혼입 — 폐기")
        return False
    if "\t" in interp or re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", interp):
        log("[GATE] 제어문자 — 폐기")
        return False
    # 한글이 너무 적으면 번역이 덜 된 것이다(제품명은 영어로 남아도 되니 여유를 둔다)
    ko = len(re.findall(r"[가-힣]", interp))
    if ko / max(1, len(interp)) < 0.35:
        log("[GATE] 한글 비율 부족 — 폐기")
        return False
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
    if len(interp) < 20:
        return False
    # 제목을 그대로 되풀이한 것도 해석이 아니다
    core = re.sub(r"\W+", "", title)[:24]
    return core not in re.sub(r"\W+", "", interp)


def split3(t: str) -> tuple[str, str, str] | None:
    """LLM 출력을 (훅, 해석, 질문)으로 쪼갠다.

    3줄을 요구했지만 모델은 늘 그대로 주지 않는다 — 번호를 붙이거나, 해석을
    두 줄로 나누거나, 질문을 빼먹는다. 그래서 **첫 줄=훅 / 마지막 줄=질문 /
    가운데 전부=해석**으로만 본다. 질문이 물음표로 안 끝나면 실패로 친다
    (폴백 질문을 쓰는 게 맹탕 마무리보다 낫다).
    """
    lines = [re.sub(r"^\s*(\d+[.)]|[-•*])\s*", "", ln).strip()
             for ln in t.splitlines() if ln.strip()]
    if len(lines) < 3:
        return None
    hook, question = lines[0], lines[-1]
    body = " ".join(lines[1:-1]).strip()
    if not question.endswith(("?", "?")):
        return None
    if not hook or not body:
        return None
    return hook, body, question


def build_text(n: dict, date: dt.date, slot: int = 0) -> tuple[str, str]:
    """(발행문, 해석문) 반환. 해석문은 인포그래픽 카드에도 쓰인다.

    slot = 그날 몇 번째 글인지. 같은 날 2건을 올릴 때 마무리 문장이 겹치지 않게 한다.
    """
    raw = _gemini(n["title"], n["source"])
    closer = CLOSERS[(date.toordinal() + slot * 2) % len(CLOSERS)]
    head = f"[{n['source']}] {n['title']}"

    parts = split3(raw) if raw else None
    if parts:
        hook, interp, question = parts
        # 훅에도 게이트를 건다. 지어낸 숫자는 해석보다 훅에서 더 위험하다 —
        # 첫 줄이라 그것만 읽고 넘어가는 사람이 대부분이다.
        if not (sane_gate(hook + " " + interp) and fact_gate(hook + " " + interp, n["title"])):
            parts = None

    if parts:
        hook, interp, question = parts
        # 훅 → 사실(원문 제목 인용) → 해석 → 질문.
        # 사실은 여전히 제목 인용뿐이다. LLM 은 훅·해석·질문만 쓴다.
        return (f"{hook}\n\n{head}\n\n{interp}\n\n{question}"[:MAX_TEXT], interp)

    # 3줄 파싱이나 게이트에 실패하면 사실 + 질문만 남긴다 — 지어내느니 짧게 간다.
    log("[GATE] 3줄 생성 실패 — 제목+질문만 발행")
    return f"{head}\n\n{closer}"[:MAX_TEXT], ""


# ── 발행 ─────────────────────────────────────────────────────
# ── 인포그래픽 A/B (2026-07-27) ──────────────────────────────
# 스레드는 원래 텍스트 중심 플랫폼이라 이미지가 도달에 유리한지 **확인된 바 없다.**
# 그래서 하루 2건 중 1건에만 카드를 붙여 같은 날·같은 계정에서 비교한다.
# 카드는 로컬 PIL 렌더(ai_news_card) — Topview 로 뽑으면 한글이 깨진다(7/30얼 실측).
# 뉴스는 회사명·금액이 틀리면 허위정보가 되므로 AI 렌더를 쓰지 않는다.
CARD_ENABLED = os.environ.get("AI_NEWS_CARD", "1") != "0"
GH_RAW = "https://raw.githubusercontent.com/gsdo1004-cloud/sajufortune-cards/main"


def build_card(n: dict, body: str, date_iso: str, slot: int) -> str | None:
    """인포그래픽을 만들고 raw URL 을 돌려준다. 실패하면 None(텍스트만 발행)."""
    try:
        import ai_news_card
        rel = f"cards/ai_news/{date_iso}_{slot}.png"
        ai_news_card.render(n["title"], body, n["source"], BASE / rel,
                            dt.date.fromisoformat(date_iso))
        return f"{GH_RAW}/{rel}"
    except Exception as e:
        log(f"[WARN] 카드 생성 실패({type(e).__name__}: {str(e)[:70]}) — 텍스트만 발행")
        return None


def publish(text: str, image_url: str | None = None) -> str:
    tok = os.environ["THREADS_ACCESS_TOKEN"]
    uid = os.environ["THREADS_USER_ID"]
    base = f"{GRAPH}/{uid}"
    payload = {"media_type": "TEXT", "text": text, "access_token": tok}
    if image_url:
        payload = {"media_type": "IMAGE", "image_url": image_url,
                   "text": text, "access_token": tok}
    j = requests.post(f"{base}/threads", timeout=30, data=payload).json()
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


PLAN = BASE / "ai_news_plan.json"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--count", type=int, default=1)
    # 카드를 붙이려면 이미지가 **먼저 레포에 올라가 있어야** raw URL 이 산다.
    # 그래서 Actions 에서는 두 단계로 나눈다: prepare(카드 생성) → 커밋·푸시 → publish.
    # 옵션 없이 실행하면(로컬) 카드 없이 텍스트만 발행한다 — 로컬 파일은 raw URL 이 없다.
    ap.add_argument("--prepare", action="store_true", help="카드 생성 + 계획 저장(발행 안 함)")
    ap.add_argument("--publish", action="store_true", help="저장된 계획으로 발행")
    a = ap.parse_args()

    if a.publish:
        return _publish_planned()

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

    plan, sent = [], 0
    for n in picked:
        if sent >= a.count:
            break
        text, interp = build_text(n, today, sent)
        if not text:
            continue
        # A/B: 같은 날 2건 중 1건에만 카드를 붙인다. 날짜에 따라 첫/둘째가 번갈아
        # 카드를 받아서, 하루 1건만 나가는 날에도 절반은 카드가 붙는다.
        # 카드는 prepare 단계에서만 만든다(로컬 단독 실행은 raw URL 이 없어 텍스트만).
        # dry-run 에서도 카드를 만든다 — 러너의 한글 폰트가 제대로 잡히는지
        # 실제 발행 전에 확인하려면 만들어 봐야 한다(로그에 폰트 경로가 찍힌다).
        use_card = CARD_ENABLED and interp and (a.prepare or a.dry_run) \
            and (today.toordinal() + sent) % 2 == 0
        img = build_card(n, interp, today.isoformat(), sent) if use_card else None
        print("-" * 52)
        print(text)
        print(f"[카드] {img or '없음(텍스트만)'}")
        print("-" * 52)
        plan.append({"key": _key(n), "text": text, "image_url": img})
        sent += 1
        if sent < a.count and not a.dry_run:
            time.sleep(25)      # Gemini 분당 한도 회피 + 연속 발행처럼 안 보이게

    if a.dry_run:
        log(f"[DRY-RUN] {sent}건 미리보기 — 발행하지 않았습니다")
        return
    if a.prepare:
        PLAN.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
        log(f"계획 저장: {len(plan)}건 (카드 {sum(1 for p in plan if p['image_url'])}건) "
            f"→ 커밋 후 --publish 로 발행")
        return
    for p in plan:                       # 로컬 단독 실행 경로
        pid = publish(p["text"], p["image_url"])
        _mark(p["key"], p["text"], pid)
        log(f"발행 완료: {pid}")


def _publish_planned():
    """prepare 로 만든 계획을 발행한다. 카드가 이미 레포에 올라간 뒤에 호출해야 한다."""
    if not PLAN.exists():
        log("계획 파일이 없습니다 — prepare 단계가 실패했을 수 있습니다")
        return
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    done = _posted()
    for p in plan:
        if p["key"] in done:
            log(f"이미 발행됨 — 건너뜀: {p['text'][:24]}")
            continue
        pid = publish(p["text"], p.get("image_url"))
        _mark(p["key"], p["text"], pid)
        log(f"발행 완료: {pid}{' (카드 첨부)' if p.get('image_url') else ''}")
        time.sleep(5)
    PLAN.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
