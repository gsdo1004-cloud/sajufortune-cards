#!/usr/bin/env python3
"""
pngtuber_shorts_pip.py — 쇼츠 본편에 PNGTuber 반응형 아바타를 PIP로 합성.

human_touch_pip.py의 위치 로테이션·페이드·상태파일 컨벤션을 그대로 따르되,
쇼츠(60초 안팎) 전체 구간에 반응형 아바타를 얹는다는 점이 다르다 — 기존
아바타 로직은 5분+ 영상에서 10초짜리 컷어웨이 1회용으로 설계돼 있어
쇼츠 전체를 커버하는 이 용도와는 맞지 않는다.

흐름:
  1. 본편에서 오디오 추출
  2. pngtuber_avatar로 음성 반응형 아바타 클립 생성 (본편과 동일한 길이,
     동일한 오디오 기준이라 별도 오프셋 없이 그대로 겹치면 싱크가 맞는다)
  3. human_touch_pip과 동일한 위치 로테이션 상태(_pip_state.json)를 공유하며
     본편 전체 길이에 걸쳐 PIP 합성

사용법:
  python pngtuber_shorts_pip.py <쇼츠본편.mp4> \
      --frames mouth_0_closed.png mouth_1_slight.png mouth_2_half.png mouth_3_wide.png \
      [--blink blink.png] [--pool 풀폴더]
"""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import human_touch_pip as htp
import pngtuber_avatar as pnt

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# 쇼츠 전용 위치. htp.POSITIONS(롱폼 바디캠용)는 상단·중단 4종뿐이라 그대로 쓰면
# 아바타가 화면 위쪽에 걸린다. 여기서 자체 좌표를 정의한다.
#
# [2026-07-30] 한밝님 지적: "좌상단에 붕 떠 있다".
#   원인 둘. (1) 아바타가 사각형 크롭이라 몸통이 허리께에서 직선으로 끊긴다.
#   화면 위쪽에 놓으면 그 잘린 면이 공중에 뜬 것처럼 보인다.
#   (2) htp.POSITIONS의 좌측상단은 y=H*0.03인데, **네이버 클립의 X(닫기) 버튼이
#   정확히 거기다.** 틱톡에서는 괜찮았지만 네이버에서는 가려지고 있었다.
#
# 발행하는 3개 플랫폼의 UI를 실측해 잡은 교집합 안전영역
# (네이버 클립·틱톡은 실제 발행 화면 캡처, 유튜브 쇼츠는 공개 사양):
#
#   구분   유튜브 쇼츠      네이버 클립        틱톡              채택
#   상단   소량            X·분석 버튼 3%     검색바 4%         5% 아래
#   우측   버튼열 81%~     버튼열 88%~        버튼열 90%~       27% 왼쪽
#   하단   380px = 80%~    프로필·설명 83%~   채널명 78%~       78% 위
#
# 가장 빡빡한 값을 취하면 하단 78%(틱톡)다. 다만 경계에 딱 붙이면 여유가 0이라
# 설명 펼침·기기 화면비에 따라 먹힐 수 있어 2% 마진을 둔다 → 아바타 하단 76%.
# 폭 24%면 높이도 약 24%이므로 최종 y는 52%~76%, x는 3%~27%.
#
# 바닥에 붙이는 것은 불가능하다. 롱폼은 화면 아래 경계에 붙여 잘린 면을 감췄지만,
# 쇼츠는 그 자리를 채널명·설명이 덮는다.
SHORTS_POSITIONS = [
    ("좌측하단", "W*0.03", "H*0.76-h"),
]


# 아바타 하단 알파 페이드
#
# 아바타 PNG는 사각형이라 몸통이 아래에서 직선으로 끊긴다. 그대로 얹으면
# 그 잘린 면이 배경 위에 떠 보인다("붕 떠 있다"). 롱폼은 화면 아래 경계에
# 붙여 감췄지만 쇼츠는 그 자리를 채널명·설명이 덮어 못 붙인다.
#
# 그래서 이미지 자체의 하단을 서서히 투명하게 만들어 경계를 없앤다.
# 클립 생성 전 PNG 4장에 한 번만 적용한다 — 합성 필터에 넣으면 82초 x 30fps,
# 즉 2400여 프레임마다 픽셀 단위 수식을 돌게 된다.
#
# geq는 r/g/b를 함께 지정해야 초기화된다. a만 주면 "Error initializing filters"로
# 죽는다(2026-07-30 실측).
# 이 지점부터 아래로 서서히 투명. 0.72로 잡았더니 모아 쥔 손까지 반투명해졌다.
# 손은 온전히 보여야 해서 0.82로 내렸다(페이드 구간 = 이미지 하단 18%).
FADE_FROM = 0.82
_FADE_VF = (
    "format=rgba,"
    "geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':"
    f"a='alpha(X,Y)*if(gt(Y,H*{FADE_FROM}),(H-Y)/(H*{1 - FADE_FROM:.2f}),1)'"
)


