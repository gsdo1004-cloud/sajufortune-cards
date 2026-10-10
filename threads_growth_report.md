# Threads 성장 자동화 보고 — 2026-10-11

- 실행: 실제 발송
- PAUSED: False
- 오늘 카운트: `{"external": 0, "inbound": 0, "nested": 1, "total": 1, "per_target": {}}`

## API 기능

- basic: ✅
- read_replies: ✅
- profile_posts: ❌
- keyword_search: ✅
- mentions: ❌
- token scopes: `threads_basic, threads_content_publish, threads_delete, threads_keyword_search, threads_manage_insights, threads_manage_replies, threads_profile_discovery, threads_read_replies`
- 추가 권장 scope: `threads_manage_mentions`

## 미지원/권한 오류

- profile_posts: `OAuthException code=10 subcode=4279067: Application does not have permission for this action`
- mentions: `THApiException code=10 subcode=None: Application does not have permission for this action`

## 이번 실행

- nested @sajangflow: 일 년에 한 번이면 딱 적당하지! 보통 신년 운세 볼 때 많이 찾아보나 봐? (sent)
