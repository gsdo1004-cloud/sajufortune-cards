# -*- coding: utf-8 -*-
"""zodiac_month_shorts.py — 월간 띠별운세 쇼츠 3종 조립 (2026-07-25)

  short30 : ~30초  표지 + 12띠 한 화면(일시정지해 읽는 구간) + 마무리
  short60 : ~60초  표지 + 3띠씩 4장 + 마무리
  short80 : ~80초  표지 + 요약 + 12띠 개별 + 마무리   ← 가장 세분화

일일 쇼츠와 같은 원칙을 그대로 따른다.
  - 프로필 유입 배지는 카드 상단에 (하단은 유튜브 UI가 덮는다)
  - PNGTuber 반응형 아바타 PIP를 얹는다 (zodiac_shorts의 함수 재사용)
  - 실패해도 빌드를 멈추지 않는다

산출물은 로컬에서 만들고 완성본만 구글드라이브로 복사한다.
G드라이브를 작업폴더로 쓰면 CFAPI 충돌로 hang이 나므로 '작업은 로컬, 보관만 G'를 지킨다.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import shutil
import subprocess
import sys
from pathlib import Path

import zodiac_shorts as zs_mod
from zodiac_month import (all_month_readings, month_label,
                          select_featured_month_readings)
from zodiac_month_cards import (make_cardnews, make_onepage, make_outro_card,
                                make_shorts_cards)

BASE = Path(__file__).resolve().parent
VIDEO_ROOT = Path(__import__("os").environ.get("ZODIAC_VIDEO_ROOT", r"D:\shorts_work\zodiac_monthly"))
W, H, FPS = 1080, 1920, 30
GDRIVE_ROOT = Path(r"G:\내 드라이브\01클로드\운세쇼츠")

try:
    import typecast_tts
except Exception:                      # TTS가 없어도 무음으로 만들 수 있게
    typecast_tts = None


def log(msg: str) -> None:
    print(f"[month-shorts {_dt.datetime.now():%H:%M:%S}] {msg}", flush=True)


def _dur(p: Path) -> float:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(p)],
            capture_output=True, text=True, check=True).stdout.strip()
        return float(out)
    except Exception:
        return 0.0


def _tts(text: str, out: Path, day: _dt.date) -> float:
    """나레이션 생성. 실패하면 0초를 돌려주고 무음으로 진행한다."""
    if typecast_tts is None:
        return 0.0
    try:
        typecast_tts.synth(text, out, day, log=log)
        return _dur(out)
    except Exception as e:
        log(f"  [!] TTS 실패({e}) — 무음으로 진행")
        return 0.0


# ── 켄번 효과 (2026-07-25) ────────────────────────────────────
# 표준: 3배 lanczos 업스케일 + 줌 18% + 모션 4종 로테이션. 떨림 금지.
# 3배로 키운 뒤 줌해야 확대 구간에서 픽셀이 뭉개지지 않는다. x/y는 프레임당 변화가
# 미세해야 하며, 급격히 움직이면 글자가 흔들려 읽기가 어려워진다.
KEN_ZOOM = 0.18          # 최대 확대율 18%
KEN_MOVES = [
    ("center_in",  "iw/2-(iw/zoom/2)",                    "ih/2-(ih/zoom/2)"),
    ("top_down",   "iw/2-(iw/zoom/2)",                    "(ih-ih/zoom)*on/{F}"),
    ("left_right", "(iw-iw/zoom)*on/{F}",                 "ih/2-(ih/zoom/2)"),
    ("diag",       "(iw-iw/zoom)*on/{F}*0.7",             "(ih-ih/zoom)*on/{F}*0.7"),
]


def _clip(img: Path, seconds: float, audio: Path | None, out: Path,
          move_idx: int = 0, zoom_ratio: float = KEN_ZOOM) -> Path:
    """정지 이미지 + (선택)오디오 → 켄번 클립.

    글자를 읽는 카드라 움직임은 느리게. 프레임당 증가분을 길이에 맞춰 계산해
    클립이 길어도 짧아도 '끝날 때 정확히 18% 확대'가 되도록 한다.
    """
    frames = max(1, int(seconds * FPS))
    step = zoom_ratio / frames                      # 프레임당 확대량
    name, xe, ye = KEN_MOVES[move_idx % len(KEN_MOVES)]
    z = f"min(1.0+{step:.6f}*on,{1.0 + zoom_ratio:.3f})"
    x = xe.replace("{F}", str(frames))
    y = ye.replace("{F}", str(frames))
    vf = (f"scale={W*3}:{H*3}:flags=lanczos,"
          f"zoompan=z='{z}':x='{x}':y='{y}'"
          f":d={frames}:s={W}x{H}:fps={FPS},format=yuv420p")
    cmd = ["ffmpeg", "-y", "-loop", "1", "-i", str(img)]
    if audio and audio.exists() and _dur(audio) > 0:
        cmd += ["-i", str(audio), "-af", "apad"]
    else:
        cmd += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
    cmd += ["-t", f"{seconds:.2f}", "-vf", vf, "-r", str(FPS),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
            "-pix_fmt", "yuv420p", str(out)]
    subprocess.run(cmd, check=True, capture_output=True)
    return out


def _concat(clips: list[Path], out: Path, tmp: Path) -> Path:
    lst = tmp / "concat.txt"
    lst.write_text("".join(f"file '{c.as_posix()}'\n" for c in clips), encoding="utf-8")
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
                    "-c", "copy", str(out)], check=True, capture_output=True)
    return out


def _pngtuber(video: Path, day: _dt.date) -> None:
    """PNGTuber 아바타 PIP — 일일 쇼츠와 동일 함수를 그대로 쓴다."""
    try:
        zs_mod._apply_pngtuber_pip(video, day)
        log("  PNGTuber PIP 적용")
    except Exception as e:
        log(f"  [!] PNGTuber 생략({e})")


# ── 유입 문구는 그림이 아니라 나레이션으로 ────────────────────
# AI 카드에 배지를 얹으니 카드마다 제목·띠 이름 위치가 달라 '8월'·'쥐띠'·'닭띠'를 덮었다.
# (자동 배치 3회 시도 실패) 한밝님 지시로 유입 문구는 TTS로 말한다.
CTA_MID = "자세한 운세는 프로필 링크에서 무료로 보실 수 있습니다."
# 마무리 카드는 Pillow라 글자가 깨지지 않는다 — 가격·URL은 화면이 맡고 목소리는 '무료'만 말한다.
# (길게 읽으면 30초판이 상한 32초를 넘는다)
CTA_END = "전체 운세는 프로필 링크에서 무료로 보실 수 있습니다."


# ── 3종 구성 정의 ────────────────────────────────────────
def _plan(kind: str, cards: dict, rs: list[dict], year: int, month: int) -> list[tuple]:
    """(이미지, 길이초, 나레이션) 목록.

    AI 카드 모드(개별 12장이 없음)에서는 3띠 그룹 카드를 길게 쓰고, 화면에 없는
    개별 정보는 나레이션이 대신 읽는다.
    """
    ml = month_label(year, month)
    intro = f"{year}년 {month}월, {ml} 띠별 운세입니다."
    ai = not cards.get("single")

    if kind == "30":
        return [(cards["cover"], 3.5, intro),
                (cards["summary"], 21.0, f"내 띠를 찾아보세요. {CTA_MID}"),
                (cards["outro"], 4.0, CTA_END)]
    if kind == "60":
        items = [(cards["cover"], 4.0, intro)]
        for gi, p in enumerate(cards["group"]):
            g = rs[gi * 3:(gi + 1) * 3]
            names = " ".join(r["sign_ko"] for r in g)
            narr = f"{names} 운세입니다."
            if gi == 1:                      # 중간에 한 번만 — 매 클립마다 넣으면 광고처럼 들린다
                narr += f" {CTA_MID}"
            items.append((p, 12.0, narr))
        items.append((cards["outro"], 4.5, CTA_END))
        return items

    # 80초 — 가장 세분화.
    # 나레이션에 advice까지 넣었더니 클립마다 5초를 크게 넘겨 총 105초가 됐다(실측).
    # 띠 이름과 한 줄 요약까지만 읽고, 상세는 화면에서 읽게 둔다.
    if not ai:
        items = [(cards["cover"], 3.5, intro), (cards["summary"], 7.0, "먼저 전체 흐름입니다.")]
        for r, p in zip(rs, cards["single"]):
            items.append((p, 5.0, f"{r['sign_ko']}, {r['headline']}"))
        items.append((cards["outro"], 4.0, CTA_END))
        return items

    # AI 카드 모드: 개별 12장이 없으므로 그룹 4장을 길게 두고 3띠씩 읽어준다.
    items = [(cards["cover"], 3.5, intro),
             (cards["summary"], 9.0, "먼저 열두 띠 전체 흐름입니다. 내 띠를 찾아보세요.")]
    for gi, p in enumerate(cards["group"]):
        g = rs[gi * 3:(gi + 1) * 3]
        narr = " ".join(f"{r['sign_ko']}, {r['headline']}." for r in g)
        if gi == 1:
            narr += f" {CTA_MID}"
        items.append((p, 15.0, narr))
    items.append((cards["outro"], 4.5, CTA_END))
    return items


# 각 판의 상한(초). 넘으면 경고를 남긴다 — 플랫폼 규격과 한밝님 요청 기준.
TARGET_MAX = {"30": 32.0, "60": 60.0, "80": 80.0}

# PNGTuber 아바타를 얹지 않을 판 — 월간은 **전부 생략**(한밝님 결정 2026-07-25).
# AI 카드는 달마다 구도가 바뀐다. 8월(한옥 유화)에서는 좌측 아바타가 그림만 가렸는데,
# 9월(부채꼴 구도)에서는 '토끼띠' 이름과 한 줄 요약을 덮었다. 어느 위치도 안전하지 않다.
# 아바타 위치는 G드라이브 공용 모듈(일일 쇼츠·셀팜 공유)이 좌측 3종 로테이션으로 정하므로
# 공용 모듈은 건드리지 않는다. '사람 흔적' 신호는 매일 18시 일일 쇼츠가 계속 낸다.
PIP_SKIP = {"30", "60", "80"}


def build(kind: str, year: int, month: int, cards: dict, rs: list[dict], out_dir: Path) -> Path:
    day = _dt.date(year, month, 1)
    tmp = out_dir / f"_tmp{kind}"
    tmp.mkdir(parents=True, exist_ok=True)
    clips: list[Path] = []
    for i, (img, sec, narr) in enumerate(_plan(kind, cards, rs, year, month)):
        mp3 = tmp / f"n{i}.mp3"
        dur = _tts(narr, mp3, day) if narr else 0.0
        sec = max(sec, round(dur + 0.4, 2)) if dur else sec
        # 모션 4종을 클립마다 돌린다(같은 방향만 반복하면 지루하다).
        clips.append(_clip(Path(img), sec, mp3 if dur else None, tmp / f"c{i}.mp4",
                           move_idx=i))
    out = out_dir / f"{year}-{month:02d}_월간띠별운세_{kind}초.mp4"
    _concat(clips, out, tmp)
    if kind in PIP_SKIP:
        log("  아바타 PIP 생략 — 카드 글자를 가리지 않도록")
    else:
        _pngtuber(out, day)
    total = _dur(out)
    cap = TARGET_MAX.get(kind)
    flag = ""
    if cap and total > cap:
        flag = f"  ⚠️ 상한 {cap:.0f}초 초과 — 나레이션을 줄여야 합니다"
    log(f"  ✅ {out.name} ({total:.1f}초){flag}")
    shutil.rmtree(tmp, ignore_errors=True)
    return out


def _featured_segments(reading: dict, year: int, month: int, card: Path,
                       outro: Path) -> list[tuple[Path, float, str]]:
    """기존 월간 계산 결과로 한 띠의 개별 쇼츠 대본을 만든다."""
    lucky_days = ", ".join(f"{day}일" for day in reading["lucky_days"])
    sign = reading["sign_ko"]
    first = (
        f"{year}년 {month}월 {sign} 월간 운세입니다. {reading['headline']}. "
        f"재물운은 {reading['wealth']} 애정운은 {reading['love']}"
    )
    second = (
        f"건강운은 {reading['health']} 직업운은 {reading['work']} "
        f"{reading['period_note']} 길일은 {lucky_days}입니다. {reading['advice']}"
    )
    return [(card, 18.0, first), (card, 22.0, second), (outro, 4.0, CTA_END)]


def build_featured_sign(reading: dict, year: int, month: int, card: Path,
                        outro: Path, out_dir: Path) -> Path:
    """기존 TTS·영상 조립 함수를 재사용해 선정 띠 한 편을 만든다."""
    out_dir.mkdir(parents=True, exist_ok=True)
    day = _dt.date(year, month, 1)
    tmp = out_dir / f"_tmp_featured_{reading['sign']}"
    tmp.mkdir(parents=True, exist_ok=True)
    clips: list[Path] = []
    for index, (image, seconds, narration) in enumerate(
            _featured_segments(reading, year, month, card, outro)):
        mp3 = tmp / f"n{index}.mp3"
        duration = _tts(narration, mp3, day)
        seconds = max(seconds, round(duration + 0.4, 2)) if duration else seconds
        clips.append(_clip(image, seconds, mp3 if duration else None,
                           tmp / f"c{index}.mp4", move_idx=index))
    out = out_dir / f"{year}-{month:02d}_월간_{reading['sign_ko']}띠_개별운세.mp4"
    _concat(clips, out, tmp)
    # 카드 글자가 핵심 정보이므로 기존 PIP 생략 정책을 유지한다.
    log(f"  개별 {reading['sign_ko']}띠: 카드 글자 보호를 위해 PNGTuber PIP 생략")
    log(f"  개별 영상 {out.name} ({_dur(out):.1f}초)")
    shutil.rmtree(tmp, ignore_errors=True)
    return out


def deploy_gdrive(local_dir: Path, year: int, month: int) -> Path | None:
    """완성본을 구글드라이브 보관 폴더로 복사. 실패해도 로컬 산출물은 남는다."""
    dest = GDRIVE_ROOT / f"{year}-{month:02d}_월간띠별운세"
    try:
        dest.mkdir(parents=True, exist_ok=True)
        n = 0
        for p in local_dir.rglob("*"):
            if p.is_file() and p.suffix.lower() in (".mp4", ".png", ".json"):
                tgt = dest / p.relative_to(local_dir)
                tgt.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, tgt)
                n += 1
        log(f"  구글드라이브 복사 {n}개 → {dest}")
        return dest
    except Exception as e:
        log(f"  [!] 구글드라이브 복사 실패({e}) — 로컬에는 그대로 있습니다: {local_dir}")
        return None


def load_ai_cards(year: int, month: int, root: Path) -> dict | None:
    """Topview가 만든 AI 카드 6장을 쇼츠 카드 자리에 끼운다.

    card_01=표지 / card_02~05=3띠 그룹 / card_06=12띠 종합 (zodiac_month_topview 순서).
    마무리 카드만은 Pillow로 만든다 — URL·가격 글자는 AI가 그리면 깨진다.
    6장이 다 있지 않으면 None을 돌려주고, 호출부가 Pillow 카드로 되돌아간다.
    """
    d = BASE / "month" / f"{year}-{month:02d}" / "ai_cards"
    ps = [d / f"card_{i:02d}.png" for i in range(1, 7)]
    if not all(p.exists() and p.stat().st_size > 50_000 for p in ps):
        return None
    return {"cover": ps[0], "group": ps[1:5], "summary": ps[5], "single": [],
            "outro": make_outro_card(year, month, root / "shorts_cards" / "s_outro.png")}


def run(year: int, month: int, kinds=("30", "60", "80"), gdrive: bool = True,
        ai: bool = True, featured_limit: int = 3) -> dict:
    root = VIDEO_ROOT / f"{year}-{month:02d}"
    root.mkdir(parents=True, exist_ok=True)
    log(f"{year}년 {month}월 ({month_label(year, month)}) 월간 콘텐츠 생성 시작")

    rs = all_month_readings(year, month)
    onepage = make_onepage(year, month, root / "onepage.png")
    cardnews = make_cardnews(year, month, root / "cardnews")

    cards = load_ai_cards(year, month, root) if ai else None
    if cards:
        log("  쇼츠 카드 = AI 카드 6장(표지1·그룹4·종합1) + 마무리 1")
    else:
        if ai:
            log("  [!] AI 카드 6장이 없어 Pillow 카드로 조립합니다")
        cards = make_shorts_cards(year, month, root / "shorts_cards")
    log(f"  카드 완료 — 한장뉴스 1 · 카드뉴스 {len(cardnews)} · 쇼츠카드 {2 + len(cards['group']) + len(cards['single'])}")

    videos = [build(k, year, month, cards, rs, root) for k in kinds]

    # AI 월간 카드에는 단일 띠 카드가 없으므로, 이 3편의 보조 자산으로만 기존
    # Pillow 단일 카드 생성기를 쓴다. 새 이미지 렌더러를 추가하지 않는다.
    detail_cards = cards if cards.get("single") else make_shorts_cards(
        year, month, root / "shorts_cards")
    single_by_sign = {reading["sign"]: card for reading, card in
                      zip(rs, detail_cards["single"])}
    featured = select_featured_month_readings(year, month, featured_limit)
    featured_dir = root / "featured"
    featured_videos = [
        build_featured_sign(reading, year, month, single_by_sign[reading["sign"]],
                            detail_cards["outro"], featured_dir)
        for reading in featured
    ]
    selection_path = root / "featured_selection.json"
    selection_path.write_text(json.dumps({
        "year": year,
        "month": month,
        "method": "deterministic_monthly_score_extremity",
        "data_status": (
            "실제 조회수·참여도 데이터 미연결: 월간 총운 점수의 극단성과 "
            "일진 관계에서 계산한 순·중·하순 점수 변동폭으로 선정"
        ),
        "selected": [
            {"sign": reading["sign"], "sign_ko": reading["sign_ko"],
             **reading["featured_selection"]}
            for reading in featured
        ],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"  개별 월간 쇼츠 {len(featured_videos)}개 생성; 선정 근거: {selection_path.name}")
    dest = deploy_gdrive(root, year, month) if gdrive else None
    return {"root": root, "gdrive": dest, "onepage": onepage,
            "cardnews": cardnews, "videos": videos,
            "featured_videos": featured_videos,
            "featured_selection": selection_path}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="월간 띠별운세 쇼츠 3종 + 카드뉴스 + 한장뉴스")
    today = _dt.date.today()
    nxt = _dt.date(today.year + (today.month == 12), (today.month % 12) + 1, 1)
    ap.add_argument("--year", type=int, default=nxt.year)
    ap.add_argument("--month", type=int, default=nxt.month)
    ap.add_argument("--kinds", default="30,60,80")
    ap.add_argument("--no-gdrive", action="store_true")
    ap.add_argument("--pillow", action="store_true", help="AI 카드 대신 Pillow 카드로 조립")
    ap.add_argument("--featured-limit", type=int, default=3,
                    help="추가 생성할 개별 띠 월간 쇼츠 수 (기본 3)")
    a = ap.parse_args()
    r = run(a.year, a.month, tuple(a.kinds.split(",")), gdrive=not a.no_gdrive,
            ai=not a.pillow, featured_limit=a.featured_limit)
    print("\n로컬 :", r["root"])
    print("G드라이브 :", r["gdrive"] or "(복사 안 함)")
    print("선정 근거 :", r["featured_selection"])
    for v in r["featured_videos"]:
        print("  개별 :", v.name)
    for v in r["videos"]:
        print("  영상 :", v.name)
