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

# ── PNGTuber 반응형 아바타 PIP (2026-07-20 연결) ──────────────
# 근거: G:\내 드라이브\01클로드\작업폴더\집PC이관_PNGTuber_2026-07-20\README_인수인계.md
# "숏폼(남녀 목소리 번갈아) = 그날 TTS 목소리 성별에 맞춰 아바타도 교체" — 타입캐스트
# 성별 로테이션(typecast_tts.pick_voice)과 동일 기준으로 페르소나를 고른다.
PNGTUBER_DIR = Path(r"G:\내 드라이브\01클로드\작업폴더\tts_pipeline\track_a_sellfarm")
PNGTUBER_AVATAR_ROOT = Path(r"G:\내 드라이브\01클로드\아바타\png tuber model")
PNGTUBER_PERSONA = {"male": "frames_shorts_young", "female": "frames_female_hanbok"}
PNGTUBER_MOUTH_FILES = ["mouth_0_closed_nobg.png", "mouth_1_slight_nobg.png",
                        "mouth_2_half_nobg.png", "mouth_3_wide_nobg.png"]


def _apply_pngtuber_pip(video_path: Path, date: dt.date) -> None:
    """쇼츠에 PNGTuber 반응형 아바타 PIP를 얹는다. 절대 예외를 던지지 않음 —
    G드라이브 스톨·프레임 누락 등 무엇이 실패해도 쇼츠 조립 자체는 계속 진행한다
    (human_touch_pip.apply_pip과 동일한 '빌드를 멈추지 않는다' 원칙)."""
    try:
        if str(PNGTUBER_DIR) not in sys.path:
            sys.path.insert(0, str(PNGTUBER_DIR))
        import pngtuber_shorts_pip as pnt_pip
        gender = typecast_tts.pick_voice(date)["gender"]
        persona = PNGTUBER_PERSONA[gender]
        frame_dir = PNGTUBER_AVATAR_ROOT / persona
        frames = [frame_dir / f for f in PNGTUBER_MOUTH_FILES]
        missing = [f for f in frames if not f.exists()]
        if missing:
            log(f"[WARN] PNGTuber 프레임 없음({persona}) — PIP 생략: {missing[0]}")
            return
        info = pnt_pip.compose(str(video_path), [str(f) for f in frames])
        log(f"PNGTuber PIP 완료: {persona}({gender}), {info['위치']} 위치, {info['길이']}초")
    except Exception as e:
        log(f"[WARN] PNGTuber PIP 실패(쇼츠는 그대로 진행): {type(e).__name__}: {e}")

# 네이버 클립 = 1분 30초 이내만 업로드 가능 (한밝님 2026-07-17). 초과하면 채널 하나를
# 통째로 못 쓴다. 88초를 목표로 잡아 인코딩 오차·패딩 여유를 둔다.
CLIP_LIMIT = 90.0
TARGET_SEC = 84.0

# TTS 말 속도 (1.0 = 기본). 2026-07-26 도입.
#   LONG  = 95초판(스레드·틱톡·네이버클립). 시니어 시청자를 배려해 +12% 선에서 멈춘다.
#   SHORT = 20초판(유튜브 쇼츠). 짧고 임팩트가 중요해 더 빠르게 간다.
# 길이 게이트가 필요하면 여기서 시작해 상한 1.35 까지 자동으로 더 올라간다.
LONG_TEMPO = 1.12
SHORT_TEMPO = 1.25
PAD = 0.7          # 컷당 꼬리 여백

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


# 3초 인트로 훅 — 날짜의 뒷 문장만 매일 바꾼다(앞 "N월 N일 N요일, 오늘의 띠별 운세."는
# 날짜 고지라 유지). 2026-07-21 훅 리서치: 궁금증갭·가족소환·결과예고 3형이 상위 조회.
INTRO_HOOKS = [
    "내 띠는 오늘 어떤 흐름일까요?",
    "우리 가족 중에, 오늘 유독 웃는 띠가 있습니다.",
    "오늘 하루, 조용히 운이 바뀌는 띠가 있어요.",
    "지금부터 딱 30초, 내 띠만 확인하세요.",
    "오늘, 뜻밖의 기회가 열리는 띠가 있습니다.",
]

# 구독·팔로우·좋아요 CTA — 매일 순환. 구걸형("눌러주세요") 대신 보상형으로 구성
# (리서치: 구걸형 CTA 채널은 조회수 바닥, 보상 프레이밍 채널이 상위). 좋아요는 쇼츠에서
# 화면 더블탭으로도 눌리므로 그 맥락을 자연스럽게 녹인다.
OUTRO_CTAS = [
    "이 채널 구독해 두시면, 매일 아침 내 띠 운세를 놓치지 않으실 수 있어요.",
    "화면을 가볍게 두 번 누르시면 좋아요가 눌러지고, 오늘의 좋은 기운이 그대로 이어집니다.",
    "우리 가족 생각나는 띠 있으면, 지금 공유해서 함께 확인해 보세요.",
    "내 띠는 어땠는지 댓글로 남겨주세요. 내일 운세도 여기서 이어집니다.",
    "매일 이 시간, 오늘의 운세로 찾아옵니다. 팔로우하고 함께해요.",
]