def fade_frames(frames, work_dir):
    """프레임 PNG들의 하단을 알파 페이드한 사본을 만들어 경로 목록을 돌려준다.

    한 장이라도 실패하면 그 장은 원본을 쓴다 — 페이드는 미관 문제라
    양산을 멈출 이유가 아니다.
    """
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    out = []
    for i, src in enumerate(frames):
        dst = work / f"_faded_{i}.png"
        r = subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(src),
             "-vf", _FADE_VF, "-frames:v", "1", str(dst)],
            capture_output=True, text=True)
        out.append(str(dst) if r.returncode == 0 and dst.exists() else str(src))
    return out


def _run(cmd):
    result = subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise RuntimeError(f"명령 실패: {' '.join(cmd)}\n{result.stderr}")
    return result.stdout


def extract_audio(video_path, out_path):
    _run(["ffmpeg", "-y", "-i", str(video_path), "-vn", "-acodec", "pcm_s16le", str(out_path)])


def compose(video_path, frames, blink_img=None, pool_dir=None, tmp_dir=None):
    video_path = Path(video_path)
    pool = Path(pool_dir or os.environ.get("SELLFARM_PIP_POOL", htp.DEFAULT_POOL))

    dur, W, H = htp._probe(video_path)
    if dur <= 0:
        raise RuntimeError(f"본편 분석 실패: {video_path}")

    tmp = Path(tmp_dir) if tmp_dir else video_path.parent
    audio_path = tmp / "_pngtuber_narration.wav"
    # .mov + qtrle(pngtuber_avatar.generate 참조)라야 알파 채널이 살아남는다.
    # frames가 배경 제거(rembg, RGBA)된 이미지가 아니면 애초에 투명 정보가 없다.
    avatar_clip = tmp / "_pngtuber_reactive.mov"

    try:
        extract_audio(video_path, audio_path)

        # 하단 알파 페이드를 프레임 PNG에 먼저 입힌다. blink도 같은 처리를 해야
        # 눈 깜빡일 때만 잘린 면이 다시 나타나는 일이 없다.
        fade_dir = tmp / "_faded"
        faded = fade_frames(frames, fade_dir)
        faded_blink = fade_frames([blink_img], fade_dir / "b")[0] if blink_img else None

        # 본편과 동일한 오디오에서 그대로 생성하므로 오프셋 없이 t=0부터 dur까지
        # 겹치면 발화 타이밍이 그대로 맞는다.
        pnt.generate(str(audio_path), faded, str(avatar_clip), blink=faded_blink)

        state = htp._load_state(pool)
        pos_i = state.get("pos_index", 0)
        pos_name, xe, ye = SHORTS_POSITIONS[pos_i % len(SHORTS_POSITIONS)]
        pw = int(W * htp.PIP_WIDTH_RATIO) // 2 * 2

        # 은은한 idle sway: 완전 정지 이미지처럼 안 보이게 좌표를 sine으로 미세하게
        # 흔든다(진폭 1.5~2px, 주기 3~4초대). 시니어 타겟 콘텐츠라 진폭은 최소로 유지.
        sway_x = f"({xe}+2*sin(2*PI*t/3.7))"
        sway_y = f"({ye}+1.5*sin(2*PI*t/4.3+1))"
        filt = (
            f"[1:v]scale={pw}:-2,format=yuva420p,"
            f"fade=t=in:st=0:d={htp.FADE_SEC}:alpha=1,"
            f"fade=t=out:st={dur - htp.FADE_SEC:.2f}:d={htp.FADE_SEC}:alpha=1"
            f"[p0];[0:v][p0]overlay=x='{sway_x}':y='{sway_y}':eof_action=pass[vout]"
        )

        tmp_out = video_path.parent / "_pngtuber_pip_tmp.mp4"
        cmd = [
            "ffmpeg", "-y", "-nostdin", "-i", str(video_path), "-i", str(avatar_clip),
            "-filter_complex", filt,
            "-map", "[vout]", "-map", "0:a?",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            "-pix_fmt", "yuv420p", "-c:a", "copy", str(tmp_out),
        ]
        result = subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace")
        if result.returncode != 0 or not tmp_out.exists():
            raise RuntimeError(f"PIP 합성 실패: {(result.stderr or '')[-500:]}")

        os.replace(str(tmp_out), str(video_path))
    finally:
        for f in (audio_path, avatar_clip):
            if f.exists():
                f.unlink()
        shutil.rmtree(tmp / "_faded", ignore_errors=True)

    # 쇼츠 목록 길이로 돈다. 예전엔 htp.POSITIONS(4종) 길이를 썼는데
    # 실제로 고르는 건 SHORTS_POSITIONS라 인덱스가 어긋났다.
    state["pos_index"] = (pos_i + 1) % len(SHORTS_POSITIONS)
    htp._save_state(pool, state)

    return {"위치": pos_name, "길이": round(dur, 1)}


def main():
    ap = argparse.ArgumentParser(description="쇼츠 본편에 PNGTuber 반응형 아바타 PIP 합성")
    ap.add_argument("video")
    ap.add_argument("--frames", required=True, nargs="+", help="입모양 이미지 목록, 닫힘→열림 순서로 최소 2장")
    ap.add_argument("--blink", default=None)
    ap.add_argument("--pool", default=None)
    args = ap.parse_args()

    info = compose(args.video, args.frames, args.blink, args.pool)
    print(f"완료: {info['위치']} 위치에 {info['길이']}초 합성")


if __name__ == "__main__":
    main()
