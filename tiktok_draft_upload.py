# -*- coding: utf-8 -*-
"""TikTok Content Posting API — Draft(Inbox) 업로드 + OAuth 인증 (2026-07-20).

공식 문서 실시간 확인(developers.tiktok.com):
  - OAuth authorize: https://www.tiktok.com/v2/auth/authorize/
  - Token exchange:  https://open.tiktokapis.com/v2/oauth/token/
  - Draft(inbox) init: https://open.tiktokapis.com/v2/post/publish/inbox/video/init/
    (Direct Post용 video.publish 스코프 불필요 — video.upload만 있으면 됨.
     인박스에 초안으로 들어가고, 한밝님이 틱톡 앱에서 알림 눌러 최종 게시)

키 저장(1회, 채팅에 값 남기지 않고 바로 자격증명관리자에 저장):
    python -c "import keyring; keyring.set_password('hanbak/global','TIKTOK_CLIENT_KEY', input('client key: '))"
    python -c "import keyring; keyring.set_password('hanbak/global','TIKTOK_CLIENT_SECRET', input('client secret: '))"

TikTok 개발자 포털의 Redirect URI 칸에 아래 값을 정확히 등록해야 함:
    http://localhost:8921/callback

사용법:
    python tiktok_draft_upload.py auth              # 최초 1회, 브라우저 로그인 필요
    python tiktok_draft_upload.py upload <video.mp4>  # 인박스에 초안 업로드
"""
from __future__ import annotations

import base64
import hashlib
import http.server
import json
import keyring
import secrets
import sys
import threading
import time
import urllib.parse
import webbrowser
from pathlib import Path

import requests

KEYRING_SERVICE = "hanbak/global"
AUTHORIZE_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
INBOX_INIT_URL = "https://open.tiktokapis.com/v2/post/publish/inbox/video/init/"
REDIRECT_URI = "http://localhost:8921/callback/"
SCOPES = "user.info.basic,video.upload"
CHUNK_SIZE = 10_000_000  # 10MB — TikTok 권장 청크 크기


def _get(key: str) -> str | None:
    return keyring.get_password(KEYRING_SERVICE, key)


def _set(key: str, value: str) -> None:
    keyring.set_password(KEYRING_SERVICE, key, value)


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    result = {}

    def do_GET(self):
        qs = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(qs)
        _CallbackHandler.result["code"] = params.get("code", [None])[0]
        _CallbackHandler.result["state"] = params.get("state", [None])[0]
        _CallbackHandler.result["error"] = params.get("error", [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write("<h2>인증 완료 — 이 탭 닫고 터미널로 돌아가세요.</h2>".encode("utf-8"))

    def log_message(self, *args):
        pass  # 콘솔 스팸 방지


def authorize() -> None:
    client_key = _get("TIKTOK_CLIENT_KEY")
    client_secret = _get("TIKTOK_CLIENT_SECRET")
    if not client_key or not client_secret:
        raise SystemExit(
            "[FAIL] TIKTOK_CLIENT_KEY/TIKTOK_CLIENT_SECRET 없음 — 먼저 keyring에 저장하세요 (파일 상단 주석 참고)"
        )

    state = secrets.token_urlsafe(16)
    # PKCE — Desktop 플랫폼 필수(문서: "Required for mobile and desktop app only")
    code_verifier = secrets.token_urlsafe(64)[:128]
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode("ascii")).digest()
    ).decode("ascii").rstrip("=")
    url = (
        f"{AUTHORIZE_URL}?client_key={client_key}&scope={SCOPES}"
        f"&response_type=code&redirect_uri={urllib.parse.quote(REDIRECT_URI, safe='')}"
        f"&state={state}&code_challenge={code_challenge}&code_challenge_method=S256"
    )

    server = http.server.HTTPServer(("localhost", 8921), _CallbackHandler)
    t = threading.Thread(target=server.handle_request, daemon=True)
    t.start()

    print(f"브라우저에서 아래 URL을 열어 로그인·동의하세요 (자동으로 안 열리면 직접 클릭):\n{url}\n")
    try:
        webbrowser.open(url)
    except Exception:
        pass

    t.join(timeout=300)
    result = _CallbackHandler.result
    if not result or result.get("error"):
        raise SystemExit(f"[FAIL] 인증 실패/타임아웃: {result}")
    if result.get("state") != state:
        raise SystemExit("[FAIL] state 불일치 — CSRF 의심, 중단")

    code = result["code"]
    r = requests.post(
        TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_key": client_key,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": REDIRECT_URI,
            "code_verifier": code_verifier,
        },
        timeout=30,
    )
    r.raise_for_status()
    tok = r.json()
    if "access_token" not in tok:
        raise SystemExit(f"[FAIL] 토큰 교환 실패: {tok}")

    _set("TIKTOK_ACCESS_TOKEN", tok["access_token"])
    _set("TIKTOK_REFRESH_TOKEN", tok["refresh_token"])
    _set("TIKTOK_TOKEN_EXPIRES_AT", str(int(time.time()) + int(tok["expires_in"]) - 60))
    print(f"인증 완료. scope={tok.get('scope')} open_id={tok.get('open_id')}")


