"""Supertonic 3 로컬 TTS 어댑터 — 오프라인·무제한·무료.

zodiac_reels / zodiac_shorts 의 Edge TTS 자리를 대신한다. 실패하면 호출부가
Edge 로 폴백하므로, 이 모듈은 "되면 쓰고 안 되면 조용히 물러난다".

왜 Supertonic인가: 한밝님 청취 판단으로 Edge보다 톤이 낫다(2026-08-05).
한국어를 120자 단위로 잘라 개별 합성 후 이어붙이는 구조라 긴 나레이션에서도
후반부가 무너지지 않는다. 회사 PC 실측 RTF 0.15(CPU only).

모델(382MB)은 GitHub에 못 올린다(vector_estimator 단일 파일만 244MB).
그래서 G드라이브 보관본을 먼저 찾고, 없으면 HF에서 자동으로 받는다 —
GitHub Actions 러너에는 G드라이브가 없으므로 이 폴백이 필수다.

환경변수:
  SUPERTONIC_DIR     모델 폴더 (기본: G드라이브 보관본)
  SUPERTONIC_VOICE   보이스 M1~M5 / F1~F5 (기본 M2)
  SUPERTONIC_OFF     1이면 아예 쓰지 않음 (Edge로 되돌릴 때)
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

MODEL_DIR = os.environ.get("SUPERTONIC_DIR", "").strip() or \
    r"G:\내 드라이브\01클로드\작업폴더\tts_pipeline\supertonic\supertonic-3"
VOICE = os.environ.get("SUPERTONIC_VOICE", "").strip() or "M2"

_ENGINE = None
_FAILED = False  # 한 번 실패하면 매 컷마다 재시도하지 않는다


def available() -> bool:
    return os.environ.get("SUPERTONIC_OFF", "0").strip() != "1" and not _FAILED


def _engine():
    global _ENGINE
    if _ENGINE is None:
        from supertonic import TTS
        if Path(MODEL_DIR).exists():
            _ENGINE = TTS(model_dir=MODEL_DIR, auto_download=False)
        else:
            print("  [Supertonic] 모델 폴더 없음 → HF 자동 다운로드(최초 1회, 약 400MB)")
            _ENGINE = TTS(auto_download=True)
    return _ENGINE


def synth(text: str, out_mp3: Path, speed: float = 1.2) -> bool:
    """나레이션 한 덩어리를 mp3로. 성공하면 True.

    speed 는 배율(1.0=기본). 호출부의 Edge식 '+N%' 는 1 + N/100 으로 환산해 넘긴다.
    """
    global _FAILED
    if not available():
        return False
    try:
        eng = _engine()
        style = eng.get_voice_style(voice_name=VOICE)
        wav_path = Path(out_mp3).with_suffix(".st.wav")
        wav, _ = eng.synthesize(text=text, voice_style=style, lang="ko",
                                total_steps=8, speed=speed)
        eng.save_audio(wav, str(wav_path))
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(wav_path), "-c:a", "libmp3lame",
             "-b:a", "128k", str(out_mp3)],
            capture_output=True, timeout=120,
        )
        wav_path.unlink(missing_ok=True)
        return Path(out_mp3).exists() and Path(out_mp3).stat().st_size > 1000
    except Exception as e:
        print(f"  [Supertonic] 사용 불가 → Edge 폴백: {e}")
        _FAILED = True
    return False
