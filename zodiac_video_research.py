# -*- coding: utf-8 -*-
"""zodiac_video_research.py — 격주 영상 기술 리서치·개선 제안 루프 (2026-07-25)

한밝님 결정(2026-07-25): 2주에 한 번, **리서치와 제안서까지만 자동**. 적용은 승인 후.

왜 자동 적용을 하지 않는가
  매주 도는 스크립트가 파이프라인 코드를 스스로 고치면, 어느 날 조용히 망가진 채로
  매일 영상이 나간다. 되돌릴 지점도 찾기 어렵다. 그래서 이 스크립트는
  '현재 상태를 기록하고 리서치 요청을 큐에 넣는 것'까지만 한다.

동작
  1) 현재 영상 스펙을 스냅샷으로 저장 (해상도·구성·길이·CTA·자막·PNGTuber 설정)
  2) 직전 스냅샷과 비교해 무엇이 바뀌었는지 기록
  3) 리서치 요청을 to_claude 큐에 넣는다 → 세션에서 클로드가 웹 리서치 후 제안서 작성

  스케줄러 안에서는 웹검색을 할 수 없다(그건 세션 도구다). 그래서 '요청을 남기는 것'과
  '리서치·제안서 작성'을 분리했다.

등록: python zodiac_video_research.py --install     (격주 월요일 08:00)
수동: python zodiac_video_research.py --run
확인: python zodiac_video_research.py --status
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
SNAP_DIR = BASE / "logs" / "video_research"
QUEUE_DIRS = [Path(r"D:\antigravity_work\hub\queue\to_claude"),
              BASE / "logs" / "video_research" / "queue"]
TASK_NAME = "Zodiac_VideoResearch_Biweekly"

RESEARCH_TOPICS = [
    "유튜브 쇼츠 알고리즘·노출 정책 변경점 (최근 2주)",
    "쇼츠 완주율을 올린 실제 연출 기법 — 훅 길이, 컷 전환, 자막 타이밍",
    "세로 영상 자막 가독성 기준 변화 (폰트 크기·안전영역·대비)",
    "TTS 자연스러움 개선 — 최신 한국어 음성 모델과 운율 기법",
    "AI 생성 영상에 대한 유튜브 라벨·수익화 정책 동향",
    "운세·사주 니치 경쟁 채널의 최근 상위 노출 포맷",
]


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def snapshot() -> dict:
    """지금 영상이 어떤 규격으로 만들어지는지 기록한다. 제안서의 '현재 상태' 근거."""
    ms = _read(BASE / "zodiac_month_shorts.py")
    ds = _read(BASE / "zodiac_shorts.py")
    mc = _read(BASE / "zodiac_month_cards.py")

    def grab(txt: str, pat: str, default=None):
        m = re.search(pat, txt)
        return m.group(1) if m else default

    return {
        "at": _dt.datetime.now().isoformat(timespec="seconds"),
        "daily": {
            "hook_sec": grab(ds, r"HOOK_SEC\s*=\s*([\d.]+)"),
            "summary_sec": grab(ds, r"SUMMARY_SEC\s*=\s*([\d.]+)"),
            "cta_text": grab(ds, r'CTA_TEXT\s*=\s*"([^"]+)"'),
            "cta_zone": grab(ds, r"CTA_ZONE\s*=\s*\(([^)]+)\)"),
            "pngtuber": "on" if "_apply_pngtuber_pip" in ds else "off",
        },
        "monthly": {
            "variants": re.findall(r'kind == "(\d+)"', ms) or ["30", "60", "80"],
            "resolution": f'{grab(ms, r"W, H, FPS = (\d+)")}x{grab(ms, r"W, H, FPS = \d+, (\d+)")}',
            "fps": grab(ms, r"W, H, FPS = \d+, \d+, (\d+)"),
            "cta_text": grab(mc, r'CTA_TEXT\s*=\s*"([^"]+)"'),
            "safe_bottom_ratio": grab(mc, r"SAFE_BOT = int\(h \* ([\d.]+)\)"),
            "gdrive": grab(ms, r'GDRIVE_ROOT = Path\(r"([^"]+)"'),
        },
    }


def _latest_snapshot() -> dict | None:
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(SNAP_DIR.glob("snapshot_*.json"))
    if not files:
        return None
    try:
        return json.loads(files[-1].read_text(encoding="utf-8"))
    except Exception:
        return None


def _diff(old: dict | None, new: dict) -> list[str]:
    if not old:
        return ["(첫 스냅샷 — 비교 대상 없음)"]
    out = []
    for sect in ("daily", "monthly"):
        for k, v in new.get(sect, {}).items():
            ov = (old.get(sect) or {}).get(k)
            if ov != v:
                out.append(f"{sect}.{k}: {ov!r} → {v!r}")
    return out or ["(직전 회차 이후 변경 없음)"]


def run_once() -> int:
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    prev = _latest_snapshot()
    snap = snapshot()
    changes = _diff(prev, snap)
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    (SNAP_DIR / f"snapshot_{stamp}.json").write_text(
        json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")

    task = {
        "type": "video_research_proposal",
        "created": snap["at"],
        "round": stamp,
        "status": "pending",
        "auto_apply": False,                      # 승인 전 적용 금지 — 한밝님 결정
        "instruction": (
            "띠별운세 쇼츠(일일·월간)의 개선 제안서를 작성한다. "
            "아래 주제를 웹 리서치해 '현재 스펙 → 제안 → 근거 → 예상 리스크' 형식으로 "
            "docs 폴더에 .md로 저장하고, 적용 여부는 한밝님 승인을 받는다. "
            "코드를 임의로 고치지 않는다."
        ),
        "topics": RESEARCH_TOPICS,
        "current_spec": snap,
        "changes_since_last": changes,
        "proposal_path": str(BASE / "docs" / f"video_improve_{stamp}.md"),
    }

    written = []
    for q in QUEUE_DIRS:
        try:
            q.mkdir(parents=True, exist_ok=True)
            p = q / f"video_research_{stamp}.json"
            p.write_text(json.dumps(task, ensure_ascii=False, indent=2), encoding="utf-8")
            written.append(str(p))
        except Exception as e:
            print(f"[!] 큐 기록 실패({q}): {e}")

    print(f"[research] 스냅샷 저장: snapshot_{stamp}.json")
    print(f"[research] 직전 대비 변경: {len(changes)}건")
    for c in changes:
        print(f"   - {c}")
    print(f"[research] 리서치 요청 큐 {len(written)}곳 기록")
    for w in written:
        print(f"   - {w}")
    print("[research] 다음: 클로드 세션에서 이 큐를 읽어 리서치 → 제안서 작성 → 승인 후 적용")
    return 0 if written else 1


def status() -> int:
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    snaps = sorted(SNAP_DIR.glob("snapshot_*.json"))
    print(f"스냅샷 {len(snaps)}개" + (f" (최근 {snaps[-1].name})" if snaps else ""))
    for q in QUEUE_DIRS:
        if q.exists():
            pend = [p for p in q.glob("video_research_*.json")
                    if json.loads(_read(p) or "{}").get("status") == "pending"]
            print(f"  대기중 요청 {len(pend)}건 — {q}")
    r = subprocess.run(["schtasks", "/Query", "/TN", TASK_NAME],
                       capture_output=True, text=True)
    print("스케줄:", "등록됨" if r.returncode == 0 else "미등록")
    return 0


def install() -> int:
    """격주 월요일 08:00. schtasks는 /SC WEEKLY /MO 2 로 2주 간격을 지원한다."""
    pyw = Path(sys.executable).with_name("pythonw.exe")
    exe = str(pyw if pyw.exists() else sys.executable)
    cmd = ["schtasks", "/Create", "/TN", TASK_NAME, "/SC", "WEEKLY", "/MO", "2",
           "/D", "MON", "/ST", "08:00", "/F",
           "/TR", f'"{exe}" "{BASE / "zodiac_video_research.py"}" --run']
    r = subprocess.run(cmd, capture_output=True, text=True)
    print(r.stdout or r.stderr)
    if r.returncode == 0:
        print("[+] 등록 완료: 격주 월요일 08:00 — 리서치 요청만 남김(자동 적용 없음)")
    return r.returncode


def uninstall() -> int:
    r = subprocess.run(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"],
                       capture_output=True, text=True)
    print(r.stdout or r.stderr)
    return r.returncode


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    for f in ("install", "uninstall", "run", "status"):
        ap.add_argument(f"--{f}", action="store_true")
    a = ap.parse_args()
    if a.install:
        sys.exit(install())
    if a.uninstall:
        sys.exit(uninstall())
    if a.run:
        sys.exit(run_once())
    sys.exit(status())
