# Threads 성장 자동화 보고 — 2026-09-25

- 실행: 실제 발송
- PAUSED: False
- 오늘 카운트: `{"external": 0, "inbound": 0, "nested": 0, "total": 0, "per_target": {}}`

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
- mentions: `HTTP 500: non-json response`

## 이번 실행

- 발송/초안 대상 없음
