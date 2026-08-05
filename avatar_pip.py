"""릴스에 PNGTuber 아바타를 PIP로 얹는다 — TTS 보이스 성별에 맞춰 자동 선택.

**자산을 리포에 번들했다(2026-08-05).** GitHub Actions 러너에는 G드라이브가 없어
아바타가 통째로 빠지고 있었다. `avatar/` 에 프레임 8장(4.4MB)과 합성 스크립트
3개를 넣어, 러너에서도 로컬과 똑같이 아바타가 들어간다.
합성 스크립트는 표준 라이브러리 + ffmpeg만 쓰므로 pip 추가 설치가 없다.

  avatar/frames/male|female/mouth_*_nobg.png   배경 제거된 입모양 4단계
  avatar/lib/pngtuber_shorts_pip.py 외 2개     합성 로직(플랫폼 UI 안전영역·하단 페이드)
  avatar/state/                                위치 로테이션 상태 파일 자리

**아바타 세트 규칙 (한밝님 확정)**
  합성 음성(Supertonic·Edge)에는 **한복 입은 젊은 남녀**만 쓴다.
    남 → frames/male   (하늘색 한복)   여 → frames/female (한복)
  중년 남성 세트는 한밝님 본인 목소리 전담이라 아예 번들하지 않았다.

배경 제거본(_nobg)을 쓴다. 배경 있는 원본을 쓰면 흰 사각형이 통째로 얹힌다.
실패해도 False 만 돌려준다 — 아바타 때문에 발행을 멈출 이유가 없다.

환경변수:
  ZODIAC_AVATAR      1이면 합성, 0이면 건너뜀 (기본 0)
  SUPERTONIC_VOICE   보이스 이름. 첫 글자 M/F 로 성별을 판단 (기본 M2)
  AVATAR_ROOT        번들 대신 외부 자산을 쓸 때만 지정
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
BUNDLE = BASE / "avatar"

# 외부(G드라이브) 자산 — 번들이 없을 때만 쓴다
EXT_ROOT = Path(os.environ.get("AVATAR_ROOT", "").strip() or
                r"G:\내 드라이브\01클로드\아바타\png tuber model")
EXT_SCRIPT = Path(r"G:\내 드라이브\01클로드\작업폴더\tts_pipeline\track_a_sellfarm\pngtuber_shorts_pip.py")

MOUTH_FILES = ["mouth_0_closed_nobg.png", "mouth_1_slight_nobg.png",
               "mouth_2_half_nobg.png", "mouth_3_wide_nobg.png"]


def enabled() -> bool:
    return os.environ.get("ZODIAC_AVATAR", "0").strip() == "1"


def _is_female(voice: str | None = None) -> bool:
    v = (voice or os.environ.get("SUPERTONIC_VOICE", "M2")).strip().upper()
    return v.startswith("F")


def resolve(voice: str | None = None) -> tuple[Path, Path, Path] | None:
    """(합성 스크립트, 프레임 폴더, 상태 폴더). 없으면 None."""
    female = _is_female(voice)
    bundled = BUNDLE / "lib" / "pngtuber_shorts_pip.py"
    if bundled.exists():
        return (bundled,
                BUNDLE / "frames" / ("female" if female else "male"),
                BUNDLE / "state")
    if EXT_SCRIPT.exists():
        return (EXT_SCRIPT,
                EXT_ROOT / ("frames_female_hanbok" if female else "frames_shorts_young"),
                EXT_ROOT.parent / "pip_pool")
    return None


def apply(video_path: Path, voice: str | None = None) -> bool:
    """완성된 mp4 에 아바타를 합성한다(in-place)."""
    got = resolve(voice)
    if not got:
        print("  [아바타] 합성 스크립트 없음 — 건너뜀")
        return False
    script, frames_dir, pool = got

    frames = [frames_dir / f for f in MOUTH_FILES]
    missing = [f.name for f in frames if not f.exists()]
    if missing:
        print(f"  [아바타] 프레임 없음(건너뜀, {frames_dir}): {missing}")
        return False
    pool.mkdir(parents=True, exist_ok=True)

    try:
        r = subprocess.run(
            [sys.executable, str(script), str(video_path),
             "--frames", *[str(f) for f in frames],
             "--pool", str(pool)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=1800,
        )
        if r.returncode == 0:
            kind = "번들" if str(script).startswith(str(BUNDLE)) else "외부"
            print(f"  [아바타] 합성 완료 ({kind}, {frames_dir.name})")
            return True
        print(f"  [아바타] 실패 (exit {r.returncode}): {(r.stderr or '')[-400:]}")
    except Exception as e:
        print(f"  [아바타] {e}")
    return False
