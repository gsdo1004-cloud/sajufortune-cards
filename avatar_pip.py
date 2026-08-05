"""릴스에 PNGTuber 아바타를 PIP로 얹는다 — TTS 보이스 성별에 맞춰 자동 선택.

G드라이브의 `pngtuber_shorts_pip.py` 를 호출한다. 그 스크립트에는 유튜브 쇼츠·
네이버 클립·틱톡 3개 플랫폼 UI 안전영역 실측값과 아바타 하단 알파 페이드가
이미 잡혀 있어서 여기서 다시 만들 이유가 없다. 원본 mp4 를 제자리에서 교체한다.

**아바타 세트 규칙 (2026-08-05 한밝님 확정)**
  합성 음성(Supertonic·Edge)에는 **한복 입은 젊은 남녀**만 쓴다.
    남 → frames_shorts_young   (하늘색 한복, 세로 720x1280)
    여 → frames_female_hanbok  (한복, 세로 720x1280)
  중년 남성 세트(frames_male_hanbok·frames_hanbok_v2)는 **한밝님 본인 목소리
  전담**이라 합성 음성에 붙이지 않는다. 가로 1280x720이라 비율도 안 맞는다.

배경 제거본(_nobg)을 쓴다. 배경 있는 원본을 쓰면 흰 사각형이 통째로 얹힌다.

GitHub Actions 러너에는 G드라이브도 아바타 자산도 없다. 그런 환경에서는 조용히
False 를 돌려주고 영상은 아바타 없이 그대로 둔다 — 발행을 멈출 이유가 아니다.

환경변수:
  ZODIAC_AVATAR      1이면 합성, 0이면 건너뜀 (기본 0)
  AVATAR_ROOT        아바타 자산 루트
  AVATAR_SET_MALE    남성 프레임 폴더명 (기본 frames_shorts_young)
  AVATAR_SET_FEMALE  여성 프레임 폴더명 (기본 frames_female_hanbok)
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

AVATAR_ROOT = Path(os.environ.get("AVATAR_ROOT", "").strip() or
                   r"G:\내 드라이브\01클로드\아바타\png tuber model")
PIP_SCRIPT = Path(os.environ.get("AVATAR_PIP_SCRIPT", "").strip() or
                  r"G:\내 드라이브\01클로드\작업폴더\tts_pipeline\track_a_sellfarm\pngtuber_shorts_pip.py")

SET_MALE = os.environ.get("AVATAR_SET_MALE", "").strip() or "frames_shorts_young"
SET_FEMALE = os.environ.get("AVATAR_SET_FEMALE", "").strip() or "frames_female_hanbok"
OWNER_ONLY_SETS = {"frames_male_hanbok", "frames_hanbok_v2"}

MOUTH_FILES = ["mouth_0_closed_nobg.png", "mouth_1_slight_nobg.png",
               "mouth_2_half_nobg.png", "mouth_3_wide_nobg.png"]


def enabled() -> bool:
    return os.environ.get("ZODIAC_AVATAR", "0").strip() == "1"


def frame_set_for_voice(voice: str | None = None) -> Path:
    """보이스 이름 첫 글자로 성별을 판단해 프레임 폴더를 고른다."""
    voice = (voice or os.environ.get("SUPERTONIC_VOICE", "M2")).strip().upper()
    female = voice.startswith("F")
    name = SET_FEMALE if female else SET_MALE
    if name in OWNER_ONLY_SETS:
        name = "frames_female_hanbok" if female else "frames_shorts_young"
        print(f"  [아바타] 한밝님 목소리 전담 세트는 합성 음성에 못 쓴다 → {name}")
    return AVATAR_ROOT / name


def apply(video_path: Path, voice: str | None = None) -> bool:
    """완성된 mp4 에 아바타를 합성한다(in-place). 실패해도 영상은 멀쩡하다."""
    if not PIP_SCRIPT.exists():
        print(f"  [아바타] 스크립트 없음(건너뜀): {PIP_SCRIPT}")
        return False

    frames_dir = frame_set_for_voice(voice)
    frames = [frames_dir / f for f in MOUTH_FILES]
    missing = [f.name for f in frames if not f.exists()]
    if missing:
        print(f"  [아바타] 프레임 없음(건너뜀, {frames_dir.name}): {missing}")
        return False

    try:
        r = subprocess.run(
            [sys.executable, str(PIP_SCRIPT), str(video_path),
             "--frames", *[str(f) for f in frames]],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=1200,
        )
        if r.returncode == 0:
            print(f"  [아바타] 합성 완료 ({frames_dir.name})")
            return True
        print(f"  [아바타] 실패 (exit {r.returncode}): {(r.stderr or '')[-300:]}")
    except Exception as e:
        print(f"  [아바타] {e}")
    return False
