# -*- coding: utf-8 -*-
"""당근 광고·소식 심사 안전 필터.

근거: 당근비즈니스 업종별 심사 가이드 33번 "운세·역술 서비스" (2026-08-07 확인).
  집행 가능 — 사주·타로·작명·풍수·꿈해몽 등 운세 콘텐츠·상담 서비스
  거절 대상 — 무속 의례 표현 강조 / "100% 적중"·"전국 1위" 등 단정적 효과 표현 /
             "액운"·"삼재" 등 불안 조장 표현 / 혐오 이미지(피·뼈·칼) /
             신당·굿 장면 등 무속 의식 연상 이미지

한밝님 작업실 규칙("절대·100%·완치·무조건 금지")과 사실상 같은 문장이라
기존 카피 원칙을 그대로 쓰면 대부분 통과한다. 문제는 유튜브 대본에서 늘 쓰는
"삼재·액운"이 당근에서는 거절 사유라는 점 — 그래서 이 필터가 필요하다.

쓰는 곳: 소식 본문, 광고 소재 카피, 카탈로그 피드 상품명.
"""
from __future__ import annotations

# 카테고리별 금지어. 부분 문자열로 검사한다(한국어는 조사가 붙으므로).
BANNED: dict[str, list[str]] = {
    "단정적 효과": [
        "100%", "100 %", "백퍼", "백프로", "완벽 적중", "완전 적중",
        "전국 1위", "전국1위", "국내 1위", "국내1위", "업계 1위", "1등",
        "무조건", "절대", "반드시", "확실히", "틀림없", "보장",
        "완치", "즉시 해결", "다 맞", "적중률",
    ],
    "불안 조장": [
        "삼재", "액운", "재앙", "저주", "불행이", "큰일 나", "큰일 납",
        "망한다", "망합니다", "위험합니다", "조심하지 않으면", "닥칩니다",
        "피해야 합니다", "불운",
    ],
    "무속 연상": [
        "신당", "굿을", "굿판", "부적", "퇴마", "접신", "무당", "신점",
        "빙의", "제사상", "촛불 의식",
    ],
    "과장 수식": [
        "소름", "충격", "경악", "미친", "역대급", "대박 터",
    ],
}

# 자동으로 순화할 수 있는 것만 치환한다. 나머지는 사람이 고쳐야 한다.
SOFTEN: dict[str, str] = {
    "삼재": "흐름이 크게 바뀌는 시기",
    "액운": "막히는 흐름",
    "불운": "잘 안 풀리는 흐름",
    "무조건": "대체로",
    "절대": "좀처럼",
    "반드시": "되도록",
    "확실히": "분명히",
    "적중률": "만족도",
    "소름": "인상적",
    "충격": "뜻밖",
    "역대급": "손꼽히는",
}

# 상품 자체가 당근 심사에 걸리는 SKU — 피드·소재에서 제외한다.
# salpuri_samjae("삼재·살풀이")는 상품명에 거절 키워드가 그대로 들어 있다.
BLOCKED_PRODUCT_IDS: set[str] = {"salpuri_samjae"}


def check(text: str) -> list[tuple[str, str]]:
    """걸린 항목을 [(카테고리, 금지어)] 로 돌려준다. 빈 리스트면 통과."""
    hits: list[tuple[str, str]] = []
    low = text.lower()
    for cat, words in BANNED.items():
        for w in words:
            if w.lower() in low:
                hits.append((cat, w))
    return hits


def soften(text: str) -> str:
    """자동 순화 가능한 표현만 바꾼다. 치환표에 없는 금지어는 그대로 남는다."""
    out = text
    for bad, good in SOFTEN.items():
        out = out.replace(bad, good)
    return out


def assert_safe(text: str, where: str = "본문") -> None:
    """통과 못 하면 멈춘다. 심사 반려를 사후에 겪지 않으려면 여기서 죽는 게 낫다."""
    # soften 을 먼저 돌려도 남는 게 있으면 사람이 판단해야 한다.
    hits = check(text)
    if hits:
        lines = "\n".join(f"  · [{cat}] {w}" for cat, w in hits)
        raise ValueError(f"{where}에 당근 심사 거절 표현이 있습니다:\n{lines}")


def product_allowed(product_id: str, title: str) -> bool:
    """카탈로그 피드에 실어도 되는 상품인지."""
    if product_id in BLOCKED_PRODUCT_IDS:
        return False
    return not check(title)


if __name__ == "__main__":
    import sys

    sys.stdout.reconfigure(encoding="utf-8")
    samples = [
        "오늘 재물운이 좋은 띠를 정리했어요. 무료로 확인해 보세요.",
        "삼재가 낀 해라 액운을 100% 막아드립니다",
    ]
    for s in samples:
        hits = check(s)
        print(f"\n입력: {s}")
        print("  판정:", "통과" if not hits else f"거절 {hits}")
        if hits:
            print("  순화:", soften(s))
