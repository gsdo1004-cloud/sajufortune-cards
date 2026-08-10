# -*- coding: utf-8 -*-
r"""띠 지목 쇼츠 — 유튜브 운명과학TV 예약발행용 (2026-08-06)

띠 지목(zodiac_signal)은 여태 쓰레드에 카드 이미지로만 나갔다. 같은 재료로 9:16
영상을 만들어 유튜브에도 올린다. 카드 생성 방식은 Topview AI(실패 시 PIL 폴백)로
바뀌어도 카드 계약은 signal_01..05.jpg 5장으로 고정하므로 나레이션만 붙이면 된다.

TTS·길이게이트·ffmpeg 조립은 zodiac_reels.make_reel_tts 를 그대로 쓴다 —
복제하면 한쪽만 고쳐져 티 안 나게 어긋난다(그 모듈 주석의 경고).

나레이션은 카드 순서와 1:1 로 맞춘다:
  1 표지(띠·해당 생년·훅) / 2 성향 / 3 인용+다리 / 4 전환점 / 5 마무리

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
import zodiac_seo as zs                 # noqa: E402  (SLUG_TO_INFO 보유 모듈)

# ⚠️ 설명란에 URL 을 넣지 않는다 (2026-08-06 한밝님 지시).
# 쇼츠는 설명란이 접혀 링크가 눌리지 않는다 — 클릭도 안 되는 URL 은 유입에 도움이
# 안 되면서 외부 유인 신호만 남긴다. 살아 있는 통로인 프로필 링크로만 안내한다.


def _parts(date_iso: str, slug: str | None = None) -> dict:
    """카드가 쓰는 것과 같은 재료를 같은 규칙으로 뽑는다(어긋나면 자막과 말이 따로 논다)."""
    slug = slug or zsig.sign_of(date_iso)
    d = dt.date.fromisoformat(date_iso)
    sign_ko = zs.SLUG_TO_INFO[slug][1]
    if not sign_ko.endswith("띠"):
        sign_ko += "띠"

    angle = zsig.angle_of(date_iso)
    trait, quote, turn = zsig.TRAITS[slug][angle]
    years = zsig.pick_years(slug, date_iso)
    hook = zsig.HOOKS[d.toordinal() % len(zsig.HOOKS)].format(sign=sign_ko)
    bridges = zsig.BRIDGES[angle]
    bridge = bridges[d.toordinal() % len(bridges)]
    cta = zsig.CTA_POOL[d.toordinal() % len(zsig.CTA_POOL)].format(sign=sign_ko)
    return {"slug": slug, "sign_ko": sign_ko, "years": years, "hook": hook,
            "trait": trait, "quote": quote, "bridge": bridge, "turn": turn, "cta": cta}


def narration(date_iso: str, slug: str | None = None) -> list[str]:
    """카드 5장과 1:1 로 맞춘 나레이션. 마지막 줄에 프로필 안내를 붙인다 —
    쇼츠에서 링크가 눌리지 않으므로 말로 안내하는 것 말고는 통로가 없다."""
    p = _parts(date_iso, slug)
    years_read = ", ".join(f"{y}년생" for y in p["years"])
    return [
        f"{p['sign_ko']}, {years_read}. {p['hook']}",
        p["trait"],
        f"{p['quote']} {p['bridge']}",
        p["turn"],
        f"{p['cta']} 오늘 내 사주 기준 운세는 프로필 링크에서 무료로 보실 수 있습니다.",
    ]


def youtube_meta(date_iso: str, slug: str | None = None) -> dict:
    p = _parts(date_iso, slug)
    years_txt = " · ".join(p["years"])
    title = f"{p['sign_ko']} {years_txt} — {p['hook']}"
    if len(title) > 95:
        title = f"{p['sign_ko']} {years_txt} 오늘의 운세"
    desc = (
        f"{p['hook']}\n\n"
        f"{p['trait']}\n\n"
        f"{p['quote']}\n{p['bridge']}\n\n"
        f"{p['turn']}\n\n"
        f"👉 내 사주 기준 오늘 운세와 사주 유형(살림꾼·해결사·재주꾼 …)은\n"
        f"   채널 프로필 링크에서 무료로 확인하실 수 있습니다.\n"
        f"   생년월일만 넣으시면 바로 나옵니다.\n\n"
        f"#{p['sign_ko']} #오늘의운세 #띠별운세 #사주 #운세\n\n"
        f"※ 본 콘텐츠는 정통 사주명리학을 바탕으로 한 참고용입니다."
    )
    return {
        "title": title,
        "description": desc,
        "tags": [p["sign_ko"], "오늘의운세", "띠별운세", "사주", "운세", "무료운세"],
    }


def _assert_card_contract(date_iso: str):
    """AI/PIL 어느 생성 경로든 쇼츠가 기대하는 다섯 파일명을 강제한다."""
    card_dir = BASE / "cards" / date_iso
    missing = [f"signal_{i:02d}.jpg" for i in range(1, 6)
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