def narration_lines(date_iso: str) -> list[str]:
    d = dt.date.fromisoformat(date_iso)
    wd = ["월", "화", "수", "목", "금", "토", "일"][d.weekday()]
    # 날짜 기반 결정론적 선택 — 파이프라인이 재실행 멱등이라 같은 날 재조립해도 훅이 안 바뀜.
    # 인트로/아웃트로에 서로 다른 오프셋(+2)을 줘 둘이 같은 주기로 겹치지 않게.
    hook = INTRO_HOOKS[d.toordinal() % len(INTRO_HOOKS)]
    cta = OUTRO_CTAS[(d.toordinal() + 2) % len(OUTRO_CTAS)]
    R = {ko: zs.make_reading(zs.KO_TO_SLUG[ko], date_iso) for ko in zpe.ZODIAC12}
    OA = _dedup_lines(date_iso)
    lines = [f"{d.month}월 {d.day}일 {wd}요일, 오늘의 띠별 운세. {hook}"]
    for group in zpe.GROUPS:
        t = ""
        for ko in group:
            seg = OA[zs.KO_TO_SLUG[ko]].replace("오늘은 ", "").split(".")[0].strip()
            seg = seg.replace(" — ", ", ")
            t += f"{ko}, {seg}. "
        lines.append(t.strip())
    top = sorted(zpe.ZODIAC12, key=lambda ko: R[ko].overall_score, reverse=True)[:3]
    lines[-1] += f" 오늘 특히 웃는 띠는 {', '.join(top)}. {cta}"
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
    out = BASE / "reels" / f"{date_iso}_tts.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
          "-c", "copy", str(out)])

    # PNGTuber PIP는 BGM을 섞기 전(내레이션 단독 오디오)에 얹는다 —
    # RMS 립싱크가 BGM 잡음 없이 실제 발화에만 반응하도록.
    _apply_pngtuber_pip(out, d)

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
HOOK_SEC = 2.0        # 표지 + 훅 내레이션
# 2026-07-25: 8초 → 18초. 시청자 피드백 — "글자를 다 못 읽는다".
# 12띠 × 각 3~4줄을 8초에 읽는 건 실제로 무리였다. 경쟁사 실측(6~11초)은
# '일시정지해서 읽는' 시청 행태를 전제한 수치인데, 우리 카드가 그보다 정보량이 많다.
# 표지 2초 + 요약 18초 = 20초로 고정한다.
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
CTA_TEXT = "무료 운세 · 사주풀이 990원 · 프로필 링크"
CTA_HIGHLIGHT = "사주풀이 990원"        # 이 부분만 금색으로 강조
CTA_ZONE = (0.212, 0.271)               # (날짜배지 끝, 첫 카드행 시작) 실측값
_C_WINE, _C_CREAM, _C_GOLD = (138, 30, 62), (255, 248, 235), (255, 205, 90)
_CTA_FONTS = [
    Path(r"G:\내 드라이브\01클로드\에셋라이브러리\폰트\GmarketSansTTFBold.ttf"),
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


def add_cta_band(src: Path, dst: Path) -> Path:
    """날짜 배지 아래 여백에 프로필 유입 배지를 얹는다. 실패하면 원본 그대로 쓴다."""
    try:
        from PIL import Image, ImageDraw, ImageFilter
        im = Image.open(src).convert("RGBA")
        w, h = im.size
        zt, zb = int(h * CTA_ZONE[0]), int(h * CTA_ZONE[1])
        if not _zone_is_empty(im, zt, zb):
            log("  [!] CTA 자리에 카드 내용이 있어 건너뜁니다(레이아웃 변경 의심)")
            return src

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


def make_shorts_10s(date_iso: str | None = None) -> Path:
    """표지 2초(훅 TTS) + 12띠 요약 18초 = 20초. 출력: reels/{date}_10s.mp4

    함수명과 파일명의 '10s'는 처음 만들 때의 이름이 남은 것이다. 실제 길이는 20초다.
    파이프라인·업로드 큐가 이 경로를 참조하고 있어 이름은 그대로 두었다.
    """
    date_iso = date_iso or zs.today_iso()
    d = dt.date.fromisoformat(date_iso)
    cdir = BASE / "cards" / date_iso
    cover, summary = cdir / "card_01.png", cdir / "card_06.png"
    for p in (cover, summary):
        if not p.exists():
            raise SystemExit(f"[FAIL] 10초판 재료 없음: {p.name} ({date_iso})")

    tmp = cdir / "_s10"
    tmp.mkdir(exist_ok=True)
    if CTA_ENABLED:
        summary = add_cta_band(summary, tmp / "card_06_cta.png")
    # 훅은 짧을수록 좋다 — 전체 10초 안에 12띠 읽는 시간(8초)을 남겨야 한다.
    # (긴 훅 "…요일, 오늘의 띠별 운세. 내 띠 확인하세요."는 4초를 먹어 12.1초가 됐음)
    hook = f"{d.month}월 {d.day}일 오늘의 띠별 운세!"
    mp3 = tmp / "hook.mp3"
    info = typecast_tts.synth(hook, mp3, d, log=log, tempo=SHORT_TEMPO)
    hook_len = max(HOOK_SEC, round(_dur(mp3) + 0.3, 2))

    clips = []
    for i, (img, L, audio) in enumerate([(cover, hook_len, mp3), (summary, SUMMARY_SEC, None)]):
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
    out = BASE / "reels" / f"{date_iso}_10s.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
          "-c", "copy", str(out)])

    _apply_pngtuber_pip(out, d)

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

    2026-07-25 한밝님 지시로 A(표지+12띠 2장, 20초)로 고정했다.
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
