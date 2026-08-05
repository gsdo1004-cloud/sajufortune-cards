#!/usr/bin/env python3
"""
pngtuber_avatar.py — 음성 반응형 PNGTuber 아바타 클립 생성기 (다단계 입모양).

TTS 음성 파일과 입모양 이미지 여러 장(닫힘→열림 순서, 선택적으로 블링크)을 받아
음량 크기에 비례해 단계적으로 전환되는 무음 영상을 만든다. 2장(닫힘/열림)만
쓰면 기존 방식과 동일하게 동작하고, 3~4장을 주면 음량 크기에 따라 살짝 벌림
→ 반쯤 벌림 → 크게 벌림 순으로 단계가 세분화되어 훨씬 자연스럽다.

프레임 세트는 같은 짧은 구간(수백 ms 이내)에서 몸통·손 위치가 고정된 채
입모양만 다른 지점들을 골라야 전환 시 "튀는" 느낌이 없다.

출력은 무음 영상이다 — 본편에 이미 같은 내레이션 오디오가 있으므로
휴먼터치pip PIP 합성 시 이 클립엔 오디오를 섞지 않는다.

사용법:
    python pngtuber_avatar.py --audio narration.mp3 \
        --frames mouth_0_closed.png mouth_1_slight.png mouth_2_half.png mouth_3_wide.png \
        --out avatar_pip.mp4 [--blink blink.png] [--fps 24] [--window-ms 90]
"""

import argparse
import os
import random
import struct
import subprocess
import sys
import tempfile
import wave
from collections import Counter

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def run(cmd):
    # 한글 경로가 섞인 ffmpeg stderr를 시스템 기본 코드페이지(cp949)로 디코딩하면
    # UnicodeDecodeError가 나므로 UTF-8로 명시 디코딩한다.
    result = subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise RuntimeError(f"명령 실패: {' '.join(cmd)}\n{result.stderr}")
    return result.stdout


def to_mono_wav(src_path, dst_path, sample_rate=16000):
    run([
        "ffmpeg", "-y", "-i", src_path,
        "-ar", str(sample_rate), "-ac", "1", "-f", "wav", dst_path,
    ])


def read_rms_windows(wav_path, window_ms):
    with wave.open(wav_path, "rb") as wf:
        sample_rate = wf.getframerate()
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        if sampwidth != 2:
            raise ValueError("16-bit PCM WAV만 지원합니다")
        window_samples = max(1, int(sample_rate * window_ms / 1000))
        rms_values = []
        while True:
            frames = wf.readframes(window_samples)
            if not frames:
                break
            count = len(frames) // (2 * n_channels)
            if count == 0:
                break
            samples = struct.unpack(f"<{count * n_channels}h", frames[: count * n_channels * 2])
            if n_channels > 1:
                samples = samples[::n_channels]
            sq_sum = sum(s * s for s in samples)
            rms = (sq_sum / len(samples)) ** 0.5
            rms_values.append(rms)
        duration_sec = wf.getnframes() / sample_rate
    return rms_values, duration_sec


def default_thresholds(n_frames):
    """N장짜리 프레임 세트에 맞춰 0.12~0.7 구간을 균등 분배한 임계값(N-1개) 생성."""
    if n_frames <= 1:
        return []
    lo, hi = 0.12, 0.7
    step = (hi - lo) / (n_frames - 1)
    return [round(lo + step * i, 4) for i in range(n_frames - 1)]


def build_mouth_schedule(rms_values, thresholds, min_hold_windows):
    """thresholds: 오름차순 임계값(피크 대비 비율) N-1개. 윈도우별 입모양 단계
    인덱스(0=가장 닫힘 ~ N-1=가장 벌림) 리스트를 반환한다."""
    if not rms_values:
        return []
    peak = max(rms_values) or 1.0
    levels = []
    for v in rms_values:
        ratio = v / peak
        level = sum(1 for t in thresholds if ratio >= t)
        levels.append(level)

    # 최소 유지 윈도우 수보다 짧게 튀는 전환은 이전 단계로 스무딩 (입모양 떨림 방지)
    smoothed = list(levels)
    i = 0
    while i < len(smoothed):
        j = i
        while j < len(smoothed) and smoothed[j] == smoothed[i]:
            j += 1
        if j - i < min_hold_windows and i > 0:
            for k in range(i, j):
                smoothed[k] = smoothed[i - 1]
        i = j
    return smoothed


def inject_blinks(schedule, window_ms, blink_every_sec_range=(3.0, 6.0), blink_hold_windows=2,
                   double_blink_prob=0.12, double_blink_gap_ms_range=(200, 300)):
    """블링크 위치를 생성한다. 실제 사람은 종종 한 번 더 깜빡이는 더블 블링크를
    보이므로, 매 블링크마다 일정 확률로 200~300ms 뒤 재블링크를 추가한다."""
    windows_per_sec = 1000 / window_ms
    blink_positions = []
    t = random.uniform(*blink_every_sec_range)
    while t * windows_per_sec < len(schedule):
        idx = int(t * windows_per_sec)
        blink_positions.append(idx)
        if random.random() < double_blink_prob:
            gap_windows = max(1, int(random.uniform(*double_blink_gap_ms_range) / window_ms))
            second_idx = idx + blink_hold_windows + gap_windows
            if second_idx < len(schedule):
                blink_positions.append(second_idx)
        t += random.uniform(*blink_every_sec_range)
    return blink_positions, blink_hold_windows


