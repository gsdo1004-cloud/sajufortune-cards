# -*- coding: utf-8 -*-
"""띠별운세 쇼츠(9:16) 영상 조립 — Topview 기본 4장 + 타입캐스트 TTS + BGM 로테이션.

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
# 영상 조립·임시 클립은 D:에서 수행한다. 카드 원본은 기존 C: 저장소를 유지하고,
# daily 파이프라인이 GitHub Actions에 필요한 게시 전달본만 별도로 복사한다.
VIDEO_ROOT = Path(os.environ.get("ZODIAC_VIDEO_ROOT", r"D:\shorts_work\zodiac_daily"))

import zodiac_seo as zs
import zodiac_prompt_engine as zpe
import typecast_tts

W, H = 1080, 1920
FPS = 30
NO_WINDOW = 0x08000000 if os.name == "nt" else 0   # 스케줄러 무창 실행

# ── PNGTuber 반응형 아바타 PIP (2026-07-20 연결) ──────────────
# 근거: G:\내 드라이브\01클로드\작업폴더\집PC이관_PNGTuber_2026-07-20\README_인수인계.md
# "숏폼(남녀 목소리 번갈아) = 그날 TTS 목소리 성별에 맞춰 아바타도 교체" — 타입캐스트
# 성별은 날짜가 아니라 **실제로 생성된 TTS 결과**를 기준으로 고른다.
# 타입캐스트 실패 시 Edge 여성 음성으로 폴백하므로, 날짜만 보면 어긋날 수 있다.
PNGTUBER_DIR = Path(r"D:\automation_control\runtimes\unmyeong\tts_pipeline\track_a_sellfarm")
PNGTUBER_AVATAR_ROOT = Path(r"D:\norae_mv\assets\pngtuber")
PNGTUBER_PERSONA = {"male": "frames_shorts_young", "female": "frames_female_hanbok"}
PNGTUBER_MOUTH_FILES = ["mouth_0_closed_nobg.png", "mouth_1_slight_nobg.png",
                        "mouth_2_half_nobg.png", "mouth_3_wide_nobg.png"]


def _apply_pngtuber_pip(video_path: Path, date: dt.date,
                         voice_info: dict | None = None) -> None:
    """쇼츠에 PNGTuber 반응형 아바타 PIP를 얹는다. 절대 예외를 던지지 않음 —
    G드라이브 스톨·프레임 누락 등 무엇이 실패해도 쇼츠 조립 자체는 계속 진행한다
    (human_touch_pip.apply_pip과 동일한 '빌드를 멈추지 않는다' 원칙).
    voice_info가 있으면 실제 TTS 성별을 사용하고, 구형 호출만 날짜 기준으로 폴백한다."""
    try:
        if str(PNGTUBER_DIR) not in sys.path:
            sys.path.insert(0, str(PNGTUBER_DIR))
        import pngtuber_shorts_pip as pnt_pip
        # 실제 TTS가 반환한 성별을 최우선으로 사용한다. 기존 날짜 홀짝 방식은
        # 타입캐스트 실패 후 SunHi(여성)로 폴백할 때 남성 PNG튜버를 고르는 버그가 있었다.
        gender = (voice_info or {}).get("gender")
        gender_source = "실제 TTS"
        if gender not in PNGTUBER_PERSONA:
            gender = typecast_tts.pick_voice(date)["gender"]
            gender_source = "날짜 폴백"
        persona = PNGTUBER_PERSONA[gender]
        frame_dir = PNGTUBER_AVATAR_ROOT / persona
        frames = [frame_dir / f for f in PNGTUBER_MOUTH_FILES]
        missing = [f for f in frames if not f.exists()]
        if missing:
            log(f"[WARN] PNGTuber 프레임 없음({persona}) — PIP 생략: {missing[0]}")
            return
        info = pnt_pip.compose(str(video_path), [str(f) for f in frames])
        log(f"PNGTuber PIP 완료: {persona}({gender}, {gender_source}), "
            f"{info['위치']} 위치, {info['길이']}초")
    except Exception as e:
        log(f"[WARN] PNGTuber PIP 실패(쇼츠는 그대로 진행): {type(e).__name__}: {e}")

# 네이버 클립 = 1분 30초 이내만 업로드 가능 (한밝님 2026-07-17). 초과하면 채널 하나를
# 통째로 못 쓴다. 88초를 목표로 잡아 인코딩 오차·패딩 여유를 둔다.
# 2026-07-26: 네이버 클립 제한이 90초라 상한을 그 값에 붙여 두니 87초짜리가 통과했고,
# 다른 경로(zodiac_reels)에서 만든 95초짜리까지 섞여 나갔다. 상한을 85초로 낮춰 여유를 둔다.
CLIP_LIMIT = 85.0
TARGET_SEC = 80.0

# TTS 말 속도 (1.0 = 기본). 2026-07-26 도입.
#   LONG  = 95초판(스레드·틱톡·네이버클립). 시니어 시청자를 배려해 +12% 선에서 멈춘다.
#   SHORT = 20초판(유튜브 쇼츠). 짧고 임팩트가 중요해 더 빠르게 간다.
# 길이 게이트가 필요하면 여기서 시작해 상한 1.35 까지 자동으로 더 올라간다.
LONG_TEMPO = 1.12
SHORT_TEMPO = 1.25
PAD = 0.7          # 컷당 꼬리 여백

# ── BGM 풀 (한밝님 지정: 구글 에셋폴더 주파수 + 로컬) ────────
BGM_DIRS = [
    Path(r"E:\automation_store\unmyeong\bgm\251108깊은수면528비소리"),
    Path(r"E:\automation_store\unmyeong\bgm\251109 긍정에너지888"),
    Path(r"E:\automation_store\unmyeong\bgm\251109스트레스불안해소432"),
    Path(r"E:\automation_store\unmyeong\bgm\251112황금로파이"),
    Path(r"E:\automation_store\unmyeong\bgm\금전운 888황금주파수"),
    Path(r"D:\norae_mv\stock\meditation"),          # M01~M32/song.mp3 (Suno 자작)
    Path(r"E:\automation_store\unmyeong\bgm"),     # 로컬 보관소
]
BGM_CACHE = VIDEO_ROOT / "bgm_cache"
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
            BGM_CACHE.mkdir(parents=True, exist_ok=True)
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


# ── 내레이션 (4컷: 띠별 3그룹 + 12띠요약) ───────────────────
#
# 홈페이지와 같은 기준을 사용한다. sajufortune.kr(사주v6)의 오늘의 띠운세는
# 매일 간지(day pillar)를 먼저 정하고, 그 일진과 띠의 합·충·형·파·해·오행
# 관계로 기조를 계산한다. zodiac_seo.make_reading()이 그 계산 결과를 카드·쇼츠
# 공통으로 제공하므로, 영상이 별도의 창작 운세를 만들지 않게 한다.
SCRIPT_MODES = [
    {"key": "overall", "intro": "내 띠와 오늘의 간지가 만나는 흐름부터 살펴봅니다.", "field": "overall"},
    {"key": "money", "intro": "오늘은 재물과 일의 흐름을 먼저 확인해 보겠습니다.", "field": "money"},
    {"key": "love", "intro": "오늘은 사람 사이의 말과 타이밍이 중요한 날입니다.", "field": "love"},
    {"key": "health", "intro": "오늘은 무리하지 않는 방법까지 함께 짚어드립니다.", "field": "health"},
    {"key": "action", "intro": "오늘 각 띠가 바로 실천할 한 가지를 찾아보세요.", "field": "overall"},
    {"key": "spotlight", "intro": "오늘 흐름이 두드러지는 띠부터 빠르게 확인합니다.", "field": "overall"},
    {"key": "question", "intro": "내 띠에 해당하는 한 줄을 골라 오늘의 행동으로 옮겨보세요.", "field": "overall"},
]

PROFILE_CTAS = [
    "오늘의 띠 흐름보다 더 개인적인 사주 내용은 프로필 링크의 홈페이지에서 이어서 확인하세요.",
    "띠 운세는 공통 흐름이고, 내 사주 흐름은 프로필 링크의 사주 홈페이지에서 확인할 수 있습니다.",
    "오늘 내용이 내 이야기와 얼마나 맞는지 프로필 링크의 사주 홈페이지에서 비교해 보세요.",
]
ENGAGEMENT_CTAS = [
    "내 띠의 한 줄이 맞았는지 댓글로 남겨 주세요. 내일은 다른 관점으로 이어갑니다.",
    "가족이나 친구의 띠가 떠올랐다면 함께 공유하고, 오늘의 행동을 하나 정해 보세요.",
    "오늘 가장 먼저 실천할 한 가지를 저장해 두고, 하루 끝에 결과를 확인해 보세요.",
    "이 채널은 매일 간지와 띠의 관계를 바탕으로 오늘의 흐름을 전해드립니다.",
]


def _script_mode(d: dt.date) -> dict:
    """날짜로 고정 선택해 재실행해도 같은 대본이 나오게 한다."""
    return SCRIPT_MODES[d.toordinal() % len(SCRIPT_MODES)]


def _profile_day(d: dt.date) -> bool:
    """프로필 링크 유도일: 이틀에 한 번(날짜 기준, KST 대상 날짜)."""
    return d.toordinal() % 2 == 0


def _first_sentence(text: str) -> str:
    text = " ".join(str(text or "").split()).strip()
    if not text:
        return "오늘의 흐름을 차분히 살펴보세요"
    return text.split(". ", 1)[0].rstrip(".")


def _reading_line(reading, ctx: dict, mode: dict) -> str:
    """사주v6 계산 결과에서 한 띠의 짧고 실제적인 한 줄을 만든다."""
    field = mode["field"]
    if field == "overall":
        # overall 앞의 '오늘은 XX일,'은 첫 카드 도입에서만 말하고 띠별로 반복하지 않는다.
        prefix = f"오늘은 {ctx['day_pillar']}일, "
        body = reading.overall[len(prefix):] if reading.overall.startswith(prefix) else reading.overall
        return _first_sentence(body)
    # 재물·인연·건강 모드도 같은 일진 관계로 계산된 홈페이지의 세부 운세를 사용한다.
    return _first_sentence(getattr(reading, field, reading.overall))


def _dedup_lines(date_iso: str, mode: dict | None = None) -> dict:
    """사주v6와 같은 계산 결과를 사용하면서 같은 문장 반복을 줄인다."""
    d = dt.date.fromisoformat(date_iso)
    from ganzhi_zodiac import zodiac_day
    mode = mode or _script_mode(d)
    seen, out = set(), {}
    for ko in zpe.ZODIAC12:
        slug = zs.KO_TO_SLUG[ko]
        ctx = zodiac_day(slug, d)
        reading = zs.make_reading(slug, date_iso)
        txt = _reading_line(reading, ctx, mode)
        if txt in seen:
            # 동일 기조에서 문장이 겹치면 홈페이지의 종합운 두 번째 문장으로 대체한다.
            fallback = reading.overall.split(". ", 1)[-1].strip()
            txt = _first_sentence(fallback)
        seen.add(txt)
        out[slug] = txt
    return out


def narration_lines(date_iso: str) -> list[str]:
    d = dt.date.fromisoformat(date_iso)
    wd = ["월", "화", "수", "목", "금", "토", "일"][d.weekday()]
    from ganzhi_zodiac import day_context
    dc = day_context(d)
    mode = _script_mode(d)
    # 사주v6 홈페이지와 같은 당일 간지를 영상 첫 문장에 한 번만 고지한다.
    # 띠별 문장은 아래에서 같은 간지×띠 관계로 계산된 make_reading 결과를 사용한다.
    day_intro = f"오늘은 {dc['label']}·{dc['animal']}의 기운이 흐르는 날입니다."
    R = {ko: zs.make_reading(zs.KO_TO_SLUG[ko], date_iso) for ko in zpe.ZODIAC12}
    OA = _dedup_lines(date_iso, mode)
    lines = []
    for gi, group in enumerate(zpe.GROUPS):
        t = ""
        for ko in group:
            seg = OA[zs.KO_TO_SLUG[ko]].replace(" — ", ", ").rstrip(". ")
            t += f"{ko}, {seg}. "
        if gi == 0:
            t = (f"{d.month}월 {d.day}일 {wd}요일, 오늘의 띠별 운세. "
                 f"{day_intro} {mode['intro']} {t}")
        lines.append(t.strip())
    top = sorted(zpe.ZODIAC12, key=lambda ko: R[ko].overall_score, reverse=True)[:3]
    if _profile_day(d):
        cta = PROFILE_CTAS[d.toordinal() % len(PROFILE_CTAS)]
    else:
        cta = ENGAGEMENT_CTAS[d.toordinal() % len(ENGAGEMENT_CTAS)]
    lines.append(
        f"{dc['label']} 기준 12띠 전체 흐름을 한눈에 확인하세요. "
        f"오늘 특히 흐름이 좋은 띠는 {', '.join(top)}입니다. {cta}"
    )
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
    narrs = narration_lines(date_iso)
    cards = sorted((BASE / "cards" / date_iso).glob("card_*.png"))
    required = len(narrs)
    if len(cards) < required:
        raise SystemExit(f"[FAIL] Topview 카드 {required}장 필요, 현재 {len(cards)}장: {date_iso}")
    # 선택 지목 카드(card_05)가 있어도 기본 4장만 긴 쇼츠에 사용한다.
    cards = cards[:required]

    tmp = VIDEO_ROOT / "tmp" / date_iso
    tmp.mkdir(parents=True, exist_ok=True)

    # ── 길이 게이트: 네이버 클립은 90초 초과분을 아예 안 받는다 (한밝님 2026-07-17).
    # 문구 길이가 날마다 달라 고정 설정으론 언젠가 넘는다 → 재서 넘치면 속도를 올린다.
    voice_used = None
    mp3s = [tmp / f"n{i}.mp3" for i in range(len(narrs))]
    # 2026-07-26: 시작 속도를 1.12 로 올렸다. 쇼츠는 템포가 빠를수록 이탈이 줄고,
    # 길이가 짧아져 시청 완료율이 올라간다. 다만 타겟이 30대~시니어라 과속은 금물이라
    # 긴판은 +12% 선에서 멈춘다(짧은판은 LONG 대비 더 빠른 SHORT_TEMPO 사용).
    tempo = LONG_TEMPO
    for attempt in range(3):
        for mp3, narr in zip(mp3s, narrs):
            info = typecast_tts.synth(narr, mp3, d, log=log, tempo=tempo)
            voice_used = info
        total = sum(_dur(m) + PAD for m in mp3s)
        if total <= CLIP_LIMIT:
            log(f"길이 {total:.1f}초 (제한 {CLIP_LIMIT}초, tempo={tempo:.2f}) ✅")
            break
        new_tempo = round(min(1.35, tempo * (total / TARGET_SEC)), 2)
        if new_tempo <= tempo:      # 더 올릴 수 없음 → 그대로 두고 경고
            log(f"[WARN] {total:.1f}초 — tempo 상한. 네이버 클립 제외될 수 있음")
            break
        log(f"길이 {total:.1f}초 > {CLIP_LIMIT}초 → tempo {tempo:.2f}→{new_tempo:.2f} 재합성")
        tempo = new_tempo

    clips = []
    for i, (card, narr) in enumerate(zip(cards, narrs)):
        mp3 = mp3s[i]
        L = round(_dur(mp3) + PAD, 2)
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
    out = VIDEO_ROOT / "reels" / f"{date_iso}_tts.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
          "-c", "copy", str(out)])

    # PNGTuber PIP는 BGM을 섞기 전(내레이션 단독 오디오)에 얹는다 —
    # RMS 립싱크가 BGM 잡음 없이 실제 발화에만 반응하도록.
    _apply_pngtuber_pip(out, d, voice_used)

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

    _fit_max_duration(out)      # 90초 넘으면 업로드 자체가 막히는 플랫폼이 있다

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


# ── A/B 10초 압축판 (2026-07-17) ──────────────────────────────
# 근거(경쟁사 실측): 조회수 상위 운세 쇼츠는 전부 6~11초이고 12띠를 한 화면에 띄워
# **일시정지해 읽게** 만든다(사주노트 8초 219K·부자될상 7초 73K). 95초판은 자기 띠가
# 나오면 이탈 → 완주율 열세. 2주 A/B로 실측한다.
HOOK_SEC = 2.0        # 첫 띠별카드 + 훅 내레이션
# 2026-07-25: 8초 → 18초. 시청자 피드백 — "글자를 다 못 읽는다".
# 12띠 × 각 3~4줄을 8초에 읽는 건 실제로 무리였다. 경쟁사 실측(6~11초)은
# '일시정지해서 읽는' 시청 행태를 전제한 수치인데, 우리 카드가 그보다 정보량이 많다.
# 첫 띠별카드 2초 + 요약 18초 = 20초로 고정한다.
SUMMARY_SEC = 18.0    # 12띠 카드 (읽는 구간)


# ── 프로필 유입 CTA 배지 (2026-07-25) ─────────────────────────
# 쇼츠는 설명란·댓글의 링크가 클릭되지 않는다(유튜브 스팸 방지 정책). 유입 통로는
# 채널 프로필 링크뿐이라, 화면에서 "프로필을 보라"고 말해주는 수밖에 없다.
#
# 위치: 날짜 배지 바로 아래의 빈 여백(실측 21.2%~27.1%, 80px).
#  - 하단에 두면 12띠 마지막 행(닭·개·돼지)을 가리고, YouTube Shorts UI도 그 구간을 덮는다
#  - 상단에 검은 띠를 얹으면 얹은 티가 난다
#  - 이 여백은 원래 비어 있어 크롭도 이동도 필요 없다 → 정보 손실 0, 이음매 0
# 모양은 날짜 배지와 같은 언어(둥근 pill + 크림 테두리 + 그림자)로 맞춰 이물감을 없앤다.
CTA_ENABLED = os.environ.get("ZODIAC_CTA_BAND", "1") != "0"   # 끄려면 ZODIAC_CTA_BAND=0
CTA_TEXT = "무료 운세 · 이용권 1,000원 · 프로필 링크"
CTA_HIGHLIGHT = "이용권 1,000원"        # 이 부분만 금색으로 강조
# ⚠️ CTA_HIGHLIGHT는 CTA_TEXT의 부분문자열이어야 금색 강조가 걸린다. 같이 고칠 것.
# 2026-07-27: "사주풀이 990원" → "이용권 1,000원". 가격은 이니시스 카드 최소금액(1,000원)
# 때문에 올렸고, 표현은 홍보 가이드(PROMO_PLAN)가 "990원 사주풀이"를 표시광고법 위반으로
# 금지하고 있어 바로잡았다 — 1,000원은 하루 이용권이고 정밀 풀이 PDF는 25,000~30,000원이다.
CTA_ZONE = (0.212, 0.271)               # (날짜배지 끝, 첫 카드행 시작) 실측값
_C_WINE, _C_CREAM, _C_GOLD = (138, 30, 62), (255, 248, 235), (255, 205, 90)
_CTA_FONTS = [
    Path(r"D:\blog_auto_work\assets\fonts\GmarketSansTTFBold.ttf"),
    Path(r"C:\Windows\Fonts\malgunbd.ttf"),
    Path(r"C:\Windows\Fonts\malgun.ttf"),
]


def _cta_font(size: int):
    from PIL import ImageFont
    for f in _CTA_FONTS:
        try:
            if f.exists():
                return ImageFont.truetype(str(f), size)
        except Exception:
            continue
    return ImageFont.load_default()


def _zone_is_empty(im, top: int, bot: int) -> bool:
    """CTA 자리가 정말 빈 여백인지 확인 — 카드 레이아웃이 바뀌면 덮어쓰지 않고 건너뛴다."""
    px, w = im.load(), im.size[0]
    whites = 0
    rows = range(top, bot, max(1, (bot - top) // 12))
    for y in rows:
        for x in range(0, w, 8):
            r, g, b = px[x, y][:3]
            if r > 235 and g > 235 and b > 230:
                whites += 1
    total = len(list(rows)) * len(range(0, w, 8))
    return total > 0 and whites / total < 0.35


def _find_empty_band(im, min_h: int) -> tuple[int, int] | None:
    """카드에서 글자가 없는 가로 여백 띠를 찾는다(위에서부터 가장 먼저 맞는 것).

    12띠 요약 카드는 CTA_ZONE 실측값이 맞지만, 신포맷(지목3띠·표형)은 레이아웃이
    달라 그 좌표가 카드 내용 위에 떨어진다 → 그대로 두면 CTA가 매번 스킵되고
    사주 유입 통로가 사라진다(실측: pick3·table12 둘 다 스킵됐다).
    아래·위 끝은 피한다 — 하단은 YouTube Shorts UI가 덮고, 최상단은 제목 자리다.
    """
    px, (w, h) = im.load(), im.size
    lo, hi = int(h * 0.06), int(h * 0.88)
    xs = range(0, w, 12)
    run_s, best = None, None
    for y in range(lo, hi, 4):
        # 판정 기준은 '밝다'가 아니라 '글자가 없다'. 그림 배경 카드(지목3띠)는
        # 여백도 순백이 아니라 밝기 기준으로는 아무 줄도 안 잡혔다(실측).
        dark = sum(1 for x in xs if sum(px[x, y][:3]) / 3 < 120) / len(xs)
        if dark <= 0.02:
            run_s = y if run_s is None else run_s
            if y - run_s >= min_h and (best is None or y - run_s > best[1] - best[0]):
                best = (run_s, y)
        else:
            run_s = None
    return best


def add_cta_band(src: Path, dst: Path) -> Path:
    """카드 여백에 프로필 유입 배지를 얹는다. 실패하면 원본 그대로 쓴다."""
    try:
        from PIL import Image, ImageDraw, ImageFilter
        im = Image.open(src).convert("RGBA")
        w, h = im.size
        zt, zb = int(h * CTA_ZONE[0]), int(h * CTA_ZONE[1])
        if not _zone_is_empty(im, zt, zb):
            band = _find_empty_band(im, int(h * 0.035))
            if band is None:
                log("  [!] CTA 얹을 여백을 못 찾아 건너뜁니다")
                return src
            zt, zb = band
            if zb - zt > h * 0.075:      # 너무 넓으면 위쪽만 쓴다(배지가 뚱뚱해짐 방지)
                zb = zt + int(h * 0.075)
            log(f"  CTA 자리 자동 탐색: y {zt}~{zb}")

        cy, ph, pw = (zt + zb) // 2, int((zb - zt) * 0.82), int(w * 0.90)
        box = [w // 2 - pw // 2, cy - ph // 2, w // 2 + pw // 2, cy + ph // 2]

        sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
        ImageDraw.Draw(sh).rounded_rectangle(
            [box[0], box[1] + 5, box[2], box[3] + 5], radius=ph // 2, fill=(90, 40, 60, 95))
        im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(6)))

        dr = ImageDraw.Draw(im)
        dr.rounded_rectangle(box, radius=ph // 2, fill=_C_WINE + (255,),
                             outline=_C_CREAM + (255,), width=4)

        size = int(ph * 0.56)
        while size > 12:
            f = _cta_font(size)
            if dr.textbbox((0, 0), CTA_TEXT, font=f)[2] <= pw * 0.90:
                break
            size -= 1
        bb = dr.textbbox((0, 0), CTA_TEXT, font=f)
        x, y = (w - (bb[2] - bb[0])) / 2, cy - (bb[3] - bb[1]) / 2 - bb[1] / 2
        if CTA_HIGHLIGHT and CTA_HIGHLIGHT in CTA_TEXT:
            head, tail = CTA_TEXT.split(CTA_HIGHLIGHT, 1)
            dr.text((x, y), head, font=f, fill=_C_CREAM + (255,))
            dr.text((x + dr.textbbox((0, 0), head, font=f)[2], y),
                    CTA_HIGHLIGHT + tail, font=f, fill=_C_GOLD + (255,))
        else:
            dr.text((x, y), CTA_TEXT, font=f, fill=_C_CREAM + (255,))

        im.convert("RGB").save(dst)
        log(f"  CTA 배지 적용: {dst.name} (pill {pw}x{ph}, 폰트 {size}px)")
        return dst
    except Exception as e:
        log(f"  [!] CTA 배지 실패({e}) — 원본으로 진행합니다")
        return src


# ── 소수 지목형 20초판 (2026-07-26 신포맷) ───────────────────
# 벤치마크 실측(별빛 운세 정원): 12띠 전부 보여준 13초 7,579뷰 < 소수만 지목한 19초
# 13,247뷰. 길이 가설은 기각됐고(더 긴 쪽이 이겼다) 실제 변수는 "내가 해당되나?"였다.
# 그래서 두 가지를 바꾼다.
#   ① 표지 컷 제거 — 쇼츠에서 첫 1~2초를 표지에 쓰는 건 순손실이다(표지는 롱폼 문법).
#   ② 12띠 나열 → 3띠 지목 — 자기 띠를 보면 이탈하던 구조를 없앤다.
# 길이는 20초를 유지한다. 단축은 근거가 없다(위 실측).
# 롤백: ZODIAC_PICK3=0 → 첫 띠별카드+12띠 20초판으로 즉시 복귀.
PICK3_ENABLED = os.environ.get("ZODIAC_PICK3", "1") != "0"
PICK3_MIN_SEC, PICK3_MAX_SEC = 17.0, 24.0

# 훅·CTA는 날짜 결정론 로테이션(재조립해도 안 바뀜). 과장 화법 금지 —
# 벤치마크 채널의 `운 폭발`류는 쓰지 않는다(운명과학TV 수익정지 이력).
PICK3_HOOKS = [
    "오늘 흐름이 좋은 띠, 세 띠만 짚어 드립니다.",
    "오늘 하루, 유독 기운이 순한 띠가 셋 있습니다.",
    "혹시 우리 집에 이 띠 계신가요. 세 띠만 알려 드립니다.",
    "오늘 운이 조용히 도와주는 띠, 딱 세 띠입니다.",
    "지금부터 이십 초, 오늘 흐름 좋은 세 띠를 짚어 봅니다.",
]
PICK3_CTAS = [
    "내일은 어느 띠일지, 구독해 두시면 아침마다 이어집니다.",
    "우리 가족 띠가 나왔다면, 지금 공유해 보세요.",
    "화면을 두 번 누르시면 좋아요가 눌러집니다.",
    "내 띠는 언제 나오는지, 내일 이 시간에 확인해 보세요.",
    "매일 이 시간, 오늘의 띠 흐름으로 찾아옵니다.",
]
# 3위→1위 역순 공개. 순위를 거꾸로 풀어야 마지막까지 볼 이유가 남는다.
PICK3_RANKS = ["먼저 세 번째", "두 번째", "그리고 오늘 첫 번째"]

# 포맷 로테이션 정본은 zodiac_prompt_engine(이미지 생성 단계에서도 필요하다).
# 유튜브 20초판은 짝수일만 올라가므로 실제 노출은 6일 주기로 3종이 순환한다.
SHORTS_FORMATS = zpe.SHORTS_FORMATS
shorts_format = zpe.shorts_format


def pick3_narration(date_iso: str, picks: list[str], rows: dict,
                    pt: dict | None = None, scores: dict | None = None) -> str:
    """주제(오늘/이번주/이달 × 총운·재물·인연·건강)에 맞춘 대본.

    기간형 주제에서 오늘치 일진 한 줄을 읽으면 제목과 내용이 어긋난다
    ("이달 흐름 좋은 띠"인데 오늘 운세를 읽는 격). 기간형은 대신 **그 기간 중
    가장 좋은 날**을 짚어 준다 — 같은 데이터에서 나오고, 시청자에게 더 쓸모 있다.
    """
    d = dt.date.fromisoformat(date_iso)
    wd = ["월", "화", "수", "목", "금", "토", "일"][d.weekday()]
    pt = pt or zpe.pick3_theme(d)
    hook = pt.get("hook") or PICK3_HOOKS[d.toordinal() % len(PICK3_HOOKS)]
    cta = PICK3_CTAS[(d.toordinal() + 2) % len(PICK3_CTAS)]
    parts = [f"{d.month}월 {d.day}일 {wd}요일. {hook}"]
    # 3띠는 서로 다른 그룹에서 뽑히는데 build_rows의 중복 회피는 그룹(3띠) 안에서만
    # 돈다 → 지목형에선 같은 문구가 그대로 샌다(실측: 용띠·쥐띠가 같은 문장).
    # 여기서 한 번 더 막는다. 문구는 rows['line']을 재창작하지 않고 반드시
    # 사주v6 정본 zodiac_seo.make_reading(sign, date)를 거쳐 얻는다.
    from ganzhi_zodiac import zodiac_day
    axis = pt.get("axis", "overall")
    field_mode = {"field": axis}
    used: set[str] = set()
    for i, ko in enumerate(reversed(picks)):
        slug = zs.KO_TO_SLUG[ko]
        if pt["scope"] == "day":
            reading = zs.make_reading(slug, date_iso)
            tail = _reading_line(reading, zodiac_day(slug, d), field_mode)
            if tail in used:
                import zodiac_topview as zt
                tone = (rows.get(ko) or {}).get("tone", "평온")
                for alt in zt.ALT_LINES.get(tone, []):
                    if alt not in used:
                        tail = alt
                        break
        else:
            bd = ((scores or {}).get(ko) or {}).get("best_day")
            target = bd or d
            # 기간형도 가장 좋은 날의 실제 사주v6 결과를 사용한다. 날짜만 던지는
            # 추상 문장으로 끝내지 않아, 카드·페이지·대본의 근거가 일치한다.
            reading = zs.make_reading(slug, target.isoformat())
            target_ctx = zodiac_day(slug, target)
            detail = _reading_line(reading, target_ctx, field_mode)
            if not bd:
                tail = detail
            elif bd == d:
                tail = f"오늘부터, {detail}"
            else:
                tail = f"특히 {bd.month}월 {bd.day}일 무렵, {detail}"
            if tail in used:      # 같은 날이 겹치면 표현을 바꿔 반복을 지운다
                tail = (f"{bd.month}월 {bd.day}일, 이 띠도 같이 좋습니다" if bd
                        else "이 띠도 흐름이 순합니다")
        used.add(tail)
        parts.append(f"{PICK3_RANKS[i]}, {ko}. {tail}.")
    parts.append(cta)
    return " ".join(parts)


# ── 표형 12띠 (2026-07-26, 한밝님 레퍼런스 포맷) ──────────────
# 12띠를 다 보여주되 **로컬 PIL 렌더**로 그린다(zodiac_table_card). AI 생성은 이
# 밀도에서 한글이 깨지는데, 표는 오타가 바로 티가 난다. 크레딧 0·실패율 0도 덤.
# 성격: 지목형이 완주율용이라면 이쪽은 '일시정지해서 읽는' 정보형이다.
TABLE12_HOOKS = [
    "열두 띠 오늘 흐름, 한 화면에 담았습니다.",
    "오늘 내 띠는 어떤 하루일지 같이 보시겠습니다.",
    "열두 띠 모두, 오늘의 기운을 한눈에 정리했습니다.",
    "우리 가족 띠까지 같이 확인해 보세요.",
    "오늘 하루 어떻게 흘러갈지, 띠별로 짚어 드립니다.",
]


def table12_narration(date_iso: str, top3: list[str]) -> str:
    d = dt.date.fromisoformat(date_iso)
    wd = ["월", "화", "수", "목", "금", "토", "일"][d.weekday()]
    hook = TABLE12_HOOKS[d.toordinal() % len(TABLE12_HOOKS)]
    cta = PICK3_CTAS[(d.toordinal() + 2) % len(PICK3_CTAS)]
    return " ".join([
        f"{d.month}월 {d.day}일 {wd}요일. {hook}",
        "화면을 잠깐 멈추시면 내 띠를 천천히 보실 수 있습니다.",
        f"오늘 흐름이 특히 좋은 띠는 {', '.join(top3)}입니다.",
        "해당되는 띠는 미뤄둔 일을 오늘 매듭지어 보셔도 좋습니다.",
        cta,
    ])


def _still_shorts(date_iso: str, card: Path, text: str, fmt: str,
                  extra: dict | None = None, overlay_cta: bool = False) -> Path:
    """정지 이미지 1장 + 전 구간 내레이션 ≈ 20초. **표지 컷 없음**.

    출력 경로와 표식은 기존 20초판과 **같게 유지한다**(reels/{date}_10s.mp4,
    shorts10_meta.json). 업로드 큐·중복 업로드 가드가 이 두 경로를 보고 있어서,
    이름을 바꾸면 업로드가 조용히 멈춘다(2026-07-17 오업로드 사고의 반대 방향 위험).
    """
    d = dt.date.fromisoformat(date_iso)
    cdir = BASE / "cards" / date_iso
    tmp = cdir / "_still"
    tmp.mkdir(exist_ok=True)
    # 신포맷 카드(지목3띠·표형)는 CTA를 카드 안에 이미 품고 있다 → 얹으면 두 개가 된다
    # (실측: 지목형 카드 첫 셀과 둘째 셀 사이 여백에 배지가 하나 더 붙었다).
    img = add_cta_band(card, tmp / "card_cta.png") if (overlay_cta and CTA_ENABLED) else card
    mp3 = tmp / "narr.mp3"
    info = typecast_tts.synth(text, mp3, d, log=log, tempo=SHORT_TEMPO)
    L = max(PICK3_MIN_SEC, round(_dur(mp3) + 0.8, 2))

    out = VIDEO_ROOT / "reels" / f"{date_iso}_10s.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    frames = int(L * FPS)
    # 줌은 최소로 — 글씨를 읽는 화면이라 흔들리면 안 된다.
    vf = (f"scale={W*3}:{H*3}:flags=lanczos,"
          f"zoompan=z='min(1.0+0.0002*on,1.03)':x='iw/2-(iw/zoom/2)':"
          f"y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps={FPS},format=yuv420p")
    _run(["ffmpeg", "-y", "-loop", "1", "-i", str(img), "-i", str(mp3),
          "-af", "apad", "-t", str(L), "-vf", vf, "-r", str(FPS),
          "-c:v", "libx264", "-preset", "veryfast",
          "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
          "-pix_fmt", "yuv420p", str(out)])

    _apply_pngtuber_pip(out, d, info)
    if L > PICK3_MAX_SEC:            # 대본이 길어진 날은 잘라내지 말고 살짝 배속
        _fit_max_duration(out, PICK3_MAX_SEC)

    bgm = pick_bgm(d)
    if bgm:
        dur = _dur(out)
        tmp_b = out.with_name(out.stem + "_b.mp4")
        try:
            _run(["ffmpeg", "-y", "-i", str(out), "-stream_loop", "-1", "-i", str(bgm),
                  "-filter_complex",
                  f"[1:a]loudnorm=I=-20:TP=-2,volume=0.13,afade=t=in:d=0.8,"
                  f"afade=t=out:st={max(0.0, dur-1.5):.2f}:d=1.5[bg];"
                  f"[0:a][bg]amix=inputs=2:duration=first:normalize=0[a]",
                  "-map", "0:v", "-map", "[a]", "-c:v", "copy",
                  "-c:a", "aac", "-b:a", "128k", "-t", f"{dur:.2f}", str(tmp_b)])
            tmp_b.replace(out)
        except subprocess.CalledProcessError as e:
            log(f"[WARN] {fmt} BGM 실패: {e.stderr[-200:] if e.stderr else e}")
            if tmp_b.exists():
                tmp_b.unlink()

    meta = {"date": date_iso, "variant": "A_10s", "format": fmt,
            "voice": info, "bgm": bgm.name if bgm else None,
            "duration": round(_dur(out), 1), "narration": text}
    meta.update(extra or {})
    (cdir / "shorts10_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    for f in tmp.glob("*"):
        f.unlink()
    tmp.rmdir()
    log(f"✅ {fmt} 20초판 완성 → {out} ({_dur(out):.1f}초, "
        f"{info['engine']}:{info['voice']})")
    return out


def make_shorts_pick3(date_iso: str | None = None) -> Path:
    """3띠 지목형 — 오늘 흐름이 좋은 띠 셋만. 표지 없음."""
    date_iso = date_iso or zs.today_iso()
    card = BASE / "cards" / date_iso / "card_05.png"
    if not card.exists():
        raise SystemExit(f"[FAIL] 지목형 재료 없음: card_05.png ({date_iso})")
    import zodiac_topview as zt      # 카드를 만든 것과 같은 데이터로 대본을 쓴다
    d = dt.date.fromisoformat(date_iso)
    rows = zt.build_rows(date_iso)
    pt = zpe.pick3_theme(d)
    sc = zpe.theme_scores(d, pt)
    picks = zpe.pick3_signs(rows, date=d, theme=pt)
    text = pick3_narration(date_iso, picks, rows, pt, sc)
    log(f"지목형 대본({len(text)}자): 주제={pt['title']}, 지목={', '.join(picks)}")
    return _still_shorts(date_iso, card, text, "pick3",
                         {"picks": picks, "theme": pt["key"],
                          "theme_title": pt["title"]})


def make_shorts_table12(date_iso: str | None = None) -> Path:
    """표형 12띠 — 로컬 렌더 카드 한 장. 표지 없음."""
    date_iso = date_iso or zs.today_iso()
    import zodiac_topview as zt
    import zodiac_table_card as ztc
    rows = zt.build_rows(date_iso)
    card = ztc.render(date_iso, BASE / "cards" / date_iso / "card_08.png", rows)
    top3 = zpe.pick3_signs(rows)
    text = table12_narration(date_iso, top3)
    log(f"표형 대본({len(text)}자): 강조={', '.join(top3)}")
    return _still_shorts(date_iso, card, text, "table12", {"top3": top3})


def make_shorts_10s(date_iso: str | None = None) -> Path:
    """첫 띠별카드 2초(훅 TTS) + 12띠 요약 18초 = 20초. 출력: reels/{date}_10s.mp4

    함수명과 파일명의 '10s'는 처음 만들 때의 이름이 남은 것이다. 실제 길이는 20초다.
    파이프라인·업로드 큐가 이 경로를 참조하고 있어 이름은 그대로 두었다.

    2026-07-26부터 이 함수는 **포맷 분배기**다. 아래 본문(첫 띠별카드+12띠 AI카드)은
    3종 로테이션의 한 갈래이자, 다른 포맷이 실패한 날의 폴백으로 남는다.
    """
    date_iso = date_iso or zs.today_iso()
    if PICK3_ENABLED:
        fmt = shorts_format(date_iso)
        if fmt != "ai12":
            try:
                return (make_shorts_pick3(date_iso) if fmt == "pick3"
                        else make_shorts_table12(date_iso))
            except BaseException as e:
                log(f"[WARN] {fmt} 포맷 실패({type(e).__name__}: {e}) — "
                    f"첫 띠별카드+12띠 20초판으로 폴백합니다")
    d = dt.date.fromisoformat(date_iso)
    cdir = BASE / "cards" / date_iso
    opening, summary = cdir / "card_01.png", cdir / "card_04.png"
    for p in (opening, summary):
        if not p.exists():
            raise SystemExit(f"[FAIL] 10초판 재료 없음: {p.name} ({date_iso})")

    tmp = cdir / "_s10"
    tmp.mkdir(exist_ok=True)
    if CTA_ENABLED:
        summary = add_cta_band(summary, tmp / "card_04_cta.png")
    # 훅은 짧을수록 좋다 — 전체 10초 안에 12띠 읽는 시간(8초)을 남겨야 한다.
    # (긴 훅 "…요일, 오늘의 띠별 운세. 내 띠 확인하세요."는 4초를 먹어 12.1초가 됐음)
    hook = f"{d.month}월 {d.day}일 오늘의 띠별 운세!"
    mp3 = tmp / "hook.mp3"
    info = typecast_tts.synth(hook, mp3, d, log=log, tempo=SHORT_TEMPO)
    hook_len = max(HOOK_SEC, round(_dur(mp3) + 0.3, 2))

    clips = []
    for i, (img, L, audio) in enumerate([(opening, hook_len, mp3), (summary, SUMMARY_SEC, None)]):
        clip = tmp / f"c{i}.mp4"
        frames = int(L * FPS)
        # 요약 카드는 줌을 최소로 — 글씨를 읽어야 하므로 흔들리면 안 된다
        z = f"min(1.0+0.0008*on,1.06)" if i == 0 else f"min(1.0+0.0002*on,1.02)"
        vf = (f"scale={W*3}:{H*3}:flags=lanczos,"
              f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
              f":d={frames}:s={W}x{H}:fps={FPS},format=yuv420p")
        cmd = ["ffmpeg", "-y", "-loop", "1", "-i", str(img)]
        if audio:
            cmd += ["-i", str(audio), "-af", "apad"]
        else:   # 무음 트랙 (concat은 스트림 구성이 같아야 함)
            cmd += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
        cmd += ["-t", str(L), "-vf", vf, "-r", str(FPS),
                "-c:v", "libx264", "-preset", "veryfast",
                "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
                "-pix_fmt", "yuv420p", str(clip)]
        _run(cmd)
        clips.append(clip)

    lst = tmp / "list.txt"
    lst.write_text("".join(f"file '{c.as_posix()}'\n" for c in clips), encoding="utf-8")
    out = VIDEO_ROOT / "reels" / f"{date_iso}_10s.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
          "-c", "copy", str(out)])

    _apply_pngtuber_pip(out, d, info)

    bgm = pick_bgm(d)
    if bgm:
        dur = _dur(out)
        tmp_b = out.with_name(out.stem + "_b.mp4")
        try:
            _run(["ffmpeg", "-y", "-i", str(out), "-stream_loop", "-1", "-i", str(bgm),
                  "-filter_complex",
                  f"[1:a]loudnorm=I=-20:TP=-2,volume=0.13,afade=t=in:d=0.8,"
                  f"afade=t=out:st={max(0.0, dur-1.5):.2f}:d=1.5[bg];"
                  f"[0:a][bg]amix=inputs=2:duration=first:normalize=0[a]",
                  "-map", "0:v", "-map", "[a]", "-c:v", "copy",
                  "-c:a", "aac", "-b:a", "128k", "-t", f"{dur:.2f}", str(tmp_b)])
            tmp_b.replace(out)
        except subprocess.CalledProcessError as e:
            log(f"[WARN] 10초판 BGM 실패: {e.stderr[-200:] if e.stderr else e}")
            if tmp_b.exists():
                tmp_b.unlink()

    (cdir / "shorts10_meta.json").write_text(json.dumps(
        {"date": date_iso, "variant": "A_10s", "voice": info,
         "bgm": bgm.name if bgm else None, "duration": round(_dur(out), 1)},
        ensure_ascii=False, indent=1), encoding="utf-8")
    for f in tmp.glob("*"):
        f.unlink()
    tmp.rmdir()
    log(f"✅ 10초판 완성 → {out} ({_dur(out):.1f}초, {info['engine']}:{info['voice']})")
    return out


# ── 길이 상한 가드 (2026-07-25) ──────────────────────────────
# 95초판은 G드라이브로 미러되어 틱톡·네이버클립에 수동 업로드된다. 90초를 넘으면
# 아예 못 올리는 플랫폼이 있어, 조립 직후 길이를 재고 넘치면 살짝 배속해 맞춘다.
# atempo는 음정을 유지하므로 1.1배 정도까지는 귀에 걸리지 않는다.
MAX_UPLOAD_SEC = 88.0        # 90초 규격에 인코딩 오차 여유 2초
MAX_TEMPO = 1.12             # 이 이상 당겨야 하면 내용을 줄여야 할 때다 → 경고만


def _fit_max_duration(video: Path, limit: float = MAX_UPLOAD_SEC) -> bool:
    """limit 초과 시 배속으로 맞춘다. 맞췄으면 True."""
    try:
        cur = _dur(video)
        if cur <= limit or cur <= 0:
            return False
        tempo = cur / limit
        if tempo > MAX_TEMPO:
            log(f"[WARN] {cur:.1f}초 — {limit:.0f}초로 줄이려면 {tempo:.2f}배가 필요합니다. "
                f"배속 대신 나레이션을 줄이세요. (원본 유지)")
            return False
        tmp = video.with_name(video.stem + "_fit.mp4")
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(video),
             "-filter_complex", f"[0:v]setpts=PTS/{tempo:.5f}[v];[0:a]atempo={tempo:.5f}[a]",
             "-map", "[v]", "-map", "[a]", "-r", str(FPS),
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
             "-c:a", "aac", "-b:a", "128k", "-pix_fmt", "yuv420p", str(tmp)],
            check=True, capture_output=True)
        tmp.replace(video)
        log(f"길이 조정: {cur:.1f}초 → {_dur(video):.1f}초 (x{tempo:.3f}, 90초 규격)")
        return True
    except Exception as e:
        log(f"[WARN] 길이 조정 실패({e}) — 원본 유지")
        return False


def ab_variant(date_iso: str) -> str:
    """업로드 변종 결정.

    2026-07-25 한밝님 지시로 A(첫 띠별카드+12띠 2장, 20초)로 고정했다.
    그 전에는 날짜 홀짝으로 A(압축판)와 B(95초판)를 번갈아 올려 A/B를 돌렸는데,
    "글자를 못 읽는다"는 실제 시청자 피드백이 나와 압축판을 20초로 늘리고
    이 형태를 상시 포맷으로 삼는다.

    A/B를 다시 돌리려면 아래 한 줄을 예전 식으로 되돌리면 된다:
        return "A" if dt.date.fromisoformat(date_iso).toordinal() % 2 == 0 else "B"
    """
    return "A"


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    mode = sys.argv[1] if len(sys.argv) > 1 else "generate"
    di = sys.argv[2] if len(sys.argv) > 2 else None
    if mode == "generate":
        make_shorts(di)
    elif mode == "10s":
        make_shorts_10s(di)
    else:
        raise SystemExit("사용법: python zodiac_shorts.py [generate|10s] [YYYY-MM-DD]")
