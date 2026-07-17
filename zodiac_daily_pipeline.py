# -*- coding: utf-8 -*-
"""띠별운세 일일 파이프라인 오케스트레이터 (집 PC, 새벽 04:40 스케줄).

흐름 (전 단계 멱등 — 2차 실행이 빈 곳만 메움):
  1. 오늘 5장 보장   ← 평소엔 어제 D+1 선행 생성분이 있어 즉시 통과 (발행 무실패의 핵심)
  2. 내일 5장 선행 생성 (D+1 버퍼) — 오늘 아침 인증이 죽어도 내일 발행은 무사
  3. G드라이브 미러 (틱톡·blog-auto 소스)
  4. 쇼츠 영상 조립 (타입캐스트 성우 로테이션 + BGM 로테이션)
  5. repo 커밋·푸시 → 05:35 GitHub Actions가 쓰레드 캐러셀+영상 발행 (Topview분 우선)
  6. 운명과학TV 쇼츠 업로드 큐 적재 + 멀티업로더 실행
  7. 실패 시 이메일 경보 (zodiac_alert)

실행: python zodiac_daily_pipeline.py [--date YYYY-MM-DD] [--no-upload] [--no-push]
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
import zodiac_topview as zt
import zodiac_alert

NO_WINDOW = 0x08000000 if os.name == "nt" else 0

# 운명과학TV 멀티업로더 (2026-07-17 정찰 확정)
UPLOADER_DIR = Path(r"G:\내 드라이브\01클로드\작업폴더\music_pipeline")
UPLOAD_QUEUE = UPLOADER_DIR / "upload_queue_unmyeong"
# 🔒 비공개 고정 — 한밝님 2026-07-17 확인. [[feedback_youtube_private_default]] 규칙 유지.
# "매일 발행"은 매일 '업로드'까지 자동이라는 뜻이고, 공개 전환은 한밝님이 스튜디오에서 직접.
# ⚠️ 한밝님이 "공개"라고 명시하기 전에는 절대 public으로 바꾸지 말 것.
YT_PRIVACY = "private"


def log(msg: str):
    line = f"[pipeline {dt.datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line)
    try:
        with open(zt.LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def _run(cmd, cwd=None, timeout=600):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                          timeout=timeout, creationflags=NO_WINDOW)


def git_push(dates: list[str], alerts: list[str]) -> bool:
    """cards/{dates}, reels 커밋·푸시. Actions와의 경합은 pull --rebase로 해소."""
    try:
        _run(["git", "pull", "--rebase", "--autostash", "origin", "main"], cwd=BASE)
        _run(["git", "add", "-A", "--"] +
             [f"cards/{d}" for d in dates] + ["reels"], cwd=BASE)
        r = _run(["git", "commit", "-m",
                  f"topview cards+shorts {dates[0]} (+D+1 buffer)"], cwd=BASE)
        if r.returncode != 0 and "nothing to commit" in (r.stdout + r.stderr):
            log("커밋할 변경 없음")
            return True
        for attempt in (1, 2):
            p = _run(["git", "push", "origin", "main"], cwd=BASE)
            if p.returncode == 0:
                log("repo 푸시 완료")
                return True
            log(f"push 실패(시도{attempt}): {p.stderr[-200:]}")
            _run(["git", "pull", "--rebase", "--autostash", "origin", "main"], cwd=BASE)
        alerts.append("git push 2회 실패 — 쓰레드 발행이 레거시 카드로 나갈 수 있음")
        return False
    except Exception as e:
        alerts.append(f"git 단계 예외: {e}")
        return False


def queue_youtube_shorts(date_iso: str, alerts: list[str],
                         do_upload: bool = True) -> bool:
    """쇼츠를 운명과학TV 업로드 큐에 적재 후 멀티업로더 실행."""
    video = BASE / "reels" / f"{date_iso}_tts.mp4"
    if not video.exists():
        alerts.append(f"쇼츠 영상 없음({video.name}) — 유튜브 업로드 생략")
        return False
    meta_src = BASE / "cards" / date_iso / "shorts_meta.json"
    voice = ""
    try:
        m = json.loads(meta_src.read_text(encoding="utf-8"))
        voice = m.get("voice", {}).get("voice", "")
    except Exception:
        pass

    d = dt.date.fromisoformat(date_iso)
    wd = ["월", "화", "수", "목", "금", "토", "일"][d.weekday()]
    title = f"{d.month}월 {d.day}일 {wd}요일 오늘의 띠별운세 🔮 12띠 총정리 #shorts"
    desc = (f"{d.year}년 {d.month}월 {d.day}일 {wd}요일, 12띠 오늘의 운세를 1분에 정리했습니다.\n"
            f"내 띠의 오늘 흐름, 금전운·연애운·건강운까지 확인해 보세요.\n\n"
            f"매일 아침 새로운 띠별운세가 올라옵니다. 구독하시면 놓치지 않아요.\n\n"
            f"#띠별운세 #오늘의운세 #12띠 #사주 #운세 #shorts\n\n"
            f"※ 본 콘텐츠는 전통 명리의 일진 풀이를 바탕으로 한 재미와 참고용입니다. "
            f"중요한 결정은 신중히 판단해 주세요.")
    try:
        UPLOAD_QUEUE.mkdir(parents=True, exist_ok=True)
        qv = UPLOAD_QUEUE / f"zodiac_{date_iso}.mp4"
        shutil.copy2(video, qv)
        meta = {
            "video_file": str(qv),
            "title": title[:100],
            "description": desc,
            "tags": ["띠별운세", "오늘의운세", "12띠", "사주", "운세", "shorts"],
            "category": "24",
            "privacy": YT_PRIVACY,
            "contains_synthetic_media": True,
        }
        (UPLOAD_QUEUE / f"zodiac_{date_iso}_meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        log(f"유튜브 큐 적재: {qv.name} (privacy={YT_PRIVACY}, AI고지=true, 성우={voice})")
    except OSError as e:
        alerts.append(f"유튜브 큐 적재 실패: {e}")
        return False

    if not do_upload:
        log("업로더 실행 생략(--no-upload)")
        return True
    r = _run([sys.executable, "04_auto_upload.py", "--channel", "unmyeong"],
             cwd=UPLOADER_DIR, timeout=900)
    ok = r.returncode == 0 and ("업로드" in r.stdout or "upload" in r.stdout.lower()
                                or r.stdout.strip() != "")
    if r.returncode != 0:
        alerts.append(f"유튜브 업로더 종료코드 {r.returncode}: {(r.stderr or r.stdout)[-300:]}")
        return False
    log(f"유튜브 업로더 완료: {r.stdout.strip().splitlines()[-1] if r.stdout.strip() else 'OK'}")
    return True


def main():
    args = sys.argv[1:]
    date_iso = None
    if "--date" in args:
        date_iso = args[args.index("--date") + 1]
    date_iso = date_iso or zs.today_iso()
    tomorrow = (dt.date.fromisoformat(date_iso) + dt.timedelta(days=1)).isoformat()
    do_upload = "--no-upload" not in args
    do_push = "--no-push" not in args

    log(f"=== 띠별운세 일일 파이프라인 시작: {date_iso} (버퍼 {tomorrow}) ===")
    alerts: list[str] = []

    # 1) 오늘 5장 보장 (평소엔 어제 만든 재고로 즉시 통과)
    r_today = zt.ensure_daily_images(date_iso)
    alerts += r_today["alerts"]
    # 2) 내일 5장 선행 생성 (실패해도 오늘 발행엔 지장 없음 — 경보만)
    try:
        r_tmr = zt.ensure_daily_images(tomorrow)
        if r_tmr["failed"]:
            alerts.append(f"D+1({tomorrow}) 선행 생성 미완: {', '.join(r_tmr['failed'])}")
    except SystemExit as e:
        alerts.append(f"D+1 생성 불가: {e}")
    # 3) G드라이브 미러
    zt.mirror_to_gdrive(date_iso)
    zt.mirror_to_gdrive(tomorrow)

    # 4) 쇼츠 조립 (오늘 5장이 있어야 함)
    video_ok = False
    if r_today["ok"]:
        try:
            import zodiac_shorts
            out = BASE / "reels" / f"{date_iso}_tts.mp4"
            if out.exists() and out.stat().st_size > 500_000:
                log("쇼츠 이미 존재 — 건너뜀")
            else:
                zodiac_shorts.make_shorts(date_iso)
            video_ok = True
            try:  # G드라이브에 영상도 미러
                gd = zt.GDRIVE_DIR / date_iso
                gd.mkdir(parents=True, exist_ok=True)
                shutil.copy2(out, gd / "06_영상.mp4")
            except OSError as e:
                log(f"[WARN] 영상 G미러 실패: {e}")
        except BaseException as e:
            alerts.append(f"쇼츠 조립 실패: {type(e).__name__}: {e}")
    else:
        alerts.append(f"오늘({date_iso}) 이미지 미완성 {r_today['failed']} — "
                      f"쇼츠·발행은 Actions 레거시 폴백에 맡김")

    # 5) repo 푸시 (Actions 05:35 발행이 Topview분을 쓰도록)
    if do_push:
        git_push([date_iso, tomorrow], alerts)

    # 6) 운명과학TV 쇼츠 업로드
    if video_ok:
        queue_youtube_shorts(date_iso, alerts, do_upload)

    # 7) 경보
    if alerts:
        body = f"날짜: {date_iso}\n" + "\n".join(f"- {a}" for a in alerts) + \
               f"\n\n로그: {zt.LOG_FILE}\n복구: 클로드 세션에서 MCP로 재생성 가능 " \
               f"(zodiac_topview.py status {date_iso} 로 빈 장 확인)"
        sent = zodiac_alert.alert(f"파이프라인 경보 {len(alerts)}건 ({date_iso})", body)
        log(f"경보 {len(alerts)}건 — 메일 {'발송됨' if sent else '발송실패'}: {alerts}")
    else:
        log("=== 전 단계 정상 완료 ===")
    return 0 if not alerts else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
