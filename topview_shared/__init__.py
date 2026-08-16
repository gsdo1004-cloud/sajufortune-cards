# -*- coding: utf-8 -*-
"""Topview REST 클라이언트 — 레포 동봉본 (vendored).

원본: ~/.claude/skills/topview-skill/scripts/shared/ (2026-07-17 판, 무수정 사본)

[2026-08-16] 왜 레포에 넣었나
  zodiac_topview.py 가 원본 스킬 경로만 sys.path 에 얹고 `from shared.client import ...`
  하던 탓에, GitHub Actions 러너(~/.claude/skills 가 없다)에서 import 단계부터 죽었다.
  8/11~8/16 엿새 동안 '띠 지목 데일리' 워크플로의 첫 스텝이 ModuleNotFoundError 로
  넘어가 카드·쇼츠·유튜브·Threads 발행이 통째로 0건이었다.
  zodiac_signal_card.build() 의 PIL 폴백은 import 시점 크래시라 닿지도 못했다.

원본을 고치는 대신 사본을 두는 이유 — 스킬은 개인 PC 자산이라 러너가 볼 수 없다.
원본이 갱신되면 이 폴더도 같이 갱신해야 한다(현재 두 곳 모두 2026-07-17 판).
자격증명은 환경변수 TOPVIEW_UID/TOPVIEW_API_KEY 우선이라 러너에서 그대로 동작한다.
"""

from .config import load_config
from .client import TopviewClient, TopviewError

__all__ = ["load_config", "TopviewClient", "TopviewError"]
