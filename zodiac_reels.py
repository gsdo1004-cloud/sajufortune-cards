# -*- coding: utf-8 -*-
"""
띠별운세 릴스(세로 영상 + TTS 내레이션) 생성 + 스레드 VIDEO 발행
====================================================================
- 카드(4:5)를 9:16 세로로 Ken Burns 줌 + 배경 여백(핑크)
- 컷별 Edge TTS(무료) 내레이션 → 컷 길이를 내레이션에 맞춰 동적 조정 (릴스용 ~70초)
- 스레드 VIDEO 발행 (media_type=VIDEO, 처리 status 폴링)
- 출력: reels/{날짜}_tts.mp4 (릴스/쇼츠/틱톡/스레드 호환)

실행: python zodiac_reels.py generate [YYYY-MM-DD]   # 릴스 mp4 생성
      python zodiac_reels.py publish  [YYYY-MM-DD]   # (커밋 후) 스레드 영상 발행
전제: ffmpeg, edge-tts, 카드 PNG(zodiac_cardnews.py generate 먼저)
"""
import os
import sys
import time
import json
import asyncio
import subprocess
import datetime as dt
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import zodiac_seo as zs

try:
    import edge_tts
except ImportError:
    raise SystemExit("pip install edge-tts --break-system-packages")

W, H = 1080, 1920
FPS = 30
BG = "0xFBE4EE"
VOICE = "ko-KR-SunHiNeural"
BASE = Path(__file__).resolve().parent
ORDER = ["rat", "ox", "tiger", "rabbit", "dragon", "snake",
         "horse", "goat", "monkey", "rooster", "dog", "pig"]

# ── 오행 BGM (2026-07-11) — 그날 일진 지지 오행에 맞는 자작 주파수 음악을 은은하게 ──
# 카드 틴트(zodiac_cardnews.ELEM_THEME)와 세트: 색·음악이 함께 '그날의 기운' 표현.
# 클립: 자작 WAV에서 90초 발췌, loudnorm(-20LUFS) 통일. 볼륨 11%+페이드 → TTS 명료도 유지.
BGM_MAP = {
    "수": "bgm_water.mp3",   # 528Hz 깊은수면+비 (물)
    "목": "bgm_wood.mp3",    # 888Hz 긍정에너지 (성장)
    "토": "bgm_earth.mp3",   # 432Hz 스트레스 해소 (안정)
    "화": "bgm_fire.mp3",    # 888Hz 황금 로파이 (따뜻한 활력)
    "금": "bgm_metal.mp3",   # 888Hz 금전운 (황금)
}


def _mix_bgm(video, date_iso):
    """완성 릴스에 일진 오행 BGM을 깔아 오디오만 재믹싱. 실패해도 원본(무음 BGM) 유지."""
    from ganzhi_zodiac import day_context
    elem = day_context(dt.date.fromisoformat(date_iso))["branch_elem"]
    bgm = BASE / "bgm" / BGM_MAP.get(elem, "bgm_earth.mp3")
    if not bgm.exists():
        print(f"[WARN] BGM 파일 없음({bgm.name}) — 무음 유지")
        return video
    dur = _dur(video)
    fade_out = max(0.0, dur - 2.0)
    tmp = video.with_name(video.stem + "_bgm.mp4")
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(video), "-stream_loop", "-1", "-i", str(bgm),
             "-filter_complex",
             f"[1:a]volume=0.11,afade=t=in:d=1.5,afade=t=out:st={fade_out:.2f}:d=2[bg];"
             f"[0:a][bg]amix=inputs=2:duration=first:normalize=0[a]",
             "-map", "0:v", "-map", "[a]", "-c:v", "copy",
             "-c:a", "aac", "-b:a", "128k", "-t", f"{dur:.2f}", str(tmp)],
            check=True, capture_output=True)
        tmp.replace(video)
        print(f"[OK] BGM 믹스: {elem}의 기운 → {bgm.name} (vol 11%, fade)")
    except subprocess.CalledProcessError as e:
        print(f"[WARN] BGM 믹스 실패 — 무음으로 진행: {e.stderr[-300:] if e.stderr else e}")
        if tmp.exists():
            tmp.unlink()
    return video

GH_USER = "gsdo1004-cloud"
GH_REPO = "sajufortune-cards"
RAW_BASE = f"https://raw.githubusercontent.com/{GH_USER}/{GH_REPO}/main"
SITE = "sajufortune.kr"


def date_full(di):
    d = dt.date.fromisoformat(di)
    wd = ["월", "화", "수", "목", "금", "토", "일"][d.weekday()]
    return f"{d.year}년 {d.month}월 {d.day}일 {wd}요일"


def _oa(date_iso):
    # 2026-07-11 간지 재설계: 총운 풀 랜덤 → 그날 일진×띠 관계 리드 (명리 근거 내레이션)
    d = dt.date.fromisoformat(date_iso)
    seen, OA = set(), {}
    for s in ORDER:
        lead = zs.zodiac_day(s, d)["lead"]
        txt = lead
        if lead in seen:
            r = zs.make_reading(s, date_iso)
            if ". " in r.overall:
                txt = r.overall.split(". ", 1)[1]  # 관계 리드 중복 시 기조 문장으로
        seen.add(lead)
        OA[s] = txt
    return OA


