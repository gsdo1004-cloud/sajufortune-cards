"""대박운세 홍보 카드·쇼츠 생성 — promo_content.py 의 세트를 실물로 만든다.

  python promo_build.py cards free      # 카드 6장 (Topview GPT Image 2)
  python promo_build.py shorts free     # 쇼츠 mp4 (타입캐스트 TTS + PNGTuber PIP)
  python promo_build.py all free        # 둘 다

산출물: promo/{key}/card_01..06.png, promo/{key}/shorts.mp4

띠별운세 일일 파이프라인은 건드리지 않는다. 이미지 엔진(zodiac_topview)·TTS(typecast_tts)·
PNGTuber PIP(zodiac_shorts) 는 기존 모듈을 그대로 빌려 쓴다.
"""
from __future__ import annotations
import subprocess
import datetime as dt
import json
import sys
from pathlib import Path

import promo_content as pc

BASE = Path(__file__).resolve().parent
OUT = BASE / "promo"

W, H, FPS = 1080, 1920, 30
BG = "0x1a2340"
PAD = 0.7               # 컷마다 붙는 여유
CLIP_LIMIT = 85.0       # 네이버 클립 90초 제한에 5초 여유
TARGET_SEC = 80.0
BASE_TEMPO = 1.12       # zodiac_shorts.LONG_TEMPO 와 같은 기준
MAX_TEMPO = 1.35


def log(msg: str) -> None:
    print(f"[promo {dt.datetime.now():%H:%M:%S}] {msg}", flush=True)


def _dur(path: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                        "-of", "json", str(path)], capture_output=True, text=True)
    return float(json.loads(r.stdout)["format"]["duration"])


# ── 카드 6장 ───────────────────────────────────────────────
def build_cards(key: str, quality: str = "medium") -> Path:
    import zodiac_topview as ztv

    s = pc.BY_KEY[key]
    outdir = OUT / key
    outdir.mkdir(parents=True, exist_ok=True)
    client = ztv.make_client()

    for i, card in enumerate(s["cards"], 1):
        dst = outdir / f"card_{i:02d}.png"
        if dst.exists() and ztv.validate_image(dst) is None:
            log(f"{dst.name} 이미 있음 — 건너뜀")
            continue
        log(f"{dst.name} 생성: {card['headline'][:24]}")
        ztv.generate_rest(client, card["prompt"], dst, quality=quality)
        bad = ztv.validate_image(dst)
        if bad:
            log(f"[WARN] {dst.name} 검증 실패({bad}) — 단순 프롬프트로 재시도")
            ztv.generate_rest(client, f"{pc.STYLE}. Korean text \"{card['headline']}\".",
                              dst, quality=quality)
    log(f"카드 완료 → {outdir}")
    return outdir


# ── 쇼츠 ──────────────────────────────────────────────────
def build_shorts(key: str) -> Path:
    import typecast_tts

    s = pc.BY_KEY[key]
    outdir = OUT / key
    cards = sorted(outdir.glob("card_*.png"))
    if len(cards) < len(s["narration"]):
        raise SystemExit(f"[FAIL] 카드가 부족합니다({len(cards)}장) — 먼저 cards 를 만드세요")

    tmp = outdir / "_tmp"
    tmp.mkdir(exist_ok=True)
    today = dt.date.today()

    # 1) 나레이션 먼저 합성해 총 길이를 재고, 상한을 넘으면 말 속도를 올려 재합성.
    mp3s = [tmp / f"n{i}.mp3" for i in range(len(s["narration"]))]
    tempo = BASE_TEMPO
    for _ in range(3):
        total = 0.0
        for mp3, narr in zip(mp3s, s["narration"]):
            typecast_tts.synth(narr, mp3, today, tempo=tempo)
            total += _dur(mp3) + PAD
        if total <= CLIP_LIMIT:
            log(f"길이 {total:.1f}초 (상한 {CLIP_LIMIT}초, tempo={tempo:.2f})")
            break
        new_tempo = round(min(MAX_TEMPO, tempo * (total / TARGET_SEC)), 2)
        if new_tempo <= tempo:
            log(f"[WARN] {total:.1f}초 — tempo 상한. 네이버 클립에서 빠질 수 있음")
            break
        log(f"길이 {total:.1f}초 > {CLIP_LIMIT}초 → tempo {tempo:.2f}→{new_tempo:.2f} 재합성")
        tempo = new_tempo

    # 2) 컷 조립 — 카드를 세로 프레임 가운데 두고 아주 약하게 줌인.
    clips = []
    for i, (img, mp3) in enumerate(zip(cards, mp3s)):
        L = round(_dur(mp3) + PAD, 2)
        clip = tmp / f"c{i:02d}.mp4"
        vf = (f"scale=1080:1350,"
              f"zoompan=z='min(1.0+0.0006*on,1.06)':d={int(L * FPS)}:s=1080x1350:fps={FPS},"
              f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color={BG},format=yuv420p")
        subprocess.run(
            ["ffmpeg", "-y", "-loop", "1", "-i", str(img), "-i", str(mp3),
             "-t", str(L), "-vf", vf, "-r", str(FPS), "-af", "apad",
             "-c:v", "libx264", "-preset", "veryfast",
             "-c:a", "aac", "-b:a", "128k", "-pix_fmt", "yuv420p", str(clip)],
            check=True, capture_output=True)
        clips.append(clip)

    lst = tmp / "list.txt"
    lst.write_text("".join(f"file '{c.as_posix()}'\n" for c in clips), encoding="utf-8")
    out = outdir / "shorts.mp4"
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
                    "-c", "copy", str(out)], check=True, capture_output=True)

    # 3) PNGTuber PIP — 사람이 만든 채널 신호. 실패해도 영상은 그대로 쓴다.
    try:
        import zodiac_shorts
        zodiac_shorts._apply_pngtuber_pip(out, today)
    except Exception as e:
        log(f"[WARN] PNGTuber PIP 생략: {e}")

    log(f"쇼츠 완료 → {out} ({_dur(out):.1f}초)")
    return out


# ── 네이버 블로그 삽화 3장 ──────────────────────────────────
def build_blog_images(quality: str = "medium") -> Path:
    import zodiac_topview as ztv

    outdir = OUT / "blog"
    outdir.mkdir(parents=True, exist_ok=True)
    client = ztv.make_client()
    for spec in pc.BLOG_IMAGES:
        dst = outdir / f"{spec['file']}.png"
        if dst.exists() and ztv.validate_image(dst) is None:
            log(f"{dst.name} 이미 있음 — 건너뜀")
            continue
        log(f"{dst.name} 생성: {spec['alt']}")
        ztv.generate_rest(client, spec["prompt"], dst, quality=quality)
        if ztv.validate_image(dst):
            log(f"[WARN] {dst.name} 검증 실패 — 그대로 사용")
    log(f"블로그 삽화 완료 → {outdir}")
    return outdir


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    if mode == "blog":
        build_blog_images()
        return
    key = sys.argv[2] if len(sys.argv) > 2 else "free"
    if key not in pc.BY_KEY:
        raise SystemExit(f"사용법: python promo_build.py [cards|shorts|all] [{'|'.join(pc.BY_KEY)}]")
    if mode in ("cards", "all"):
        build_cards(key)
    if mode in ("shorts", "all"):
        build_shorts(key)


if __name__ == "__main__":
    main()
