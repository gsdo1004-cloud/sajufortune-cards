# -*- coding: utf-8 -*-
"""띠별운세 쇼츠(9:16) 영상 조립 — Topview 5장 + 타입캐스트 TTS + BGM 로테이션.

2026-07-17 한밝님 지시 반영:
  - TTS = 타입캐스트, 매일 다른 성우·다른 성별 (typecast_tts.py 로테이션, edge 폴백)
  - BGM = 구글 에셋폴더 + 로컬 주파수 음악 풀에서 매일 다른 곡, 은은하게(11%)
  - 발행처 = 쓰레드 + 운명과학TV 쇼츠 (출력 파일명은 기존 reels/{date}_tts.mp4
    그대로 → GitHub Actions 쓰레드 발행 스텝 무수정 재사용)

조립 방식: 9:16 원본 → 3배 lanczos 업스케일 → zoompan 중앙 줌(교차 in/out, 떨림 금지
[[feedback_kenburns_standard]]) → 컷 길이 = 내레이션 길이 동적 → concat → BGM 믹스.

실행: python zodiac_shorts.py generate [YYYY-MM-DD]
"""
from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

import zodiac_seo as zs
import zodiac_prompt_engine as zpe
import typecast_tts

W, H = 1080, 1920
FPS = 30
NO_WINDOW = 0x08000000 if os.name == "nt" else 0   # 스케줄러 무창 실행

# ── BGM 풀 (한밝님 지정: 구글 에셋폴더 주파수 + 로컬) ────────
BGM_DIRS = [
    Path(r"G:\내 드라이브\01클로드\에셋라이브러리\bgm\251108깊은수면528비소리"),
    Path(r"G:\내 드라이브\01클로드\에셋라이브러리\bgm\251109 긍정에너지888"),
    Path(r"G:\내 드라이브\01클로드\에셋라이브러리\bgm\251109스트레스불안해소432"),
    Path(r"G:\내 드라이브\01클로드\에셋라이브러리\bgm\251112황금로파이"),
    Path(r"G:\내 드라이브\01클로드\에셋라이브러리\bgm\금전운 888황금주파수"),
    Path(r"D:\norae_mv\stock\meditation"),          # M01~M32/song.mp3 (Suno 자작)
    BASE / "bgm",                                    # 오행 5곡 (기존)
]
BGM_CACHE = BASE / "bgm_cache"
AUDIO_EXTS = {".mp3", ".wav", ".m4a"}


def log(msg: str):
    print(f"[shorts] {msg}")


def _run(cmd: list, **kw):
    return subprocess.run(cmd, check=True, capture_output=True,
                          creationflags=NO_WINDOW, **kw)


def build_bgm_pool() -> list[Path]:
    """풀 스캔(결정론적 정렬). G드라이브가 죽어 있으면 로컬만으로도 동작."""
    pool: list[Path] = []
    for d in BGM_DIRS:
        try:
            if not d.exists():
                continue
            if d.name == "meditation" and d.parent.name == "stock":
                for sub in sorted(d.glob("M*/song.mp3")):
                    if sub.stat().st_size > 400_000:   # M07 불완전(458KB) 같은 것 제외
                        pool.append(sub)
            else:
                for f in sorted(d.iterdir()):
                    if f.suffix.lower() in AUDIO_EXTS and f.stat().st_size > 400_000:
                        pool.append(f)
        except OSError as e:
            log(f"[WARN] BGM 폴더 스캔 실패({d}): {e}")
    return pool


def pick_bgm(date: dt.date) -> Path | None:
    """매일 다른 곡(결정론). G드라이브 곡은 로컬 캐시로 복사 후 사용(CFAPI 함정 회피)."""
    pool = build_bgm_pool()
    if not pool:
        log("[WARN] BGM 풀 비어있음 — 무음 진행")
        return None
    f = pool[date.toordinal() % len(pool)]
    log(f"BGM 풀 {len(pool)}곡 중 오늘: {f.name}")
    if str(f).startswith("G:"):
        try:
            BGM_CACHE.mkdir(exist_ok=True)
            cached = BGM_CACHE / f.name
            if not cached.exists() or cached.stat().st_size != f.stat().st_size:
                shutil.copy2(f, cached)
            return cached
        except OSError as e:
            log(f"[WARN] BGM 캐시 복사 실패({e}) — 로컬 폴백")
            for alt in pool:
                if not str(alt).startswith("G:"):
                    return alt
            return None
    return f


# ── 내레이션 (5컷: 표지 인트로 + 띠별 4컷) ───────────────────
def _dedup_lines(date_iso: str) -> dict:
    """zodiac_reels._oa와 동일 원리 — 관계 리드 중복 시 기조 문장으로 대체."""
    d = dt.date.fromisoformat(date_iso)
    from ganzhi_zodiac import zodiac_day
    seen, out = set(), {}
    for slug in [zs.KO_TO_SLUG[ko] for ko in zpe.ZODIAC12]:
        lead = zodiac_day(slug, d)["lead"]
        txt = lead
        if lead in seen:
            r = zs.make_reading(slug, date_iso)
            if ". " in r.overall:
                txt = r.overall.split(". ", 1)[1]
        seen.add(lead)
        out[slug] = txt
    return out


