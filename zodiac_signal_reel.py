# -*- coding: utf-8 -*-
r"""띠 지목 쇼츠 — 유튜브 운명과학TV 예약발행용 (2026-08-06)

띠 지목(zodiac_signal)은 여태 쓰레드에 카드 이미지로만 나갔다. 같은 재료로 9:16
영상을 만들어 유튜브에도 올린다. 카드 생성 방식은 Topview AI(실패 시 PIL 폴백)로
바뀌어도 카드 계약은 signal_01..02.jpg 2장으로 고정하므로 나레이션만 붙이면 된다.

TTS·길이게이트·ffmpeg 조립은 zodiac_reels.make_reel_tts 를 그대로 쓴다 —
복제하면 한쪽만 고쳐져 티 안 나게 어긋난다(그 모듈 주석의 경고).

나레이션은 카드 순서와 1:1 로 맞춘다:
  1 당일 간지 기반 훅·종합 흐름 / 2 재물·관계·건강 중 핵심 행동과 행운 요소

사용:
  python zodiac_signal_reel.py 2026-08-06            # 영상 생성
  python zodiac_signal_reel.py 2026-08-06 --meta     # 유튜브 제목·설명만 출력
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

import zodiac_signal as zsig            # noqa: E402

# ⚠️ 설명란에 URL 을 넣지 않는다 (2026-08-06 한밝님 지시).
# 쇼츠는 설명란이 접혀 링크가 눌리지 않는다 — 클릭도 안 되는 URL 은 유입에 도움이
# 안 되면서 외부 유인 신호만 남긴다. 살아 있는 통로인 프로필 링크로만 안내한다.


def narration(date_iso: str, slug: str | None = None) -> list[str]:
    """사주v6의 당일 간지·띠 지지 계산 대본을 카드 2장과 1:1로 읽는다."""
    return zsig.daily_story(date_iso, slug)["narration"]


def youtube_meta(date_iso: str, slug: str | None = None) -> dict:
    p = zsig.daily_story(date_iso, slug)
    title = f"{p['sign_ko']} 오늘의 {p['focus_label']} — {p['hook']}"
    if len(title) > 95:
        title = f"{p['sign_ko']} 오늘의 {p['focus_label']}"
    desc = (
        f"{p['caption']}\n\n"
        f"#{p['sign_ko']} #오늘의운세 #띠별운세 #사주 #운세\n\n"
        f"※ 본 콘텐츠는 정통 사주명리학을 바탕으로 한 참고용입니다."
    )
    return {
        "title": title,
        "description": desc,
        "tags": [p["sign_ko"], "오늘의운세", "띠별운세", "사주", "운세", "무료운세"],
    }


def _assert_card_contract(date_iso: str):
    """AI/PIL 어느 생성 경로든 쇼츠가 기대하는 두 파일명을 강제한다."""
    card_dir = BASE / "cards" / date_iso
    missing = [f"signal_{i:02d}.jpg" for i in range(1, 3)
               if not (card_dir / f"signal_{i:02d}.jpg").is_file()]
    if missing:
        raise FileNotFoundError(f"띠 지목 카드 계약 위반({date_iso}): {', '.join(missing)}")


def build(date_iso: str, slug: str | None = None) -> Path:
    import zodiac_reels as zr
    _assert_card_contract(date_iso)
    narrs = narration(date_iso, slug)
    out = zr.make_reel_tts(date_iso, card_stem="signal_", narrs=narrs,
                           out_name=f"{date_iso}_signal.mp4")
    meta = youtube_meta(date_iso, slug)
    (BASE / "cards" / date_iso / "signal_youtube_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def main() -> int:
    argv = [a for a in sys.argv[1:] if not a.startswith("--")]
    date_iso = argv[0] if argv else dt.date.today().isoformat()
    slug = argv[1] if len(argv) > 1 else None

    if "--meta" in sys.argv:
        print(json.dumps(youtube_meta(date_iso, slug), ensure_ascii=False, indent=2))
        return 0
    if "--narration" in sys.argv:
        for i, line in enumerate(narration(date_iso, slug), 1):
            print(f"{i}. {line}")
        return 0

    out = build(date_iso, slug)
    print(f"[OK] 띠 지목 쇼츠 → {out}")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    sys.exit(main())
