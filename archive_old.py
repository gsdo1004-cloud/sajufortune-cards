# -*- coding: utf-8 -*-
"""오래된 산출물을 E드라이브로 옮긴다 (2026-07-27 신설).

왜
--
C 드라이브가 87% 찼다(여유 124GB). 이 레포는 카드 PNG 8장 + 영상 2편을 **매일** 쌓는다.
게다가 그것들이 git 에 커밋되므로 레포도 같이 부푼다.

무엇을 남기고 무엇을 옮기나
---------------------------
카드뉴스·릴스 발행은 이 파일들을 `raw.githubusercontent.com` URL 로 읽어간다
(스레드·인스타 API 가 공개 URL 을 요구하기 때문). 그래서 **최근 것은 절대 못 옮긴다.**
발행은 당일~며칠 안에 끝나므로 기본 45일이면 안전 마진이 충분하다.

⚠️ 이미 게시된 글의 이미지는 플랫폼이 게시 시점에 자기 서버로 복사하는 것이 일반적이라
   원본을 지워도 남는다 — 다만 이건 **공식 문서로 확인하지 않았다**. 그래서 기간을
   넉넉히 잡았다. 더 보수적으로 가려면 --days 를 올려라.

실행:
  python archive_old.py --dry-run     # 뭐가 옮겨질지만 출력
  python archive_old.py               # 45일 지난 것 이동
  python archive_old.py --days 90
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import shutil
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
ARCHIVE = Path(r"E:\cardnews_archive")     # E = 5.5TB 여유(2026-07-27 실측)
KEEP_DAYS = 45
DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def log(m: str):
    print(f"[archive] {m}", flush=True)


def _old_date(name: str, cutoff: dt.date) -> bool:
    m = DATE_RE.search(name)
    if not m:
        return False
    try:
        return dt.date.fromisoformat(m.group(1)) < cutoff
    except ValueError:
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=KEEP_DAYS)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    cutoff = dt.date.today() - dt.timedelta(days=a.days)
    log(f"기준일 {cutoff} 이전 산출물을 {ARCHIVE} 로 옮깁니다")

    targets: list[Path] = []
    cards = BASE / "cards"
    if cards.is_dir():
        targets += [d for d in cards.iterdir()
                    if d.is_dir() and _old_date(d.name, cutoff)]
    reels = BASE / "reels"
    if reels.is_dir():
        targets += [f for f in reels.glob("*.mp4") if _old_date(f.name, cutoff)]

    if not targets:
        log("옮길 것이 없습니다")
        return

    moved, freed = 0, 0
    for src in targets:
        size = sum(f.stat().st_size for f in src.rglob("*") if f.is_file()) \
            if src.is_dir() else src.stat().st_size
        rel = src.relative_to(BASE)
        dst = ARCHIVE / rel
        log(f"  {rel}  ({size/1024/1024:.1f}MB)")
        if a.dry_run:
            continue
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.exists():
                shutil.rmtree(dst) if dst.is_dir() else dst.unlink()
            shutil.move(str(src), str(dst))
            # git 추적에서도 빼야 레포가 줄어든다. 다음 커밋에 반영된다.
            subprocess.run(["git", "rm", "-r", "--cached", "--quiet",
                            str(rel).replace("\\", "/")],
                           cwd=BASE, capture_output=True)
            moved += 1
            freed += size
        except OSError as e:
            log(f"  [WARN] 이동 실패({rel}): {e}")

    if a.dry_run:
        log(f"[DRY-RUN] {len(targets)}건 대상 — 옮기지 않았습니다")
    else:
        log(f"완료: {moved}건, {freed/1024/1024:.1f}MB 확보")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
