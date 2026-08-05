# -*- coding: utf-8 -*-
"""
human_touch_pip.py — 휴먼터치 PIP 자동 배치 (유튜브 AI 크랙다운 방어)

완성된 final.mp4 위에 바디캠(실사)·아바타 조각을 PIP로 자동 얹는다.
"사람이 만든 채널" 신호를 매 영상에 심는 게 목적.

배치 규칙 (2026-07-03 한밝님 확정):
  - 위치 4곳 로테이션: 우측상단 → 우측중단 → 좌측상단 → 좌측중단
    (하단은 자막 영역이라 절대 사용 안 함)
  - 같은 위치가 연속 영상에서 반복되지 않도록 상태 파일로 이어감
  - 바디캠 컷은 같은 컷 재사용 최소화 (사용 횟수 최저인 컷 우선)
  - 아바타는 시작 지점을 5초씩 밀어가며 10초만 잘라 써 매번 다른 장면
  - 아바타 자체 음성은 버리고 본편 오디오만 유지

영상 길이별 삽입 횟수:
  90초 미만 → 1회 (바디캠)         : 인트로
  5분 미만  → 2회 (바디캠+아바타)   : 인트로 + 중반
  5분 이상  → 3회 (바디+아바타+바디) : 인트로 + 중반 + 후반

풀 폴더 (SSOT, 듀얼 PC 공용):
  G:\\내 드라이브\\01클로드\\아바타\\pip_pool\\
    body_컷NN_XXs.mp4  바디캠 조각 (무음)
    avatar_NN.mp4       AI 아바타 (음성 포함이지만 사용 안 함)
    _pip_state.json     위치/사용횟수 상태 (자동 관리)

끄기: 환경변수 SELLFARM_PIP_ENABLED=0 또는 _pip_state.json 의 "enabled": false

단독 실행:
  python human_touch_pip.py <영상.mp4> [--pool 폴더]
"""
import json
import os
import re
import subprocess
import sys
import threading
from pathlib import Path

# 2026-07-03: 같은 프로세스에서 단일 빌드·큐 워커가 동시에 PIP를 돌릴 때
# _pip_state.json 읽기-쓰기 경합으로 로테이션이 무력화되던 문제 방지
_PIP_PROC_LOCK = threading.Lock()

DEFAULT_POOL = r"G:\내 드라이브\01클로드\아바타\pip_pool"
STATE_FILE = "_pip_state.json"

# (이름, x식, y식) — W/H=본편, w/h=PIP. 하단(자막)은 금지 구역
POSITIONS = [
    ("우측상단", "W-w-W*0.03", "H*0.03"),
    ("우측중단", "W-w-W*0.03", "H*0.42-h/2"),
    ("좌측상단", "W*0.03", "H*0.03"),
    ("좌측중단", "W*0.03", "H*0.42-h/2"),
]

PIP_WIDTH_RATIO = 0.24   # 본편 가로 대비 PIP 크기
AVATAR_SEG_SEC = 10.0    # 아바타에서 잘라 쓰는 길이
FADE_SEC = 0.4

# 배경 제거본 규칙 (2026-07-03 한밝님 지시 — 사각형 박스 대신 인물만 뜨게):
#   *_bk.*   = 캡컷 스마트 컷아웃 결과 (검은 배경) → colorkey 로 검정만 투명 처리
#   *_gs.* / *green* = 그린스크린 → chromakey
#   .webm / .mov / *_nobg.* = 알파 채널 투명 배경 (그대로 사용)
#   풀에 배경 제거본이 하나라도 있으면 일반본 대신 그것만 사용
NOBG_PAT = re.compile(r"_nobg|_gs|_bk|green", re.IGNORECASE)
ALPHA_EXT = {".webm", ".mov"}