def pick_image(idx, schedule, frames, blink_img, blink_set):
    if blink_img and idx in blink_set:
        return blink_img
    return frames[schedule[idx]]


def write_concat_list(schedule, window_ms, frames, blink_img, blink_positions, blink_hold_windows, list_path):
    blink_set = set()
    for pos in blink_positions:
        for k in range(pos, min(pos + blink_hold_windows, len(schedule))):
            blink_set.add(k)

    lines = []
    for idx in range(len(schedule)):
        img = pick_image(idx, schedule, frames, blink_img, blink_set)
        safe_path = os.path.abspath(img).replace("\\", "/")
        lines.append(f"file '{safe_path}'")
        lines.append(f"duration {window_ms / 1000:.4f}")

    # concat demuxer는 마지막 항목의 duration을 적용하지 않는 known issue가 있어
    # 종료 경계를 위해 마지막 이미지를 한 번 더 반복 기재한다.
    if schedule:
        last_img = pick_image(len(schedule) - 1, schedule, frames, blink_img, blink_set)
        lines.append(f"file '{os.path.abspath(last_img).replace(chr(92), '/')}'")

    with open(list_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def generate(audio, frames, out, blink=None, window_ms=90, thresholds=None,
             min_hold_windows=2, fps=24):
    """음성 반응형 아바타 클립을 생성하고 요약 통계 dict를 반환한다.
    frames: 닫힘→열림 순서로 정렬된 입모양 이미지 경로 리스트 (최소 2장).
    CLI(main)와 다른 스크립트(pngtuber_shorts_pip 등)가 공통으로 호출하는 진입점."""
    if len(frames) < 2:
        raise ValueError("frames는 최소 2장 이상이어야 합니다 (닫힘~열림 순서)")
    if thresholds is None:
        thresholds = default_thresholds(len(frames))
    elif len(thresholds) != len(frames) - 1:
        raise ValueError(f"thresholds 개수는 frames 개수-1({len(frames) - 1})개여야 합니다")

    with tempfile.TemporaryDirectory() as tmp:
        wav_path = os.path.join(tmp, "audio.wav")
        to_mono_wav(audio, wav_path)

        rms_values, duration_sec = read_rms_windows(wav_path, window_ms)
        schedule = build_mouth_schedule(rms_values, thresholds, min_hold_windows)
        blink_positions, blink_hold_windows = ([], 0) if not blink else inject_blinks(schedule, window_ms)

        list_path = os.path.join(tmp, "frames.txt")
        write_concat_list(schedule, window_ms, frames, blink,
                           blink_positions, blink_hold_windows, list_path)

        # yuv420p는 알파 채널이 없어 배경 제거(rembg)한 프레임을 넣어도 최종 출력에서
        # 투명 정보가 사라진다. .mov로 출력을 요청하면 알파 보존 코덱(qtrle)을 쓴다.
        if os.path.splitext(out)[1].lower() == ".mov":
            video_args = ["-c:v", "qtrle"]
        else:
            video_args = ["-pix_fmt", "yuv420p"]

        run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_path,
            "-vsync", "cfr", "-r", str(fps),
            *video_args, "-an",
            out,
        ])

    counts = Counter(schedule)
    level_dist = ({lvl: round(counts.get(lvl, 0) / len(schedule) * 100)
                   for lvl in range(len(frames))} if schedule else {})
    return {"duration_sec": duration_sec, "level_dist": level_dist, "blinks": len(blink_positions)}


def main():
    parser = argparse.ArgumentParser(description="음성 반응형 PNGTuber 아바타 클립 생성 (다단계 입모양)")
    parser.add_argument("--audio", required=True)
    parser.add_argument("--frames", required=True, nargs="+",
                         help="입모양 이미지 목록, 닫힘→열림 순서로 최소 2장")
    parser.add_argument("--blink", default=None, help="눈 깜빡임 이미지 (선택)")
    parser.add_argument("--out", required=True)
    parser.add_argument("--window-ms", type=int, default=90, help="입모양 판정 윈도우 길이(ms)")
    parser.add_argument("--thresholds", type=float, nargs="+", default=None,
                         help="단계 전환 임계값들 (frames 개수-1개, 0~1 피크 대비 비율). 생략 시 자동 균등 분배")
    parser.add_argument("--min-hold-windows", type=int, default=2, help="상태 전환 최소 유지 윈도우 수 (떨림 방지)")
    parser.add_argument("--fps", type=int, default=24)
    args = parser.parse_args()

    result = generate(args.audio, args.frames, args.out, args.blink,
                       args.window_ms, args.thresholds, args.min_hold_windows, args.fps)
    dist_str = ", ".join(f"{lvl}단계 {pct}%" for lvl, pct in sorted(result["level_dist"].items()))
    print(f"완료: {args.out}")
    print(f"길이: {result['duration_sec']:.1f}초 / 입모양 분포: {dist_str} / 블링크 {result['blinks']}회")


if __name__ == "__main__":
    main()
