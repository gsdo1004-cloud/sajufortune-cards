# -*- coding: utf-8 -*-
"""Instagram 계정 실험용 릴스 A/B 변형 생성.

동일한 띠별운세 본편을 유지하되 첫 1.8초에 서로 다른 후킹 문구를 렌더링해
두 계정에 완전히 동일한 영상 파일을 재게시하지 않도록 한다.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import instagram_dual_experiment as ide

BASE = Path(__file__).resolve().parent
FONT = BASE / "assets" / "fonts" / "NanumGothic-Bold.ttf"


def hook_text(variant: str) -> str:
    key = (variant or "").strip().upper()
    if key == "A":
        return "오늘 내 띠의 흐름, 끝까지 확인하세요"
    if key == "B":
        return "재물·인연 흐름이 달라지는 띠, 내 띠도 있을까요?"
    raise ValueError(f"unknown Instagram reel variant: {variant}")


def output_path(source: Path, variant: str) -> Path:
    key = (variant or "").strip().upper()
    if key not in ide.VARIANTS:
        raise ValueError(f"unknown Instagram reel variant: {variant}")
    return source.with_name(f"{source.stem}_ig_{key}{source.suffix}")


def source_path(date_iso: str) -> Path:
    return BASE / "reels" / f"{date_iso}_tts.mp4"


def generate(date_iso: str, variant: str) -> Path:
    key = (variant or "").strip().upper()
    src = source_path(date_iso)
    out = output_path(src, key)
    if not src.exists() or src.stat().st_size < 1024:
        raise FileNotFoundError(f"base reel missing: {src}")
    if out.exists() and out.stat().st_size >= 1024:
        print(f"[SKIP] Instagram variant exists: {out}")
        return out
    if not FONT.exists():
        raise FileNotFoundError(f"font missing: {FONT}")

    out.parent.mkdir(parents=True, exist_ok=True)
    tmp_name = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".txt", delete=False) as tmp:
            tmp.write(hook_text(key))
            tmp_name = tmp.name
        vf = (
            f"drawtext=fontfile='{FONT}':textfile='{tmp_name}':"
            "fontcolor=white:fontsize=h/28:box=1:boxcolor=black@0.62:boxborderw=18:"
            "x=(w-text_w)/2:y=h*0.12:shadowx=2:shadowy=2:enable='between(t,0,1.8)'"
        )
        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(src),
            "-vf", vf,
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart",
            str(out),
        ]
        subprocess.run(cmd, check=True)
        if not out.exists() or out.stat().st_size < 1024:
            raise RuntimeError(f"Instagram variant generation produced no usable file: {out}")
        print(f"[OK] Instagram variant {key}: {out}")
        return out
    finally:
        if tmp_name:
            try:
                Path(tmp_name).unlink(missing_ok=True)
            except Exception:
                pass


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("usage: instagram_reel_variant.py YYYY-MM-DD A|B")
    generate(sys.argv[1], sys.argv[2])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
