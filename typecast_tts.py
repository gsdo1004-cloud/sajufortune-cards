# -*- coding: utf-8 -*-
"""타입캐스트(Typecast) TTS + 매일 다른 성우·다른 성별 로테이션 (2026-07-17 한밝님 지시)

- API: POST https://api.typecast.ai/v1/text-to-speech (X-API-KEY, 2026-07-17 공식문서 검증)
  model=ssfm-v30(한국어 포함 37개 언어), text 1~2000자, 1글자=1크레딧(Free 월 3만)
- 키: Windows 자격증명관리자 `hanbak/global` / `TYPECAST_API_KEY` (키보관소 방식)
- 로테이션(결정론): 날짜 홀짝으로 성별 교차 + 성별 풀 내 순환
  → 연속 이틀은 성별부터 다르고, 같은 성우는 12일 주기로만 재등장
- 폴백: 키 없음/API 실패 → edge-tts(무료) — TTS 때문에 발행이 죽는 일은 없다
"""
from __future__ import annotations

import datetime as dt
import time
from pathlib import Path

API_URL = "https://api.typecast.ai/v1/text-to-speech"
MODEL = "ssfm-v30"
EDGE_VOICE = "ko-KR-SunHiNeural"   # 폴백(기존 zodiac_reels와 동일)

# ssfm-v30 한국어 성우 풀 (2026-07-17 /v2/voices 실조회로 선별 — 남6·여6)
VOICE_POOL = {
    "male": [
        ("tc_69fc0cff784968297fb45daa", "상현"),
        ("tc_694395d43f2c8d9d43e9a897", "병훈"),
        ("tc_68f0727fd62a5934102f7ec0", "민욱"),
        ("tc_685cdfad4027aeec7d097a28", "철훈"),
        ("tc_68d4b115f0486108a7eefb37", "강일"),
        ("tc_686dc43ebd6351e06ee64d74", "원우"),
    ],
    "female": [
        ("tc_69f2e455ea79fd197aa0476f", "서현"),
        ("tc_694b51e6dc12c8f4ec1a959c", "정숙"),
        ("tc_692799c46508f6b9468c54c7", "다은"),
        ("tc_691d49ccc47926d741f15913", "효은"),
        ("tc_68f9c6a72f0f04a417bb136f", "문정"),
        ("tc_68785db8ba9cd7503f27d921", "고운"),
    ],
}


def load_typecast_key() -> str | None:
    import os
    key = os.environ.get("TYPECAST_API_KEY", "").strip()
    if key:
        return key
    try:
        import keyring
        return keyring.get_password("hanbak/global", "TYPECAST_API_KEY")
    except Exception:
        return None


def pick_voice(date: dt.date) -> dict:
    """날짜 결정론 성우 선택. 짝수일=남 / 홀수일=여, 성별 풀 내 순환."""
    o = date.toordinal()
    gender = "male" if o % 2 == 0 else "female"
    pool = VOICE_POOL[gender]
    vid, name = pool[(o // 2) % len(pool)]
    return {"gender": gender, "voice_id": vid, "name": name,
            "label": f"{name}({'남' if gender == 'male' else '여'})"}


def synth_typecast(text: str, out_path: Path, voice_id: str,
                   key: str, tempo: float = 1.0) -> None:
    """1회 합성. 실패 시 예외. 200 응답 = 바이너리 오디오(mp3)."""
    import requests
    payload = {
        "voice_id": voice_id,
        "text": text[:2000],
        "model": MODEL,
        "language": "kor",
        "output": {"volume": 100, "audio_pitch": 0,
                   "audio_tempo": tempo, "audio_format": "mp3"},
    }
    r = requests.post(API_URL, json=payload, timeout=120,
                      headers={"X-API-KEY": key, "Content-Type": "application/json"})
    if r.status_code != 200:
        raise RuntimeError(f"typecast {r.status_code}: {r.text[:200]}")
    if len(r.content) < 2000:
        raise RuntimeError(f"typecast 응답 오디오가 너무 작음({len(r.content)}B)")
    out_path.write_bytes(r.content)


def synth_edge(text: str, out_path: Path, tempo: float = 1.0) -> None:
    import asyncio
    import edge_tts
    rate = f"{int(round((tempo - 1.0) * 100)) + 6:+d}%"   # 기본 +6%에 tempo 반영

    async def go():
        await edge_tts.Communicate(text, EDGE_VOICE, rate=rate).save(str(out_path))
    asyncio.run(go())


def synth(text: str, out_path: Path, date: dt.date | None = None,
          log=print, tempo: float = 1.0) -> dict:
    """내레이션 1줄 합성 — 타입캐스트 2회 → edge 폴백. 반환 {engine, voice}.

    tempo: 말 속도(0.5~2.0). 네이버 클립 90초 제한을 맞추려 자동 상향될 수 있음.
    """
    date = date or dt.date.today()
    v = pick_voice(date)
    tempo = max(0.5, min(2.0, tempo))
    key = load_typecast_key()
    if key:
        for attempt in (1, 2):
            try:
                synth_typecast(text, out_path, v["voice_id"], key, tempo=tempo)
                return {"engine": "typecast", "voice": v["label"], "tempo": tempo}
            except Exception as e:
                log(f"[WARN] typecast 시도{attempt} 실패({v['label']}): {e}")
                time.sleep(3 * attempt)
    else:
        log("[WARN] 타입캐스트 키 없음 — edge-tts 폴백")
    synth_edge(text, out_path, tempo)
    return {"engine": "edge", "voice": "SunHi(폴백)", "tempo": tempo}


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    base = dt.date(2026, 7, 18)
    print("=== 14일 성우 로테이션 ===")
    for i in range(14):
        d = base + dt.timedelta(days=i)
        print(d, pick_voice(d)["label"])
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        out = Path(__file__).parent / "_tts_test.mp3"
        r = synth("칠월 십팔일 토요일, 오늘의 띠별 운세. 내 띠는 오늘 어떤 흐름일까요?",
                  out, base)
        print("결과:", r, "| 크기:", out.stat().st_size if out.exists() else 0)
