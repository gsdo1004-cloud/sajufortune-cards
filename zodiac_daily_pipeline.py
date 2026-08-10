# -*- coding: utf-8 -*-
"""띠별운세 일일 파이프라인 오케스트레이터 (집 PC, **전날 19:00** 스케줄).

⏰ 생성과 발행을 분리한다 (2026-07-17 한밝님 지시):
  - 19:00 (D-1) 생성 → 20:00~23:00 전날 저녁 발행 창을 확보한다.
  - 유튜브는 D-1 21:00에 예약공개하고, 예약 완료 후에만 Threads 발행 경로를 연다.
  - 틱톡은 수동이라 한밝님이 저녁에 G드라이브에서 받아 예약 발행한다.

흐름 (전 단계 멱등 — 재실행이 빈 곳만 메움). 기준일 = **내일(D)**:
  1. D 기본 4장 보장 ← 평소엔 어제 버퍼분이 있어 즉시 통과 (발행 무실패의 핵심)
  2. D+1 기본 4장 선행 ← 내일 19:00 실행이 죽어도 모레 발행은 무사
  3. G드라이브 미러 (틱톡 수동 업로드·blog-auto 소스)
  4. D 쇼츠 조립 (타입캐스트 성우 로테이션 + BGM 로테이션)
  5. 운명과학TV 쇼츠 업로드 — **비공개 + publishAt=D-1 21:00 예약공개**
  6. 유튜브 예약 성공 표식과 함께 repo 커밋·푸시 → GitHub Actions가 Threads 발행
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
# [[feedback_youtube_private_default]]의 "항상 비공개" 규칙을 지키면서 전날 저녁 발행을 얻는 방식:
# 19:00에 비공개로 올라가고 21:00에 유튜브가 자동 공개한다. 그 사이 약 2시간 동안 한밝님이
# 확인·취소 가능. ⚠️ privacy를 public으로 직접 바꾸지 말 것 — 예약공개가 정본 경로.
YT_PRIVACY = "private"
YT_PUBLISH_HOUR = "21:00:00+09:00"   # 기준일 전날 21시


def youtube_publish_at(date_iso: str) -> str:
    """기준일(D) 운세를 전날(D-1) 저녁 21시에 공개한다."""
    day = dt.date.fromisoformat(date_iso) - dt.timedelta(days=1)
    return f"{day.isoformat()}T{YT_PUBLISH_HOUR}"


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
    """cards/{dates}, reels 커밋·푸시. Actions와의 경합은 pull --rebase로 해소.

    2026-07-30 수리 — 7/28·7/29 이틀 연속 발행이 죽은 실제 원인:
    인덱스에 미해결 병합(cards/ai_news/2026-07-27_0.png, 3-way)이 남아 있어
    git pull 과 git commit 이 "unmerged files" 로 계속 거부됐다. 그런데 옛 코드는
      ① pull 의 종료코드를 안 봤고,
      ② commit 실패도 "nothing to commit" 이 아니면 그냥 통과시켜 push 로 넘어갔다.
    그래서 로그에는 non-fast-forward push 실패만 남아 원인이 가려졌고, 원격에
    카드·릴스가 없는 상태로 Actions 가 "[FAIL] 카드 없음" 을 내며 죽었다.
    → 이제 각 단계의 실패를 로그·경보로 드러내고, 커밋이 안 됐으면 push 하지 않는다.
    미해결 병합은 자동 해결하지 않는다(어느 쪽이 정본인지는 사람이 판단할 일).
    """
    def _unmerged() -> list[str]:
        u = _run(["git", "diff", "--name-only", "--diff-filter=U"], cwd=BASE)
        return [ln for ln in u.stdout.splitlines() if ln.strip()]

    def _pull(tag: str) -> bool:
        p = _run(["git", "pull", "--rebase", "--autostash", "origin", "main"], cwd=BASE)
        if p.returncode != 0:
            log(f"git pull 실패({tag}): {(p.stderr or p.stdout)[-300:]}")
            return False
        return True

    try:
        # 0) 미해결 병합이 남아 있으면 여기서 끊는다 — 그대로 두면 pull·commit 이
        #    전부 거부되고 push 만 non-FF 로 실패해 원인이 안 보인다.
        stuck = _unmerged()
        if stuck:
            msg = ("git 인덱스에 미해결 병합 잔존 → 커밋·푸시 불가. "
                   "수동 해결 필요: " + ", ".join(stuck[:5]))
            log(msg)
            alerts.append(msg)
            return False

        if not _pull("사전"):
            alerts.append("git pull 실패 — 원격 반영 없이 진행하면 발행이 깨진다")
            return False

        _run(["git", "add", "-A", "--"] +
             [f"cards/{d}" for d in dates] + ["reels"], cwd=BASE)
        r = _run(["git", "commit", "-m",
                  f"topview cards+shorts {dates[0]} (+D+1 buffer)"], cwd=BASE)
        if r.returncode != 0:
            out = r.stdout + r.stderr
            # "변경 없음" 판정은 문자열로 하지 않는다 — git 은 미추적 파일이 있으면
            # "nothing to commit" 대신 "no changes added to commit" 을 쓰고, 로케일에
            # 따라 문구가 또 달라진다(옛 코드가 여기서 새는 것을 이번에 확인).
            # 스테이지가 비어 있으면 올릴 게 없는 정상 상황이다.
            staged = _run(["git", "diff", "--cached", "--name-only"], cwd=BASE)
            if not staged.stdout.strip():
                log("커밋할 변경 없음")
                return True
            # 커밋이 안 된 상태로 push 해도 non-FF 로만 실패한다 → 여기서 끊는다.
            msg = f"git commit 실패 → 푸시 중단: {out[-300:]}"
            log(msg)
            alerts.append(msg)
            return False

        for attempt in (1, 2, 3):
            p = _run(["git", "push", "origin", "main"], cwd=BASE)
            if p.returncode == 0:
                log("repo 푸시 완료")
                return True
            log(f"push 실패(시도{attempt}): {(p.stderr or p.stdout)[-300:]}")
            if attempt < 3 and not _pull(f"재시도{attempt}"):
                break
        alerts.append("git push 실패 — 원격에 오늘치 카드·릴스가 없어 "
                      "쓰레드 발행(21시 Actions)이 '카드 없음'으로 죽는다")
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
             "privacy": YT_PRIVACY, "publish_at": youtube_publish_at(date_iso),
             "uploaded_at": dt.datetime.now().isoformat(timespec="seconds")},
            ensure_ascii=False), encoding="utf-8")
    except OSError as e:
        log(f"[WARN] 업로드 표식 기록 실패(다음 실행에 중복 위험): {e}")
    return vid


def backfill_gdrive(days: int = 4) -> int:
    """최근 며칠 중 G드라이브에 빠진 영상·카드를 메운다.

    틱톡·릴스는 휴대폰에서 올리므로 G드라이브에 없으면 업로드 자체가 불가능하다.
    실제로 2026-07-27치 95초판이 빠져 있었다(D+1→D+2 오프셋 전환기에 그날치가
    정규 실행 밖에서 조립돼 미러 단계를 안 거쳤다). 사람이 눈치채기 전엔 모르는
    종류의 누락이라 매 실행마다 훑어서 자동으로 채운다.
    """
    today = dt.date.fromisoformat(zs.today_iso())
    n = 0
    for i in range(days):
        di = (today + dt.timedelta(days=i - 1)).isoformat()
        gd = zt.GDRIVE_DIR / di
        # 2026-08-03: 20초판(10s) 폐기로 미러 대상에서 뺐다. 되살리면 여기도 되살릴 것.
        pairs = [(BASE / "reels" / f"{di}_tts.mp4", "07_영상.mp4"),
                 (BASE / "cards" / di / "card_05.png", "08_지목3띠.png"),
                 (BASE / "cards" / di / "card_08.png", "09_표형12띠.png")]
        for src, name in pairs:
            if not src.exists():
                continue
            try:
                if not (gd / name).exists():
                    gd.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, gd / name)
                    log(f"G미러 보충: {di}/{name}")
                    n += 1
            except OSError as e:
                log(f"[WARN] G미러 보충 실패({di}/{name}): {e}")
    return n


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
    voice, fmt, theme_title = "", "", ""
    try:
        m = json.loads(meta_src.read_text(encoding="utf-8"))
        voice = m.get("voice", {}).get("voice", "")
        fmt = m.get("format", "")      # 20초판 포맷(pick3/table12/없으면 기존 ai12)
        theme_title = m.get("theme_title", "")   # 지목형 주제(오늘/이번주/이달 × 축)
    except Exception:
        pass

    d = dt.date.fromisoformat(date_iso)
    wd = ["월", "화", "수", "목", "금", "토", "일"][d.weekday()]
    # 2026-07-26: 제목도 포맷을 따라간다. 지목형인데 "12띠 총정리"라고 달면
    # 제목과 내용이 어긋나 이탈을 부른다. 지목형 제목은 **띠 이름을 밝히지 않는다** —
    # "내가 해당되나?"를 남겨야 끝까지 본다(벤치마크 실측의 핵심).
    # ⚠️ 과장 화법 금지(수익정지 이력) — `운 폭발`류 대신 `흐름이 좋은` 수준으로.
    if fmt == "pick3":
        subj = theme_title or "오늘 흐름이 좋은 띠"
        title = f"{subj} 세 개 🍀 {d.month}월 {d.day}일 {wd}요일 #shorts"
        lead = (f"{d.year}년 {d.month}월 {d.day}일 {wd}요일, {subj} 세 개를 짚어 "
                f"드립니다.\n혹시 내 띠, 우리 가족 띠가 들어 있는지 확인해 보세요.")
    else:
        title = f"{d.month}월 {d.day}일 {wd}요일 오늘의 띠별운세 🔮 12띠 총정리 #shorts"
        lead = (f"{d.year}년 {d.month}월 {d.day}일 {wd}요일, 12띠 오늘의 운세를 정리했습니다.\n"
                f"내 띠의 오늘 흐름, 금전운·연애운·건강운까지 확인해 보세요.")
    desc = (f"{lead}\n\n"
            f"매일 아침 새로운 띠별운세가 올라옵니다. 구독하시면 놓치지 않아요.\n\n"
            f"#띠별운세 #오늘의운세 #12띠 #사주 #운세 #shorts\n\n"
            f"※ 본 콘텐츠는 전통 명리의 일진 풀이를 바탕으로 한 재미와 참고용입니다. "
            f"중요한 결정은 신중히 판단해 주세요.")
    try:
        UPLOAD_QUEUE.mkdir(parents=True, exist_ok=True)
        qv = UPLOAD_QUEUE / f"zodiac_{date_iso}_{variant}.mp4"
        shutil.copy2(video, qv)
        publish_at = youtube_publish_at(date_iso)
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
    log(f"유튜브 업로드 완료: {vid or '(ID확인실패)'} — 변종{variant}, 전날 저녁 예약공개")
    return True


def main():
    args = sys.argv[1:]

    date_iso = None
    if "--date" in args:
        date_iso = args[args.index("--date") + 1]
    elif "--today" in args:
        date_iso = zs.today_iso()
    else:
        # 19:00(D-1) 실행 → 전날 21:00 예약공개가 정본이다. D+1 카드도 함께
        # 만들어 하루치 재고를 유지하므로, 다음 날 실행 실패에도 발행 공백을 줄인다.
        try:
            offset = int(os.environ.get("ZODIAC_PIPELINE_OFFSET_DAYS", "1"))
        except ValueError:
            offset = 1
        date_iso = (dt.date.fromisoformat(zs.today_iso())
                    + dt.timedelta(days=offset)).isoformat()
    tomorrow = (dt.date.fromisoformat(date_iso) + dt.timedelta(days=1)).isoformat()
    do_upload = "--no-upload" not in args
    do_push = "--no-push" not in args

    log(f"=== 띠별운세 파이프라인 시작: 기준일 {date_iso} "
        f"(오늘={zs.today_iso()}, 버퍼={tomorrow}) ===")
    alerts: list[str] = []

    # 1) 오늘 기본 4장 보장 (평소엔 어제 만든 재고로 즉시 통과)
    r_today = zt.ensure_daily_images(date_iso)
    alerts += r_today["alerts"]
    # 2) 내일 기본 4장 선행 생성 (실패해도 오늘 발행엔 지장 없음 — 경보만)
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
    # 2026-08-03: 20초판(변종A) 폐기 — 한밝님 지시. 유튜브도 95초판 고정.
    #   95초판 → 스레드·틱톡·네이버클립·유튜브 전부
    # 20초판은 pick3/table12/ai12 3종을 격일로 돌리며 A/B를 보던 것인데, 짧아서
    # 담기는 정보가 적고 띠 하나하나를 스치듯 지나가 유입으로 이어지지 않았다.
    # 그 자리는 십성·사주구성 에버그린 쇼츠가 대신한다(별도 라인).
    # 되살리려면 variant 를 다시 격일로 돌리고 아래 make_shorts_10s 블록을 되살리면 된다.
    variant = "B"
    if r_today["ok"]:
        try:
            import zodiac_shorts
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
            # 2026-08-03: 20초판 생성 중단. make_shorts_10s 함수는 zodiac_shorts 에 그대로
            # 남겨 둔다 — 되살릴 때 여기서 다시 부르기만 하면 된다.
            log("영상 1종 준비: 95초판(스레드·틱톡·유튜브 공용)")
            # G드라이브 미러 — 틱톡·릴스·네이버클립은 **휴대폰에서 업로드**하므로
            # G드라이브에 없는 파일은 올릴 수가 없다. 그래서 두 판본을 다 올린다.
            # 3단계 미러는 이 시점보다 앞서 돌아 표형카드가 아직 없다
            # (표형 카드는 조립 중에 로컬 렌더된다) → 여기서 따로 붙인다.
            try:
                gd = zt.GDRIVE_DIR / date_iso
                gd.mkdir(parents=True, exist_ok=True)
                shutil.copy2(out, gd / "07_영상.mp4")            # 95초판
                # 2026-08-03: 20초판(10s) 폐기로 미러 대상에서 뺐다.
                extra = [(BASE / "cards" / date_iso / "card_08.png", "09_표형12띠.png")]
                for src, name in extra:
                    if src.exists():
                        shutil.copy2(src, gd / name)
                        log(f"G미러 추가: {name}")
            except OSError as e:
                log(f"[WARN] 영상 G미러 실패: {e}")
        except BaseException as e:
            alerts.append(f"쇼츠 조립 실패: {type(e).__name__}: {e}")
    else:
        alerts.append(f"오늘({date_iso}) 이미지 미완성 {r_today['failed']} — "
                      f"쇼츠·발행은 Actions 레거시 폴백에 맡김")

    # 4-b) G드라이브 누락분 보충 (틱톡·릴스 = 휴대폰 업로드라 여기 없으면 못 올린다)
    backfill_gdrive()

    # 4-c) 오래된 산출물은 E드라이브로 (C 87% 사용 중). 최근 45일은 건드리지 않는다 —
    #      카드뉴스·릴스 발행이 raw.githubusercontent.com 으로 읽어가기 때문이다.
    try:
        r = _run([sys.executable, "archive_old.py"], cwd=BASE, timeout=300)
        for line in (r.stdout or "").splitlines():
            if "완료:" in line or "[WARN]" in line:
                log(line.strip())
    except Exception as e:
        log(f"[WARN] 아카이브 실패(무시하고 계속): {e}")

    # 5) 운명과학TV 쇼츠를 먼저 비공개 예약 업로드한다.
    #    uploaded.json은 이 성공 뒤에만 쓰이며, 다음 repo push/Threads 발행의 선행조건이다.
    youtube_ready = False
    if video_ok:
        youtube_ready = queue_youtube_shorts(date_iso, alerts, do_upload, variant)
    else:
        alerts.append("쇼츠가 없어 유튜브 예약·Threads 발행을 모두 보류")

    # 6) 유튜브 예약 성공 뒤에만 카드·영상·uploaded.json을 푸시한다.
    #    GitHub Actions의 Threads 단계도 이 표식이 있어야 실행된다.
    if do_push:
        if youtube_ready and _upload_marker(date_iso).exists():
            git_push([date_iso, tomorrow], alerts)
        else:
            alerts.append("유튜브 예약 미완료 — Threads 선행 방지를 위해 repo 푸시 보류")

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