# ── PNGTuber 반응형 아바타 — 2026-07-20 추가 ───────────────────
# 기존 정적 avatar_*.mp4 풀과 별개로, "avatar" 슬롯이 나올 때마다 정적 풀/PNGTuber를
# 번갈아 쓴다(state["avatar_mode_index"] 홀짝) — 3번째 종류를 로테이션에 추가.
# 근거: G:\내 드라이브\01클로드\작업폴더\집PC이관_PNGTuber_2026-07-20\README_인수인계.md
PNGTUBER_DIR = Path(r"G:\내 드라이브\01클로드\작업폴더\tts_pipeline\track_a_sellfarm")
PNGTUBER_AVATAR_ROOT = Path(r"G:\내 드라이브\01클로드\아바타\png tuber model")
PNGTUBER_MOUTH_FILES = ["mouth_0_closed_nobg.png", "mouth_1_slight_nobg.png",
                        "mouth_2_half_nobg.png", "mouth_3_wide_nobg.png"]
# 카테고리ID(정밀 매칭 우선) → 페르소나. 근거: 인수인계 2026-07-20 §3 "아직 안 한 것"
# 목록의 용도 라벨(뇌과학/자기계발·K방산/역사·경제/트렌드). visual_presets.py의 카테고리
# 분류가 더 성긴 곳(예: self_dev·economy가 둘 다 modern_business로 뭉침)을 여기서 세분화.
# ⚠️ 뇌과학·K방산은 visual_presets.py 카테고리ID에 정확히 없어 가장 가까운 것으로 매핑한
# 추정치 — 실제 콘텐츠 카테고리 체계와 다르면 이 dict만 고치면 됨.
PNGTUBER_PERSONA_BY_CATEGORY = {
    "self_dev":     "frames_male_casual_study",   # 자기계발
    "psychology":   "frames_male_casual_study",   # 뇌과학 근사
    "science":      "frames_male_casual_study",   # 뇌과학 근사
    "history":      "frames_male_darkformal",
    "space":        "frames_male_darkformal",     # K방산 근사(진지한 톤)
    "economy":      "frames_female_casual",
    "social_trend": "frames_female_casual",       # 트렌드
}
# preset_key(sellfarm_v4/visual_presets.py) → 롱폼 페르소나. 위 카테고리 매핑에 없을 때 폴백.
# (한복=사주/역사/명상, 정장클로즈업=경제/자기계발 일반, 그 외=정장스탠딩 일반 로테이션)
PNGTUBER_PERSONA_BY_PRESET = {
    "tradition_korean": "frames_hanbok_v2",
    "history_era":       "frames_hanbok_v2",
    "serene_minimal":     "frames_hanbok_v2",
    "modern_business":    "frames_suit_closeup_v2",
}
PNGTUBER_DEFAULT_PERSONA = "frames_suit_standing_v2"


def _pngtuber_frames(category_id):
    """카테고리에 맞는 PNGTuber 입모양 프레임 4장 경로. 준비 안 됐으면 None."""
    persona = PNGTUBER_PERSONA_BY_CATEGORY.get(category_id)
    if not persona:
        preset_key = None
        try:
            if str(PNGTUBER_DIR) not in sys.path:
                sys.path.insert(0, str(PNGTUBER_DIR))
            from sellfarm_v4.visual_presets import get_preset
            preset_key = get_preset(category_id=category_id)["key"]
        except Exception:
            pass
        persona = PNGTUBER_PERSONA_BY_PRESET.get(preset_key, PNGTUBER_DEFAULT_PERSONA)
    frame_dir = PNGTUBER_AVATAR_ROOT / persona
    frames = [frame_dir / f for f in PNGTUBER_MOUTH_FILES]
    return frames if all(f.exists() for f in frames) else None


