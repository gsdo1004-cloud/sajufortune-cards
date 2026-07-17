# -*- coding: utf-8 -*-
"""띠별운세 일일 파이프라인 오케스트레이터 (집 PC, **전날 18:00** 스케줄).

⏰ 생성과 발행을 분리한다 (2026-07-17 한밝님 지시):
  - 18:00 (D-1) 생성 → 자정까지 **6시간 재시도 여유**. 새벽에 만들어 바로 쏘면 실패 시 복구 불가.
  - 00:00 (D) 발행 → "D일 오늘의 운세"가 D일 0시에 나가 **날짜가 정확히 일치**하고,
    밤에 잠 못 드는 시청자부터 다음날 밤까지 **하루 전체를 커버**한다(05:35은 새벽을 통째로 놓침).
  - 틱톡은 수동이라 한밝님이 저녁에 G드라이브에서 받아 **틱톡 예약(00:00)**으로 거신다.

흐름 (전 단계 멱등 — 재실행이 빈 곳만 메움). 기준일 = **내일(D)**:
  1. D 5장 보장     ← 평소엔 어제 버퍼분이 있어 즉시 통과 (발행 무실패의 핵심)
  2. D+1 5장 선행   ← 내일 18:00 실행이 죽어도 모레 발행은 무사
  3. G드라이브 미러 (틱톡 수동 업로드·blog-auto 소스)
  4. D 쇼츠 조립 (타입캐스트 성우 로테이션 + BGM 로테이션)
  5. repo 커밋·푸시 → 00:02 GitHub Actions가 쓰레드 발행 (Topview분 우선)
  6. 운명과학TV 쇼츠 업로드 — **비공개 + publishAt=D 00:00 예약공개**
  7. 실패 시 이메일 경보 (zodiac_alert)

실행: python zodiac_daily_pipeline.py [--date YYYY-MM-DD] [--today] [--no-upload] [--no-push]
      --date  기준일 명시 (기본 = 내일)
      --today 기준일을 오늘로 (수동 복구용)
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
# pythonw로 돌 때 sys.executable=pythonw.exe → 자식도 무창(콘솔 안 뜸). 절대경로 고정.
UPLOADER_PY = sys.executable
# 🔒 업로드는 항상 private + publishAt 예약공개 (한밝님 2026-07-17 확인).
# [[feedback_youtube_private_default]]의 "항상 비공개" 규칙을 지키면서 00:00 정각 발행을 얻는 방식:
# 18:00에 비공개로 올라가고 자정에 유튜브가 자동 공개한다. 그 사이 1~6시간 동안 한밝님이
# 확인·취소 가능. ⚠️ privacy를 public으로 직접 바꾸지 말 것 — 예약공개가 정본 경로.
YT_PRIVACY = "private"
YT_PUBLISH_HOUR = "00:00:00+09:00"   # 기준일 자정 정각


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


def _is_our_shorts(date_iso: str) -> bool:
    """이 날짜 mp4가 '우리가 만든 Topview 쇼츠'인지 판정.

    zodiac_shorts.make_shorts가 완주해야만 shorts_meta.json을 남긴다. 이 표식이
    영상보다 오래됐거나 없으면 그 mp4는 레거시 릴스(Actions 산출물)다.
    """
    video = BASE / "reels" / f"{date_iso}_tts.mp4"
    meta = BASE / "cards" / date_iso / "shorts_meta.json"
    if not (video.exists() and meta.exists()):
        return False
    try:
        m = json.loads(meta.read_text(encoding="utf-8"))
        if m.get("date") != date_iso or not m.get("voice"):
            return False
        # 표식이 영상보다 먼저 만들어졌으면(=영상이 나중에 딴 걸로 덮임) 신뢰 불가
        return meta.stat().st_mtime >= video.stat().st_mtime - 5
    except (json.JSONDecodeError, OSError):
        return False


def _upload_marker(date_iso: str) -> Path:
    return BASE / "cards" / date_iso / "uploaded.json"


def _record_upload(date_iso: str, variant: str = "B") -> str:
    """업로더 로그에서 방금 올린 영상ID를 찾아 표식으로 남긴다. 반환=video_id.

    variant도 함께 기록 → 2주 뒤 A/B 집계 때 어느 날이 어느 변종이었는지 근거가 된다.
    """
    vid = ""
    try:
        logs = sorted((UPLOADER_DIR / "logs").glob("upload_unmyeong_*.json"),
                      key=lambda p: p.stat().st_mtime)
        if logs:
            for e in json.loads(logs[-1].read_text(encoding="utf-8")):
                if e.get("status") == "success":
                    vid = e.get("video_id", "")
    except Exception as e:
        log(f"[WARN] 업로드 로그 파싱 실패(표식은 남김): {e}")
    try:
        _upload_marker(date_iso).write_text(json.dumps(
            {"date": date_iso, "video_id": vid, "variant": variant,
             "privacy": YT_PRIVACY, "publish_at": f"{date_iso}T{YT_PUBLISH_HOUR}",
             "uploaded_at": dt.datetime.now().isoformat(timespec="seconds")},
            ensure_ascii=False), encoding="utf-8")
    except OSError as e:
        log(f"[WARN] 업로드 표식 기록 실패(다음 실행에 중복 위험): {e}")
    return vid


def queue_youtube_shorts(date_iso: str, alerts: list[str],
                         do_upload: bool = True, variant: str = "B") -> bool:
    """쇼츠를 운명과학TV 업로드 큐에 적재 후 멀티업로더 실행.

    variant: A=10초 압축판(reels/{date}_10s.mp4) / B=95초판(reels/{date}_tts.mp4).
    2주 A/B(2026-07-19~08-01) — 유튜브만 변종을 바꾸고 쓰레드·틱톡은 95초 고정이라
    실험이 오염되지 않는다.
    """
    # 🚨 2026-07-17: 멱등성 없어서 재실행하면 같은 날짜가 중복 업로드됨(실측 확인).
    # 업로더 자체엔 중복방지가 없다 → 여기서 표식으로 막는다.
    mk = _upload_marker(date_iso)
    if mk.exists():
        try:
            vid = json.loads(mk.read_text(encoding="utf-8")).get("video_id", "?")
        except Exception:
            vid = "?"
        log(f"이미 업로드됨({date_iso} → {vid}) — 건너뜀")
        return True
    if variant == "A":
        video = BASE / "reels" / f"{date_iso}_10s.mp4"
        ok_mark = (BASE / "cards" / date_iso / "shorts10_meta.json").exists()
    else:
        video = BASE / "reels" / f"{date_iso}_tts.mp4"
        ok_mark = _is_our_shorts(date_iso)
    if not video.exists():
        alerts.append(f"쇼츠 영상 없음({video.name}, 변종{variant}) — 유튜브 업로드 생략")
        return False
    # 🚨 2026-07-17 오업로드 사고 방지: 우리 쇼츠가 아니면 절대 올리지 않는다.
    if not ok_mark:
        alerts.append(f"{date_iso} mp4가 우리 쇼츠가 아님(레거시 릴스 추정) — "
                      f"유튜브 업로드 거부")
        return False
    meta_src = (BASE / "cards" / date_iso /
                ("shorts10_meta.json" if variant == "A" else "shorts_meta.json"))
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
        qv = UPLOAD_QUEUE / f"zodiac_{date_iso}_{variant}.mp4"
        shutil.copy2(video, qv)
        publish_at = f"{date_iso}T{YT_PUBLISH_HOUR}"
        meta = {
            "video_file": str(qv),
            "title": title[:100],
            "description": desc,
            "tags": ["띠별운세", "오늘의운세", "12띠", "사주", "운세", "shorts"],
            "category": "24",
            "privacy": YT_PRIVACY,
            "publish_at": publish_at,     # 업로더: privacy=private일 때만 publishAt 적용
            "contains_synthetic_media": True,
        }
        (UPLOAD_QUEUE / f"zodiac_{date_iso}_{variant}_meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        log(f"유튜브 큐 적재: {qv.name} (변종{variant}, 예약공개 {publish_at}, "
            f"AI고지=true, 성우={voice})")
    except OSError as e:
        alerts.append(f"유튜브 큐 적재 실패: {e}")
        return False

    if not do_upload:
        log("업로더 실행 생략(--no-upload)")
        return True
    r = _run([UPLOADER_PY, "04_auto_upload.py", "--channel", "unmyeong"],
             cwd=UPLOADER_DIR, timeout=900)
    ok = r.returncode == 0 and ("업로드" in r.stdout or "upload" in r.stdout.lower()
                                or r.stdout.strip() != "")
    if r.returncode != 0:
        alerts.append(f"유튜브 업로더 종료코드 {r.returncode}: {(r.stderr or r.stdout)[-300:]}")
        return False
    vid = _record_upload(date_iso, variant)
    log(f"유튜브 업로드 완료: {vid or '(ID확인실패)'} — 변종{variant}, 자정 예약공개")
    return True


def main():
    args = sys.argv[1:]
    date_iso = None
    if "--date" in args:
        date_iso = args[args.index("--date") + 1]
    elif "--today" in args:
        date_iso = zs.today_iso()
    else:
        # 기본 = 내일. 이 파이프라인은 **전날 18:00**에 돌아 다음날치를 만든다.
        date_iso = (dt.date.fromisoformat(zs.today_iso())
                    + dt.timedelta(days=1)).isoformat()
    tomorrow = (dt.date.fromisoformat(date_iso) + dt.timedelta(days=1)).isoformat()
    do_upload = "--no-upload" not in args
    do_push = "--no-push" not in args

    log(f"=== 띠별운세 파이프라인 시작: 기준일 {date_iso} "
        f"(오늘={zs.today_iso()}, 버퍼={tomorrow}) ===")
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

    # 4) 쇼츠 조립 (이미지가 다 있어야 함)
    #    95초판은 항상 만든다 = 쓰레드·틱톡·네이버클립 공용(90초 이내 게이트 적용).
    #    A일이면 10초 압축판도 추가로 만들어 **유튜브에만** 올린다 → A/B가 오염되지 않음.
    video_ok = False
    variant = "B"
    if r_today["ok"]:
        try:
            import zodiac_shorts
            variant = zodiac_shorts.ab_variant(date_iso)
            out = BASE / "reels" / f"{date_iso}_tts.mp4"
            # ⚠️ 2026-07-17 버그: 파일 존재+크기만 보면 **레거시 릴스**(Actions가 05:35에
            # HTML카드+EdgeTTS로 만들어 커밋한 같은 이름 파일)를 우리 쇼츠로 오인해
            # 그대로 유튜브에 올린다(실제 오업로드 1건 발생). 판정은 반드시 우리가 남긴
            # 표식(shorts_meta.json)으로. 없으면 그 mp4는 남의 것 → 새로 만든다.
            if out.exists() and _is_our_shorts(date_iso):
                log("쇼츠 이미 존재(우리 것 확인) — 건너뜀")
            else:
                if out.exists():
                    log("기존 mp4는 레거시 릴스 — 덮어쓰고 Topview 쇼츠로 재조립")
                zodiac_shorts.make_shorts(date_iso)
            video_ok = True
            if variant == "A":   # A/B: 10초 압축판 (유튜브 전용)
                s10 = BASE / "reels" / f"{date_iso}_10s.mp4"
                if s10.exists() and (BASE / "cards" / date_iso / "shorts10_meta.json").exists():
                    log("10초판 이미 존재 — 건너뜀")
                else:
                    zodiac_shorts.make_shorts_10s(date_iso)
            log(f"A/B 변종: {variant} ({'10초 압축판' if variant == 'A' else '95초판'}) → 유튜브")
            try:  # G드라이브에 영상도 미러 (틱톡·네이버클립 수동 업로드용 = 95초판)
                gd = zt.GDRIVE_DIR / date_iso
                gd.mkdir(parents=True, exist_ok=True)
                shutil.copy2(out, gd / "07_영상.mp4")
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

    # 6) 운명과학TV 쇼츠 업로드 (A/B 변종 반영, 자정 예약공개)
    if video_ok:
        queue_youtube_shorts(date_iso, alerts, do_upload, variant)

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