def _refresh() -> str:
    client_key = _get("TIKTOK_CLIENT_KEY")
    client_secret = _get("TIKTOK_CLIENT_SECRET")
    refresh_token = _get("TIKTOK_REFRESH_TOKEN")
    if not refresh_token:
        raise SystemExit("[FAIL] 리프레시 토큰 없음 — 'auth'부터 먼저 실행하세요")
    r = requests.post(
        TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_key": client_key,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
        timeout=30,
    )
    r.raise_for_status()
    tok = r.json()
    if "access_token" not in tok:
        raise SystemExit(f"[FAIL] 토큰 갱신 실패: {tok}")
    _set("TIKTOK_ACCESS_TOKEN", tok["access_token"])
    _set("TIKTOK_REFRESH_TOKEN", tok["refresh_token"])
    _set("TIKTOK_TOKEN_EXPIRES_AT", str(int(time.time()) + int(tok["expires_in"]) - 60))
    return tok["access_token"]


def get_access_token() -> str:
    exp = _get("TIKTOK_TOKEN_EXPIRES_AT")
    if exp and int(exp) > int(time.time()):
        return _get("TIKTOK_ACCESS_TOKEN")
    print("액세스 토큰 만료/없음 — 갱신 시도")
    return _refresh()


def upload_draft(video_path: str) -> str:
    """영상을 틱톡 인박스에 초안으로 업로드. 반환: publish_id."""
    path = Path(video_path)
    if not path.exists():
        raise SystemExit(f"[FAIL] 파일 없음: {path}")
    token = get_access_token()
    size = path.stat().st_size
    chunk_size = min(CHUNK_SIZE, size)
    total_chunks = max(1, (size + chunk_size - 1) // chunk_size)

    init = requests.post(
        INBOX_INIT_URL,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"},
        json={"source_info": {
            "source": "FILE_UPLOAD",
            "video_size": size,
            "chunk_size": chunk_size,
            "total_chunk_count": total_chunks,
        }},
        timeout=30,
    )
    init.raise_for_status()
    body = init.json()
    if body.get("error", {}).get("code") not in (None, "ok"):
        raise SystemExit(f"[FAIL] init 실패: {body}")
    publish_id = body["data"]["publish_id"]
    upload_url = body["data"]["upload_url"]
    print(f"init 완료. publish_id={publish_id}, {total_chunks}개 청크 업로드 시작")

    with open(path, "rb") as f:
        for i in range(total_chunks):
            start = i * chunk_size
            data = f.read(chunk_size)
            end = start + len(data) - 1
            r = requests.put(
                upload_url,
                headers={
                    "Content-Range": f"bytes {start}-{end}/{size}",
                    "Content-Type": "video/mp4",
                },
                data=data,
                timeout=120,
            )
            if r.status_code not in (200, 201, 206):
                raise SystemExit(f"[FAIL] 청크 {i+1}/{total_chunks} 업로드 실패({r.status_code}): {r.text[:300]}")
            print(f"  청크 {i+1}/{total_chunks} 완료")

    print(f"✅ 인박스 업로드 완료. publish_id={publish_id}")
    print("→ 한밝님 틱톡 앱 알림함(인박스)에서 초안 확인 후 직접 게시하시면 됩니다.")
    return publish_id


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    cmd = sys.argv[1]
    if cmd == "auth":
        authorize()
    elif cmd == "upload":
        if len(sys.argv) < 3:
            raise SystemExit("사용법: python tiktok_draft_upload.py upload <video.mp4>")
        upload_draft(sys.argv[2])
    else:
        raise SystemExit(__doc__)
