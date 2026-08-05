# -*- coding: utf-8 -*-
"""띠 지목 카드 → G드라이브 스테이징.

한밝님 지시(2026-08-05): 생성된 카드뉴스는 G드라이브에 넣어두고, 인스타 등에는
직접 올린다. 자동 업로드는 하지 않는다 — 2026-07 메타 계정 제재 이력이 있어
"자동 생성 → 드라이브 스테이징 → 사람이 게시" 구조를 유지한다.

쓰레드 발행은 GitHub Actions 가 하고, 이 스크립트는 그 결과물을 손에 잡히는 곳으로
옮겨놓기만 한다. 러너는 G드라이브에 접근할 수 없으므로 로컬 PC 에서 돌려야 한다.

실행:
  python signal_to_gdrive.py             # 오늘 + 앞으로 3일치 있는 대로
  python signal_to_gdrive.py 2026-08-06  # 특정 날짜
  python signal_to_gdrive.py --pull      # git pull 먼저(러너가 만든 카드 받아오기)
"""
from __future__ import annotations
import sys
import shutil
import subprocess
import datetime as dt
from pathlib import Path

BASE = Path(__file__).resolve().parent
GDRIVE = Path(r"G:\내 드라이브\01클로드\작업폴더\띠지목_카드뉴스")

# 인스타에 올릴 때 순서가 헷갈리지 않게 한글 이름을 붙인다.
NAMES = ["1_표지", "2_성향", "3_속마음", "4_전환", "5_안내"]


def caption_for(date_iso: str) -> tuple[str, str]:
    """발행 본문과 띠 이름. 카드와 같은 로직으로 뽑아 캡션 복붙에 쓴다."""
    sys.path.insert(0, str(BASE))
    import zodiac_signal as zsig
    import zodiac_seo as zs
    slug = zsig.sign_of(date_iso)
    ko = zs.SLUG_TO_INFO[slug][1]
    if not ko.endswith("띠"):
        ko += "띠"
    return zsig.build_text(date_iso), ko


def mirror(date_iso: str) -> bool:
    src = BASE / "cards" / date_iso
    cards = sorted(src.glob("signal_*.jpg"))
    if not cards:
        return False
    try:
        text, ko = caption_for(date_iso)
    except Exception as e:
        print(f"  [WARN] 캡션 생성 실패({e}) — 이미지만 복사")
        text, ko = "", ""

    dst = GDRIVE / f"{date_iso}_{ko}" if ko else GDRIVE / date_iso
    dst.mkdir(parents=True, exist_ok=True)
    n = 0
    for i, p in enumerate(cards):
        name = NAMES[i] if i < len(NAMES) else f"{i+1}"
        shutil.copy2(p, dst / f"{name}.jpg")
        n += 1
    if text:
        (dst / "캡션.txt").write_text(text, encoding="utf-8")
    print(f"  [OK] {dst.name}  이미지 {n}장 + 캡션")
    return True


def main():
    argv = sys.argv[1:]
    if "--pull" in argv:
        print("git pull …")
        subprocess.run(["git", "pull", "--rebase", "--autostash"], cwd=BASE)
        argv = [a for a in argv if a != "--pull"]

    dates = [a for a in argv if not a.startswith("--")]
    if not dates:
        # 러너가 D+0 을 만들고, 로컬에서 미리 만들어 둔 날짜가 있을 수 있어 앞뒤로 훑는다.
        today = dt.date.today()
        dates = [(today + dt.timedelta(days=d)).isoformat() for d in range(-1, 4)]

    done = 0
    for d in dates:
        if mirror(d):
            done += 1
    print(f"\n스테이징 {done}일치 → {GDRIVE}")
    if done == 0:
        print("복사할 카드가 없습니다. --pull 로 러너 생성분을 먼저 받아보세요.")


if __name__ == "__main__":
    main()