def _make_pngtuber_clip(final: Path, t0: float, seg_len: float, frames,
                        tmp_files: list, log=print):
    """본편 [t0, t0+seg_len] 구간 오디오 그대로 반응형 PNGTuber 클립을 즉석 생성해
    반환(실패 시 None). 만든 임시파일은 tmp_files에 등록 — 호출부가 최종 정리한다."""
    try:
        if str(PNGTUBER_DIR) not in sys.path:
            sys.path.insert(0, str(PNGTUBER_DIR))
        import pngtuber_avatar as pnt
        seg_audio = final.parent / f"_pngtuber_seg_{int(t0)}.wav"
        r = subprocess.run(
            ["ffmpeg", "-y", "-nostdin", "-ss", f"{t0:.2f}", "-t", f"{seg_len:.2f}",
             "-i", str(final), "-vn", "-acodec", "pcm_s16le", str(seg_audio)],
            capture_output=True)
        if r.returncode != 0 or not seg_audio.exists():
            log(f"[pip] PNGTuber 오디오 추출 실패: "
                f"{(r.stderr or b'').decode('utf-8', 'replace')[-200:]}")
            return None
        tmp_files.append(seg_audio)
        clip = final.parent / f"_pngtuber_clip_{int(t0)}.mov"
        pnt.generate(str(seg_audio), [str(f) for f in frames], str(clip))
        if not clip.exists():
            return None
        tmp_files.append(clip)
        return clip
    except Exception as e:
        log(f"[pip] PNGTuber 클립 생성 실패: {e}")
        return None


def _is_nobg(p: Path) -> bool:
    return bool(NOBG_PAT.search(p.name)) or p.suffix.lower() in ALPHA_EXT


def _prefer_nobg(files: list) -> list:
    nobg = [f for f in files if _is_nobg(f)]
    return nobg if nobg else files


def _probe(path):
    """(duration, width, height) — 실패 시 (0,0,0)"""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_format", "-show_streams", str(path)],
            capture_output=True, text=True, encoding="utf-8", timeout=30)
        j = json.loads(r.stdout)
        dur = float(j["format"]["duration"])
        v = next(s for s in j["streams"] if s["codec_type"] == "video")
        return dur, int(v["width"]), int(v["height"])
    except Exception:
        return 0.0, 0, 0


