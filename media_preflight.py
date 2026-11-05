# -*- coding: utf-8 -*-
"""Read-only public media validation before Meta publish API calls."""
from __future__ import annotations

import json
import os
import shutil
import struct
import subprocess
import requests

_IMAGE_LIMIT = 8 * 1024 * 1024
_VIDEO_LIMIT = 300 * 1024 * 1024


def _probe_video(url: str) -> tuple[bool, str]:
    if os.environ.get("MEDIA_PREFLIGHT_FFPROBE", "1") == "0":
        return True, "ffprobe disabled"
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return True, "ffprobe unavailable; HTTP/header only"
    try:
        proc = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries",
             "stream=codec_type,codec_name,width,height:format=duration",
             "-of", "json", url],
            capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"ffprobe {type(exc).__name__}"
    if proc.returncode:
        return False, f"ffprobe rejected source (exit={proc.returncode})"
    try:
        data = json.loads(proc.stdout)
        streams = data.get("streams") or []
        video = next(s for s in streams if s.get("codec_type") == "video")
        audios = [s for s in streams if s.get("codec_type") == "audio"]
        duration = float((data.get("format") or {}).get("duration") or 0)
    except (ValueError, TypeError, StopIteration, AttributeError):
        return False, "ffprobe missing video stream or duration"
    if duration <= 0 or video.get("codec_name") not in {"h264", "hevc"}:
        return False, "unsupported video codec or duration"
    if audios and any(s.get("codec_name") != "aac" for s in audios):
        return False, "unsupported audio codec"
    if int(video.get("width") or 0) <= 0 or int(video.get("height") or 0) <= 0:
        return False, "missing video dimensions"
    return True, f"codec={video['codec_name']} duration={duration:.1f}s"


def check_public_media(url: str, kind: str) -> tuple[bool, str]:
    """Check public HTTP response, media signature and size; no Meta calls."""
    if kind not in {"image", "video"}:
        raise ValueError(f"unknown media type: {kind}")
    try:
        response = requests.get(url, stream=True, timeout=20, allow_redirects=True)
        try:
            if response.status_code != 200:
                return False, f"HTTP {response.status_code}"
            content_type = (response.headers.get("content-type") or "").lower()
            if content_type.startswith(("text/", "application/json")):
                return False, f"unexpected Content-Type {content_type}"
            raw_size = response.headers.get("content-length")
            try:
                size = int(raw_size) if raw_size is not None else None
            except (ValueError, TypeError):
                return False, "invalid Content-Length"
            limit = _IMAGE_LIMIT if kind == "image" else _VIDEO_LIMIT
            if size is not None and not (1024 <= size <= limit):
                return False, f"out-of-range size {size}"
            header = next(response.iter_content(chunk_size=32), b"")
            if kind == "image":
                if header.startswith(b"\x89PNG\r\n\x1a\n") and len(header) >= 24:
                    width, height = struct.unpack(">II", header[16:24])
                    if not width or not height:
                        return False, "invalid PNG dimensions"
                    detail = f"PNG {width}x{height}"
                elif header.startswith(b"\xff\xd8\xff"):
                    detail = "JPEG"
                else:
                    return False, "invalid image signature"
            else:
                if len(header) < 12 or header[4:8] != b"ftyp":
                    return False, "invalid MP4 signature"
                detail = "MP4"
        finally:
            response.close()
    except requests.RequestException as exc:
        return False, f"{type(exc).__name__}: {str(exc)[:120]}"
    if kind == "video":
        passed, meta = _probe_video(url)
        if not passed:
            return False, meta
        detail += f" {meta}"
    return True, f"HTTP 200 {detail} size={size if size is not None else 'unknown'}"
