# -*- coding: utf-8 -*-
"""답글 코치 — 매일 아침 '오늘 어디에 뭘 답글 달지' 한 장 (2026-07-31 신설).

왜 이게 필요한가
----------------
팔로워 15명. 쓰레드는 대화 플랫폼이라 도달이 '발행'이 아니라 **'답글'에서** 나온다.
이 계정은 하루 4번 방송하고 남의 글에는 0회 참여한다 — 확성기만 있고 대화가 없다.
남의 글 답글은 사람이 직접 써야 한다. 그 **결정 피로만** 없애주는 게 이 스크립트다.

🚨 자동 답글이 아니다. 앞으로도 아니어야 한다.
   인스타 계정이 **링크 자동댓글 대량 살포로 이미 제재**당했다. 같은 실수를 하면
   이 계정도 잃는다. 여기서는 어디에 갈지·무슨 각도로 쓸지만 알려준다.
   읽고 쓰는 건 사람이 한다.

왜 '오늘 답글 달 글 10개 링크'가 아닌가 (실측)
--------------------------------------------
남의 쓰레드 글을 가져올 합법적 경로가 지금 없다.
  - Threads keyword_search API → `threads_keyword_search` 권한 승인 필요. 안 받았다.
    (받는 순간 자동 살포의 유혹이 생기므로 받지 않는 게 낫다)
  - 프로필 RSS(`/@user/rss`) → **404**. 존재하지 않는다(2026-07-31 실측).
  - 스크래핑 → Meta 자동화 정책 위반. 계정 위험.
그래서 **검색어 + 각도 + 타깃 목록**을 준다. 앱에서 사람이 연다.

실행:
  python threads_reply_coach.py            # 화면 출력 + 메일
  python threads_reply_coach.py --no-mail  # 화면만
타깃 계정을 늘리려면 `reply_targets.txt` 에 한 줄에 하나씩 적는다(@ 포함/생략 무관).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
TARGETS = BASE / "reply_targets.txt"
STORE = BASE / "threads_insights.json"
ACCOUNT = BASE / "threads_account.json"
OUT = BASE / "threads_reply_coach.md"

# 앱 검색창에 그대로 넣을 말. 사주·AI 교집합을 노린다.
# 날짜로 회전시켜 매일 다른 물을 판다 — 같은 검색어만 보면 같은 사람만 만난다.
KEYWORDS = [
    ["사주", "올해 운세", "AI 사주"],
    ["타로", "챗GPT", "궁합"],
    ["일주", "제미나이", "운세 앱"],
    ["명리", "AI 상담", "신점"],
    ["대운", "챗GPT 상담", "사주 후기"],
    ["오늘의 운세", "AI 심리테스트", "관상"],
    ["점집", "클로드", "무료 운세"],
]

# 답글 각도. "좋아요!" "공감합니다"는 알고리즘에도 사람에게도 아무 값이 없다.
ANGLES = [
    ("질문형", "상대가 답하고 싶어지는 걸 묻는다",
     "이 해석은 어느 유파 기준인가요? 저는 다르게 배웠어서요"),
    ("경험형", "내 경험을 한 줄. 홍보 아님",
     "저도 같은 일주인데 저는 반대로 나왔습니다. 사람마다 다르더군요"),
    ("반론형", "부드럽게 다른 각도. 시비조 금지",
     "그 부분은 저는 좀 다르게 봅니다. 그렇게 보는 이유가 있는데요"),
    ("보충형", "상대 글에 없는 걸 하나 더 얹는다",
     "덧붙이면 그 시기는 계절도 같이 봐야 맞더라고요"),
]

RULES = [
    "링크 절대 금지. 사주 사이트·앱 언급도 금지. 프로필로 알아서 온다",
    "'좋아요!' '공감합니다' 같은 빈 답글 금지 — 도달에 도움이 안 된다",
    "내 글 홍보 금지. 답글에서 홍보하면 그 계정 사람들이 차단한다",
    "하루 5~10개면 충분하다. 그 이상은 스팸으로 잡힌다",
    "같은 계정에 하루 2개 이상 달지 않는다",
]


def _followers() -> tuple[int | None, int | None]:
    """(현재 팔로워, 어제 대비 증감). 측정 루프가 남긴 값을 그대로 읽는다."""
    try:
        d = json.loads(ACCOUNT.read_text(encoding="utf-8"))
    except Exception:
        return None, None
    hist = d.get("history") or []
    cur = (d.get("latest") or {}).get("followers_count")
    prev = hist[-2].get("followers_count") if len(hist) >= 2 else None
    delta = (cur - prev) if (cur is not None and prev is not None) else None
    return cur, delta


def _yesterday_replies() -> int | None:
    """어제 내 글에 달린 답글 수 합. 답글 활동이 대화를 끌어왔는지 보는 지표."""
    try:
        d = json.loads(STORE.read_text(encoding="utf-8"))
    except Exception:
        return None
    total = 0
    for r in (d.get("posts") or {}).values():
        snaps = [s for s in r.get("snapshots", [])
                 if s.get("age_h") is not None and s["age_h"] <= 48]
        if snaps:
            total += snaps[-1].get("replies", 0) or 0
    return total


def _targets() -> list[str]:
    if not TARGETS.exists():
        return []
    return [ln.strip().lstrip("@") for ln in
            TARGETS.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("#")]


def build(today: dt.date) -> str:
    idx = today.toordinal()
    kws = KEYWORDS[idx % len(KEYWORDS)]
    angle = ANGLES[idx % len(ANGLES)]
    cur, delta = _followers()
    reps = _yesterday_replies()
    tg = _targets()

    L = [f"# 답글 코치 — {today:%Y-%m-%d} ({'월화수목금토일'[today.weekday()]})", ""]

    # 어제 성과부터. 숫자가 안 움직이면 방법을 바꿔야 한다는 신호다.
    if cur is not None:
        d = f" ({delta:+d})" if delta is not None else ""
        L += [f"**어제까지 팔로워 {cur}명{d}**"]
    if reps is not None:
        L += [f"최근 48시간 내 글에 달린 답글 합계 **{reps}개**"]
    L += ["", "---", "", "## 오늘 15분", "",
          "쓰레드 앱 검색창에 아래를 넣고, 최근 글에 답글 **5개**를 단다.", ""]
    for k in kws:
        L.append(f"- `{k}`")

    if tg:
        L += ["", "### 오늘 볼 계정 (회전)", ""]
        for i in range(min(3, len(tg))):
            L.append(f"- @{tg[(idx + i) % len(tg)]}")
    else:
        L += ["", "> `reply_targets.txt` 에 자주 보는 계정을 한 줄에 하나씩 적어두면",
              "> 매일 3개씩 돌아가며 띄워드립니다. (아직 비어 있습니다)"]

    L += ["", "---", "", f"## 오늘의 각도 — {angle[0]}", "",
          f"{angle[1]}", "", f"> 예: {angle[2]}", "",
          "---", "", "## 지킬 것", ""]
    L += [f"- {r}" for r in RULES]
    L += ["", "---", "",
          "왜 이걸 하나: 쓰레드는 대화가 도달을 만든다. 큰 계정 글에 제대로 된 답글을",
          "달면 그쪽 팔로워에게 내가 노출된다. 팔로워 15명이 뚫을 수 있는 유일한 문이다.",
          "", "🚨 자동화하지 않는다. 인스타는 자동 댓글 살포로 제재당했다."]
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-mail", action="store_true")
    ap.add_argument("--date", default="", help="YYYY-MM-DD (기본 오늘)")
    a = ap.parse_args()

    today = dt.date.fromisoformat(a.date) if a.date else dt.date.today()
    body = build(today)
    OUT.write_text(body, encoding="utf-8")
    print(body)

    if not a.no_mail:
        try:
            import zodiac_alert
            ok = zodiac_alert.alert(f"답글 코치 {today:%m/%d}", body)
            print(f"\n[메일] {'발송' if ok else '실패 — 화면 출력으로 대체'}")
        except Exception as e:
            # 메일이 안 나가도 코치 카드 자체는 파일로 남는다. 여기서 죽이지 않는다.
            print(f"\n[메일] 건너뜀({type(e).__name__}: {str(e)[:60]}) — {OUT.name} 확인")
    return 0


if __name__ == "__main__":
    sys.exit(main())