def _load_state(pool: Path):
    f = pool / STATE_FILE
    state = {"enabled": True, "pos_index": 0, "usage": {}, "avatar_offset": 0}
    if f.exists():
        try:
            state.update(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            pass
    return state


def _save_state(pool: Path, state):
    # 원자적 저장 (쓰다 죽어도 상태 파일 보존)
    f = pool / STATE_FILE
    tmp = f.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(str(tmp), str(f))


def _pick_least_used(files, usage):
    return min(files, key=lambda p: (usage.get(p.name, 0), p.name))


def apply_pip(final_path, ffmpeg="ffmpeg", pool_dir=None, log=print, category_id=None):
    """final.mp4 위에 PIP를 얹어 같은 경로에 저장. 실패해도 예외를 던지지 않고
    None 반환 (빌드 파이프라인을 절대 멈추지 않는다). 성공 시 배치 정보 dict.
    category_id: PNGTuber 슬롯이 걸릴 때 페르소나 선택에 씀(없으면 정장 폴백)."""
    try:
        with _PIP_PROC_LOCK:
            return _apply_pip(Path(final_path), ffmpeg,
                              Path(pool_dir or os.environ.get("SELLFARM_PIP_POOL", DEFAULT_POOL)),
                              log, category_id)
    except Exception as e:
        log(f"[pip] 실패 (본편은 그대로 유지): {e}")
        return None


def _apply_pip(final: Path, ffmpeg, pool: Path, log, category_id=None):
    if os.environ.get("SELLFARM_PIP_ENABLED", "1") == "0":
        log("[pip] SELLFARM_PIP_ENABLED=0 — 건너뜀")
        return None
    if not final.exists():
        log(f"[pip] 대상 없음: {final}")
        return None
    if not pool.exists():
        log(f"[pip] 풀 폴더 없음 (G드라이브 확인): {pool} — 건너뜀")
        return None

    state = _load_state(pool)
    if not state.get("enabled", True):
        log("[pip] _pip_state.json enabled=false — 건너뜀")
        return None

    vid_exts = {".mp4", ".webm", ".mov"}
    bodies = _prefer_nobg(sorted(
        p for p in pool.glob("body_*") if p.suffix.lower() in vid_exts))
    avatars = _prefer_nobg(sorted(
        p for p in pool.glob("avatar_*") if p.suffix.lower() in vid_exts))
    if not bodies:
        log("[pip] 바디캠 조각이 없음 — 건너뜀")
        return None
    if bodies and _is_nobg(bodies[0]):
        log("[pip] 바디캠 배경 제거본 사용")
    if avatars and _is_nobg(avatars[0]):
        log("[pip] 아바타 배경 제거본 사용")

    dur, W, H = _probe(final)
    if dur <= 0:
        log("[pip] 본편 분석 실패 — 건너뜀")
        return None

    # 삽입 계획: (시각, 종류)
    if dur < 90:
        plan = [(2.0, "body")]
    elif dur < 300:
        plan = [(2.0, "body"), (dur * 0.45, "avatar")]
    else:
        plan = [(2.0, "body"), (dur * 0.45, "avatar"), (dur * 0.78, "body")]
    pngtuber_frames = _pngtuber_frames(category_id)
    if not avatars and not pngtuber_frames:
        plan = [(t, "body") for t, _ in plan]

    usage = state.setdefault("usage", {})
    pos_i = state.get("pos_index", 0)
    av_off = state.get("avatar_offset", 0)
    av_mode = state.get("avatar_mode_index", 0)

    inputs, filters, placements = [], [], []
    prev_label = "0:v"
    used_names = set()
    pngtuber_names = set()
    tmp_files: list[Path] = []

    for n, (t0, kind) in enumerate(plan):
        content_kind = kind
        if kind == "body":
            cands = [b for b in bodies if b.name not in used_names] or bodies
            clip = _pick_least_used(cands, usage)
            c_dur, _, _ = _probe(clip)
            seg_len = min(c_dur, 15.0)
            ss = 0.0
        else:
            # "avatar" 슬롯: 정적 풀 vs PNGTuber를 홀짝으로 번갈아 씀(3종 로테이션)
            use_pngtuber = bool(pngtuber_frames) and (not avatars or av_mode % 2 == 1)
            if use_pngtuber:
                content_kind = "pngtuber"
                seg_len = AVATAR_SEG_SEC
                clip = _make_pngtuber_clip(final, t0, seg_len, pngtuber_frames,
                                           tmp_files, log)
                c_dur = seg_len if clip else 0.0
                ss = 0.0
                av_mode += 1
            else:
                cands = [a for a in avatars if a.name not in used_names] or avatars
                clip = _pick_least_used(cands, usage)
                c_dur, _, _ = _probe(clip)
                seg_len = min(AVATAR_SEG_SEC, c_dur)
                max_off = max(0.0, c_dur - seg_len - 0.5)
                ss = min(float(av_off % 4) * 5.0, max_off)
                av_off += 1
                if pngtuber_frames:
                    av_mode += 1
        if c_dur <= 0:
            continue

        # 본편 끝 3초 안쪽으로 밀리지 않게 보정
        t0 = min(t0, max(0.5, dur - seg_len - 3.0))
        used_names.add(clip.name)
        if content_kind == "pngtuber":
            pngtuber_names.add(clip.name)   # 즉석 생성분 — 재사용 풀 집계 제외
        else:
            usage[clip.name] = usage.get(clip.name, 0) + 1

        pos_name, xe, ye = POSITIONS[pos_i % len(POSITIONS)]
        pos_i += 1

        idx = len(placements) + 1  # 입력 0 = 본편, 이후 조각 순서대로
        dec = []
        if clip.suffix.lower() == ".webm":
            dec = ["-c:v", "libvpx-vp9"]   # 네이티브 vp9 디코더는 알파를 버림
        inputs += dec + ["-ss", f"{ss:.2f}", "-t", f"{seg_len:.2f}", "-i", str(clip)]
        pw = int(W * PIP_WIDTH_RATIO) // 2 * 2
        # 배경 투명 처리: _gs/green=그린 크로마키, _bk=검정 colorkey, 알파본=그대로
        key = ""
        low = clip.name.lower()
        if clip.suffix.lower() not in ALPHA_EXT:
            if "_gs" in low or "green" in low:
                key = "chromakey=0x00FF00:0.30:0.10,despill=type=green,"
            elif "_bk" in low or "_nobg" in low:
                # 캡컷 컷아웃 배경은 순수 검정 — 임계값을 좁게 잡아
                # 어두운 옷·마이크가 같이 뚫리지 않게 한다
                key = "colorkey=0x000000:0.04:0.02,"
        filters.append(
            f"[{idx}:v]scale={pw}:-2,{key}format=yuva420p,"
            f"fade=t=in:st=0:d={FADE_SEC}:alpha=1,"
            f"fade=t=out:st={seg_len - FADE_SEC:.2f}:d={FADE_SEC}:alpha=1,"
            f"setpts=PTS-STARTPTS+{t0:.3f}/TB[p{n}]")
        out_label = f"v{n}"
        filters.append(
            f"[{prev_label}][p{n}]overlay=x={xe}:y={ye}:eof_action=pass[{out_label}]")
        prev_label = out_label
        placements.append({"clip": clip.name, "종류": content_kind, "위치": pos_name,
                           "시작": round(t0, 1), "길이": round(seg_len, 1)})

    if not placements:
        log("[pip] 배치할 조각 없음 — 건너뜀")
        return None

    tmp = final.parent / "_pip_tmp.mp4"
    cmd = [ffmpeg, "-y", "-nostdin", "-i", str(final)] + inputs + [
        "-filter_complex", ";".join(filters),
        "-map", f"[{prev_label}]", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        "-pix_fmt", "yuv420p", "-c:a", "copy", str(tmp)]
    try:
        try:
            # timeout: 본편 길이 비례 (G드라이브 스톨로 빌드 스레드가 영구 대기하던 문제)
            r = subprocess.run(cmd, capture_output=True,
                               timeout=max(600, int(dur) * 10))
        except subprocess.TimeoutExpired:
            log(f"[pip] ffmpeg timeout — 본편 유지")
            if tmp.exists():
                tmp.unlink()
            return None
        if r.returncode != 0 or not tmp.exists() or tmp.stat().st_size == 0:
            err = r.stderr.decode("utf-8", errors="replace")[-300:] if r.stderr else "?"
            log(f"[pip] ffmpeg 실패 — 본편 유지: {err}")
            if tmp.exists():
                tmp.unlink()
            return None

        os.replace(str(tmp), str(final))
        # 2026-07-03: 저장 직전 디스크 상태를 다시 읽어 증분 병합 — 인코딩(수 분) 동안
        # 다른 프로세스/PC가 갱신한 사용 기록을 덮어쓰지 않게 (G드라이브 공유 풀)
        fresh = _load_state(pool)
        fresh_usage = fresh.setdefault("usage", {})
        for _nm in used_names - pngtuber_names:   # 즉석 생성분은 풀 집계에서 제외
            fresh_usage[_nm] = fresh_usage.get(_nm, 0) + 1
        fresh["pos_index"] = pos_i % len(POSITIONS)
        fresh["avatar_offset"] = av_off
        fresh["avatar_mode_index"] = av_mode
        fresh["last_pick"] = {"clips": sorted(used_names)}
        _save_state(pool, fresh)
        usage = fresh_usage   # 아래 로그·미사용 집계용

        for p in placements:
            log(f"[pip] {p['종류']} {p['clip']} → {p['위치']} @{p['시작']}s ({p['길이']}초)")
        fresh = sum(1 for b in bodies if usage.get(b.name, 0) == 0)
        if fresh == 0:
            log("[pip] ⚠ 모든 바디캠 컷을 1회 이상 사용 — 재촬영 권장 (바디캠_시작.bat)")
        return {"placements": placements, "남은_미사용_바디컷": fresh}
    finally:
        for f in tmp_files:   # 세그먼트 오디오·PNGTuber 클립 임시파일 정리
            try:
                if f.exists():
                    f.unlink()
            except OSError:
                pass


def main():
    import argparse
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--pool", default=None)
    args = ap.parse_args()
    info = apply_pip(args.video, pool_dir=args.pool)
    print("[완료]" if info else "[건너뜀/실패]")


if __name__ == "__main__":
    main()
