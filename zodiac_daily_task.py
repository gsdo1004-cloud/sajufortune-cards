# -*- coding: utf-8 -*-
"""띠별운세 파이프라인 — Windows 작업 스케줄러 전용 런처 (무창 pythonw).

왜 런처가 따로 필요한가:
  1) pythonw.exe는 콘솔이 없어 `sys.stdout`이 None일 수 있다 → 파이프라인의 print /
     sys.stdout.reconfigure가 즉사한다. 여기서 stdout·stderr를 로그파일로 먼저 돌린다.
  2) 스케줄러는 실패를 조용히 삼킨다 → 최상위에서 예외를 잡아 메일로 알린다
     ([[feedback_korean_hostname_smtp_trap]] 처리된 zodiac_alert 사용).
  3) 로그 무한증식 방지 — 2MB 넘으면 .1로 회전.

⚠️ 패키지는 반드시 main site-packages에 (user-site/Roaming은 스케줄러가 못 봄)
   — [[feedback_scheduled_task_usersite_trap]]. 2026-07-17 확인: requests·PIL·keyring·
   edge_tts·mcp 전부 main site ✅
"""
import io
import os
import sys
import traceback
import datetime as dt
from pathlib import Path

BASE = Path(__file__).resolve().parent
LOG = BASE / "zodiac_task.log"
MAX_LOG = 2 * 1024 * 1024


def _open_log():
    try:
        if LOG.exists() and LOG.stat().st_size > MAX_LOG:
            LOG.replace(LOG.with_suffix(".log.1"))
    except OSError:
        pass
    return open(LOG, "a", encoding="utf-8", buffering=1)


def main() -> int:
    f = _open_log()
    # pythonw: stdout/stderr가 None → 로그파일로 교체 (print 즉사 방지)
    sys.stdout = f
    sys.stderr = f
    sys.stdin = io.StringIO()
    f.write(f"\n{'='*70}\n[{dt.datetime.now():%Y-%m-%d %H:%M:%S}] 스케줄 실행 시작 "
            f"(py={sys.executable})\n")
    os.chdir(BASE)
    sys.path.insert(0, str(BASE))
    try:
        import zodiac_daily_pipeline as p
        rc = p.main()
        f.write(f"[{dt.datetime.now():%H:%M:%S}] 종료코드 {rc}\n")
        return rc
    except BaseException:
        tb = traceback.format_exc()
        f.write(f"[{dt.datetime.now():%H:%M:%S}] 💥 최상위 예외:\n{tb}\n")
        try:
            import zodiac_alert
            zodiac_alert.alert(
                "스케줄 실행 자체가 실패",
                f"파이프라인이 시작조차 못했거나 도중 크래시했습니다.\n\n{tb}\n\n로그: {LOG}")
        except BaseException:
            pass
        return 2
    finally:
        f.close()


if __name__ == "__main__":
    sys.exit(main())
