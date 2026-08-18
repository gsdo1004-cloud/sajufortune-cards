# -*- coding: utf-8 -*-
"""zodiac_month_task.py — 매월 15일 '다음 달' 월간 운세 자동 생성 (2026-07-25)

전달 15일에 돌려서 다음 달 콘텐츠(쇼츠 3종 + 카드뉴스 + 한장뉴스)를 미리 만들어 둔다.
완성본은 구글드라이브 보관 폴더로 복사되어 바로 찾을 수 있다.

⚠️ 업로드는 하지 않는다. 생성까지만이고, 검토 후 수동으로 올린다.
   (일일 12띠 파이프라인과 스케줄·업로드가 겹치면 중복 사고가 난다 — 그 선을 넘지 않는다.)

등록:  python zodiac_month_task.py --install
해제:  python zodiac_month_task.py --uninstall
수동:  python zodiac_month_task.py --run
"""
from __future__ import annotations

import argparse
import datetime as _dt
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
TASK_NAME = "Zodiac_MonthlyFortune"
LOG_DIR = BASE / "logs"


def next_month(today: _dt.date | None = None) -> tuple[int, int]:
    d = today or _dt.date.today()
    return (d.year + (d.month == 12), (d.month % 12) + 1)


def run_once() -> int:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    y, m = next_month()
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    logf = LOG_DIR / f"month_{y}-{m:02d}_{stamp}.log"
    print(f"[month-task] {y}년 {m}월 콘텐츠 생성 시작 → {logf}")
    if str(BASE) not in sys.path:
        sys.path.insert(0, str(BASE))
    try:
        import zodiac_month_shorts as zms
        # AI 카드 6장을 먼저 확보한다(멱등 — 이미 있으면 건너뛴다).
        # 이 호출이 빠져 있어 쇼츠가 Pillow 카드로만 나갔다. 실패해도 조립은 계속하며,
        # 카드가 없으면 zms.run 이 알아서 Pillow 카드로 되돌아간다.
        try:
            import zodiac_month_topview as zmt
            zmt.ensure_month_images(y, m)
        except Exception as e:
            print(f"[month-task] AI 카드 생성 건너뜀({e!r}) — Pillow 카드로 진행")
        # 생성만 수행한다. 기존 통합 세트와 새 개별 영상 모두 자동 업로드하지 않는다.
        r = zms.run(y, m, featured_limit=3)
        msg = [f"{y}-{m:02d} 생성 완료",
               f"로컬     : {r['root']}",
               f"구글드라이브: {r['gdrive'] or '(복사 실패 — 로컬 확인)'}",
               f"영상     : {', '.join(v.name for v in r['videos'])}"]
        msg.extend([
            "개별 영상: " + ", ".join(v.name for v in r["featured_videos"]),
            f"선정 근거: {r['featured_selection']}",
            "업로드: 수행하지 않음 (생성 후 수동 검토 전용)",
        ])
        logf.write_text("\n".join(msg), encoding="utf-8")
        print("\n".join(msg))
        return 0
    except Exception as e:
        logf.write_text(f"실패: {e!r}", encoding="utf-8")
        print(f"[month-task] 실패: {e!r}")
        return 1


def install() -> int:
    """매월 15일 07:00. pythonw로 창 없이 실행한다."""
    pyw = Path(sys.executable).with_name("pythonw.exe")
    exe = str(pyw if pyw.exists() else sys.executable)
    cmd = ["schtasks", "/Create", "/TN", TASK_NAME, "/SC", "MONTHLY", "/D", "15",
           "/ST", "07:00", "/F",
           "/TR", f'"{exe}" "{BASE / "zodiac_month_task.py"}" --run']
    # schtasks 출력은 CP949다. 기본 utf-8로 읽으면 등록에 성공해도 디코드 예외가 난다.
    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="cp949", errors="replace")
    print(r.stdout or r.stderr)
    if r.returncode == 0:
        print(f"[+] 등록 완료: 매월 15일 07:00 — 다음 달 운세 자동 생성 (업로드 없음)")
    return r.returncode


def uninstall() -> int:
    r = subprocess.run(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"],
                       capture_output=True, text=True, encoding="cp949", errors="replace")
    print(r.stdout or r.stderr)
    return r.returncode


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--install", action="store_true")
    ap.add_argument("--uninstall", action="store_true")
    ap.add_argument("--run", action="store_true")
    a = ap.parse_args()
    if a.install:
        sys.exit(install())
    if a.uninstall:
        sys.exit(uninstall())
    if a.run:
        sys.exit(run_once())
    y, m = next_month()
    print(f"다음 실행 시 생성될 대상: {y}년 {m}월")
    print("등록하려면 --install, 지금 만들려면 --run")