def narration_lines(date_iso: str) -> list[str]:
    d = dt.date.fromisoformat(date_iso)
    wd = ["월", "화", "수", "목", "금", "토", "일"][d.weekday()]
    R = {ko: zs.make_reading(zs.KO_TO_SLUG[ko], date_iso) for ko in zpe.ZODIAC12}
    OA = _dedup_lines(date_iso)
    lines = [f"{d.month}월 {d.day}일 {wd}요일, 오늘의 띠별 운세. "
             f"내 띠는 오늘 어떤 흐름일까요?"]
    for group in zpe.GROUPS:
        t = ""
        for ko in group:
            seg = OA[zs.KO_TO_SLUG[ko]].replace("오늘은 ", "").split(".")[0].strip()
            seg = seg.replace(" — ", ", ")
            t += f"{ko}, {seg}. "
        lines.append(t.strip())
    top = sorted(zpe.ZODIAC12, key=lambda ko: R[ko].overall_score, reverse=True)[:3]
    lines[-1] += (f" 오늘 특히 웃는 띠는 {', '.join(top)}. "
                  f"내일 운세도 이 채널에서 만나요.")
    return lines


def _dur(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "json", str(path)],
        capture_output=True, text=True, creationflags=NO_WINDOW)
    return float(json.loads(r.stdout)["format"]["duration"])


def make_shorts(date_iso: str | None = None) -> Path:
    date_iso = date_iso or zs.today_iso()
    d = dt.date.fromisoformat(date_iso)
    cards = sorted((BASE / "cards" / date_iso).glob("card_*.png"))
    if len(cards) < 5:
        raise SystemExit(f"[FAIL] Topview 카드 5장 필요, 현재 {len(cards)}장: {date_iso}")
    cards = cards[:5]

    narrs = narration_lines(date_iso)
    tmp = BASE / "cards" / date_iso / "_shorts"
    tmp.mkdir(exist_ok=True)

    voice_used = None
    clips = []
    for i, (card, narr) in enumerate(zip(cards, narrs)):
        mp3 = tmp / f"n{i}.mp3"
        info = typecast_tts.synth(narr, mp3, d, log=log)
        voice_used = voice_used or info
        L = round(_dur(mp3) + 0.7, 2)
        clip = tmp / f"c{i:02d}.mp4"
        frames = int(L * FPS)
        # 3배 lanczos 업스케일 후 중앙 zoompan(교차 in/out) — 떨림 금지 표준
        if i % 2 == 0:
            zexpr = f"min(1.0+0.0008*on,1.08)"
        else:
            zexpr = f"max(1.08-0.0008*on,1.0)"
        vf = (f"scale={W*3}:{H*3}:flags=lanczos,"
              f"zoompan=z='{zexpr}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
              f":d={frames}:s={W}x{H}:fps={FPS},format=yuv420p")
        _run(["ffmpeg", "-y", "-loop", "1", "-i", str(card), "-i", str(mp3),
              "-t", str(L), "-vf", vf, "-r", str(FPS), "-af", "apad",
              "-c:v", "libx264", "-preset", "veryfast",
              "-c:a", "aac", "-b:a", "128k", "-pix_fmt", "yuv420p", str(clip)])
        clips.append(clip)
        log(f"컷 {i+1}/5: {L}s ({info['engine']}:{info['voice']})")

    lst = tmp / "list.txt"
    lst.write_text("".join(f"file '{c.as_posix()}'\n" for c in clips), encoding="utf-8")
    out = BASE / "reels" / f"{date_iso}_tts.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
          "-c", "copy", str(out)])

    # BGM 은은하게 (매일 다른 곡, 11% + 페이드 + loudnorm)
    bgm = pick_bgm(d)
    if bgm:
        dur = _dur(out)
        fade_out = max(0.0, dur - 2.0)
        tmp_bgm = out.with_name(out.stem + "_bgm.mp4")
        try:
            _run(["ffmpeg", "-y", "-i", str(out), "-stream_loop", "-1", "-i", str(bgm),
                  "-filter_complex",
                  f"[1:a]loudnorm=I=-20:TP=-2,volume=0.11,"
                  f"afade=t=in:d=1.5,afade=t=out:st={fade_out:.2f}:d=2[bg];"
                  f"[0:a][bg]amix=inputs=2:duration=first:normalize=0[a]",
                  "-map", "0:v", "-map", "[a]", "-c:v", "copy",
                  "-c:a", "aac", "-b:a", "128k", "-t", f"{dur:.2f}", str(tmp_bgm)])
            tmp_bgm.replace(out)
            log(f"BGM 믹스 완료: {bgm.name} (11%, fade)")
        except subprocess.CalledProcessError as e:
            log(f"[WARN] BGM 믹스 실패 — TTS만 진행: {e.stderr[-200:] if e.stderr else e}")
            if tmp_bgm.exists():
                tmp_bgm.unlink()

    # 메타 저장 (유튜브 업로드·기록용)
    meta = {"date": date_iso, "voice": voice_used, "bgm": bgm.name if bgm else None,
            "duration": round(_dur(out), 1), "narration": narrs}
    (BASE / "cards" / date_iso / "shorts_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")

    for f in tmp.glob("*"):
        f.unlink()
    tmp.rmdir()
    log(f"✅ 쇼츠 완성 → {out} ({meta['duration']}초, {W}x{H}, "
        f"{voice_used['engine']}:{voice_used['voice']}, BGM={meta['bgm']})")
    return out


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    mode = sys.argv[1] if len(sys.argv) > 1 else "generate"
    di = sys.argv[2] if len(sys.argv) > 2 else None
    if mode == "generate":
        make_shorts(di)
    else:
        raise SystemExit("사용법: python zodiac_shorts.py generate [YYYY-MM-DD]")