def narration_lines(date_iso):
    R = {s: zs.make_reading(s, date_iso) for s in ORDER}
    OA = _oa(date_iso)
    lines = [f"{date_full(date_iso)} 오늘의 띠별 운세. 내 띠는 오늘 어떤 흐름일까요?"]
    for i in range(0, 12, 3):
        grp = ORDER[i:i + 3]
        t = ""
        for s in grp:
            seg = OA[s].replace("오늘은 ", "").split(".")[0].strip()
            seg = seg.replace(" — ", ", ")  # TTS가 대시를 읽지 않도록
            t += f"{R[s].sign_ko}, {seg}. "
        lines.append(t)
    top = sorted(ORDER, key=lambda s: R[s].overall_score, reverse=True)[:3]
    lines.append(
        f"오늘 운이 좋은 띠는 {', '.join(R[s].sign_ko for s in top)}. "
        f"자세한 운세는 사주포춘에서 확인하세요."
    )
    return lines


def _tts(text, out_mp3):
    async def go():
        await edge_tts.Communicate(text, VOICE, rate="+6%").save(str(out_mp3))
    asyncio.run(go())


def _dur(path):
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "json", str(path)],
        capture_output=True, text=True)
    return float(json.loads(r.stdout)["format"]["duration"])


def make_reel_tts(date_iso):
    cards = sorted((BASE / "cards" / date_iso).glob("card_*.png"))
    if not cards:
        raise SystemExit(f"[FAIL] 카드 없음: {date_iso} (generate 먼저)")
    narrs = narration_lines(date_iso)
    n = min(len(cards), len(narrs))

    tmp = BASE / "cards" / date_iso / "_reel"
    tmp.mkdir(exist_ok=True)

    clips = []
    for i in range(n):
        mp3 = tmp / f"n{i}.mp3"
        _tts(narrs[i], mp3)
        L = round(_dur(mp3) + 0.7, 2)
        clip = tmp / f"c{i:02d}.mp4"
        vf = (f"scale=1080:1350,"
              f"zoompan=z='min(zoom+0.0008,1.10)':d={int(L * FPS)}:s=1080x1350:fps={FPS},"
              f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color={BG},format=yuv420p")
        subprocess.run(
            ["ffmpeg", "-y", "-loop", "1", "-i", str(cards[i]), "-i", str(mp3),
             "-t", str(L), "-vf", vf, "-r", str(FPS), "-af", "apad",
             "-c:v", "libx264", "-preset", "veryfast",
             "-c:a", "aac", "-b:a", "128k", "-pix_fmt", "yuv420p", str(clip)],
            check=True, capture_output=True)
        clips.append(clip)

    lst = tmp / "list.txt"
    lst.write_text("".join(f"file '{c.as_posix()}'\n" for c in clips), encoding="utf-8")
    out = BASE / "reels" / f"{date_iso}_tts.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
         "-c", "copy", str(out)],
        check=True, capture_output=True)

    for f in tmp.glob("*"):
        f.unlink()
    tmp.rmdir()
    _mix_bgm(out, date_iso)  # 2026-07-11 일진 오행 BGM (은은하게 11%)
    print(f"[OK] reel+TTS → {out} ({n}컷, 약 {round(_dur(out), 1)}초, {W}x{H})")
    return out


# ── 스레드 VIDEO 발행 ──
def _post(url, data):
    import requests
    return requests.post(url, data=data, timeout=60).json()


def publish_video(video_url, caption):
    import requests
    tok = os.environ["THREADS_ACCESS_TOKEN"]
    uid = os.environ["THREADS_USER_ID"]
    base = f"https://graph.threads.net/v1.0/{uid}"

    j = _post(f"{base}/threads", {
        "media_type": "VIDEO", "video_url": video_url,
        "text": caption, "access_token": tok})
    cid = j.get("id")
    if not cid:
        raise SystemExit(f"[FAIL] video container: {j}")

    # 비디오 처리 대기 (status 폴링 — VIDEO는 트랜스코딩 시간 필요)
    for _ in range(30):
        time.sleep(6)
        st = requests.get(f"{base}/{cid}",
                          params={"fields": "status", "access_token": tok},
                          timeout=30).json()
        s = st.get("status")
        if s == "FINISHED":
            break
        if s == "ERROR":
            raise SystemExit(f"[FAIL] video processing: {st}")

    j = _post(f"{base}/threads_publish", {"creation_id": cid, "access_token": tok})
    pid = j.get("id")
    if not pid:
        raise SystemExit(f"[FAIL] publish: {j}")
    print(f"[OK] published video: {pid}")
    return pid


def publish_reply(post_id, text):
    tok = os.environ["THREADS_ACCESS_TOKEN"]
    uid = os.environ["THREADS_USER_ID"]
    base = f"https://graph.threads.net/v1.0/{uid}"
    j = _post(f"{base}/threads", {
        "media_type": "TEXT", "text": text,
        "reply_to_id": post_id, "access_token": tok})
    cid = j.get("id")
    if not cid:
        print(f"[WARN] reply container: {j}")
        return
    time.sleep(3)
    j = _post(f"{base}/threads_publish", {"creation_id": cid, "access_token": tok})
    print(f"[OK] reply: {j.get('id')}")


def do_publish(date_iso):
    url = f"{RAW_BASE}/reels/{date_iso}_tts.mp4"
    caption = (f"{date_full(date_iso)} 오늘의 띠별 운세 🔮\n"
               f"영상으로 보는 12띠 오늘의 흐름\n\n"
               f"#오늘의운세 #띠별운세 #사주 #운세 #릴스")
    pid = publish_video(url, caption)
    publish_reply(pid, f"내 띠 운세 자세히 →\nhttps://{SITE}/zodiac")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "generate"
    di = sys.argv[2] if len(sys.argv) > 2 else zs.today_iso()
    if mode == "generate":
        make_reel_tts(di)
    elif mode == "publish":
        do_publish(di)
    else:
        raise SystemExit("사용법: python zodiac_reels.py [generate|publish] [YYYY-MM-DD]")
