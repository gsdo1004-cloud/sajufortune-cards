# -*- coding: utf-8 -*-
r"""유튜브 업로드 (GitHub Actions 용) — 2026-08-06

왜 새로 만들었나: 여태 유튜브 업로드는 집 PC 의 music_pipeline/04_auto_upload.py 가
했는데, 그 경로가 zodiac_daily_pipeline 은퇴와 함께 끊겼다. Actions 안에서 끝내려면
러너에서 돌 수 있는 업로더가 이 레포에 있어야 한다.

인증: 시크릿 두 개를 파일로 떨어뜨려 쓴다(값을 인자로 넘기면 로그에 남는다).
  YOUTUBE_TOKEN_UNMYEONG   운명과학TV 사용자 토큰(refresh_token 포함)
  YOUTUBE_CLIENT_SECRETS   OAuth 클라이언트(토큰 갱신에 필요)

발행 규칙: **항상 private + publishAt 예약공개**. 즉시 공개하지 않는다.
  [[feedback_youtube_private_default]] — 올라가자마자 공개되면 되돌릴 틈이 없다.
  publishAt 이 과거면 유튜브가 거부하므로, 지난 시각은 다음 슬롯으로 민다.

사용:
  python youtube_upload.py --file reels/2026-08-06_signal.mp4 \
      --title "..." --description "..." --publish-at 2026-08-07T12:00:00+09:00
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]
KST = dt.timezone(dt.timedelta(hours=9))

# 채널 오업로드 방지 — 운명과학TV 가 아니면 멈춘다. 브랜드 채널이 여러 개라
# 토큰이 바뀌면 엉뚱한 채널로 나갈 수 있고, 그건 되돌리기가 매우 번거롭다.
EXPECT_CHANNEL_TITLE = os.environ.get("YOUTUBE_EXPECT_CHANNEL", "운명과학TV").strip()


def _write_secret(env_name: str, path: Path) -> Path | None:
    """시크릿 문자열을 파일로. 값은 절대 출력하지 않는다."""
    raw = os.environ.get(env_name, "").strip()
    if not raw:
        return None
    try:
        json.loads(raw)                     # 형식만 확인
    except json.JSONDecodeError:
        print(f"[오류] {env_name} 이 JSON 이 아닙니다(값은 표시하지 않습니다).")
        return None
    path.write_text(raw, encoding="utf-8")
    return path


def _credentials():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request

    tok = _write_secret("YOUTUBE_TOKEN_UNMYEONG", BASE / "_yt_token.json")
    if not tok:
        print("[오류] YOUTUBE_TOKEN_UNMYEONG 시크릿이 없습니다.")
        return None
    cli = _write_secret("YOUTUBE_CLIENT_SECRETS", BASE / "_yt_client.json")

    creds = Credentials.from_authorized_user_file(str(tok), SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            print("  토큰 만료 → refresh_token 으로 갱신")
            creds.refresh(Request())
        else:
            print("[오류] 토큰이 유효하지 않고 갱신도 불가합니다. 로컬에서 재인증이 필요합니다.")
            return None
    if cli:
        cli.unlink(missing_ok=True)         # 쓰고 바로 지운다
    return creds


def _next_slot(publish_at: str | None, slot_hours: list[int]) -> str:
    """예약 시각 결정. 인자로 받은 값이 과거면 다음 슬롯으로 민다."""
    now = dt.datetime.now(KST)
    if publish_at:
        try:
            want = dt.datetime.fromisoformat(publish_at)
            if want.tzinfo is None:
                want = want.replace(tzinfo=KST)
            if want > now + dt.timedelta(minutes=10):
                return want.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")
            print(f"  [주의] 지정 시각({publish_at})이 지났거나 임박 → 다음 슬롯으로 밉니다")
        except ValueError:
            print(f"  [주의] publish-at 형식 오류({publish_at}) → 다음 슬롯으로 밉니다")

    cand = []
    for d in (0, 1):
        for h in slot_hours:
            t = (now + dt.timedelta(days=d)).replace(hour=h, minute=0, second=0, microsecond=0)
            if t > now + dt.timedelta(minutes=20):
                cand.append(t)
    pick = min(cand)
    return pick.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def upload(video: Path, title: str, description: str, tags: list[str],
           publish_at: str | None, slot_hours: list[int],
           thumbnail: Path | None = None) -> str | None:
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    creds = _credentials()
    if not creds:
        return None
    youtube = build("youtube", "v3", credentials=creds)

    me = youtube.channels().list(part="snippet", mine=True).execute()
    items = me.get("items") or []
    if not items:
        print("[오류] 채널 조회 실패 — 토큰 권한을 확인하십시오.")
        return None
    ch_title = items[0]["snippet"]["title"]
    if EXPECT_CHANNEL_TITLE and ch_title.strip() != EXPECT_CHANNEL_TITLE:
        print(f"[중단] 토큰이 가리키는 채널이 '{ch_title}' 입니다. "
              f"'{EXPECT_CHANNEL_TITLE}' 가 아니라 올리지 않습니다.")
        return None
    print(f"  대상 채널: {ch_title}")

    when = _next_slot(publish_at, slot_hours)
    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:4900],
            "tags": tags[:30],
            "categoryId": "24",             # Entertainment
        },
        "status": {
            "privacyStatus": "private",     # 항상 비공개로 올리고
            "publishAt": when,              # 이 시각에 유튜브가 공개한다
            "selfDeclaredMadeForKids": False,
            # TTS·AI 이미지를 쓰므로 합성 미디어로 신고한다
            "containsSyntheticMedia": True,
        },
    }
    print(f"  예약 공개: {when} (UTC)")

    media = MediaFileUpload(str(video), mimetype="video/mp4",
                            chunksize=-1, resumable=True)
    req = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    resp = None
    while resp is None:
        status, resp = req.next_chunk()
        if status:
            print(f"  업로드 {int(status.progress() * 100)}%")
    vid = resp.get("id")
    print(f"  완료: https://youtu.be/{vid}")

    if thumbnail and Path(thumbnail).exists():
        try:
            youtube.thumbnails().set(
                videoId=vid,
                media_body=MediaFileUpload(str(thumbnail), mimetype="image/jpeg")).execute()
            print("  썸네일 설정 완료")
        except Exception as e:  # noqa: BLE001
            print(f"  썸네일 실패(무시): {str(e)[:120]}")

    (BASE / "_yt_token.json").unlink(missing_ok=True)
    return vid


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--description", default="")
    ap.add_argument("--tags", default="운세,사주,띠운세,오늘의운세")
    ap.add_argument("--publish-at", default=None,
                    help="RFC3339 (예: 2026-08-07T12:00:00+09:00). 과거면 다음 슬롯으로 민다")
    ap.add_argument("--slot-hours", default="12",
                    help="예약 슬롯 시각들(쉼표). 기본 12시")
    ap.add_argument("--thumbnail", default=None)
    a = ap.parse_args()

    video = Path(a.file)
    if not video.exists():
        print(f"[오류] 영상 없음: {video}")
        return 1

    slots = [int(x) for x in a.slot_hours.split(",") if x.strip().isdigit()] or [12]
    vid = upload(video, a.title, a.description,
                 [t.strip() for t in a.tags.split(",") if t.strip()],
                 a.publish_at, slots,
                 Path(a.thumbnail) if a.thumbnail else None)
    return 0 if vid else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    sys.exit(main())
