# Threads 성장 자동화 보고 — 2026-10-02

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
- mentions: `THApiException code=10 subcode=None: Application does not have permission for this action`

## 이번 실행

- external @gsdo10042026: 띠별 운세는 큰 흐름을 보기 좋지요. 혹시 오늘 일진에서 띠(년지)와 일간이 서로 부딪히는 날은 어느 쪽을 더 비중 있게 보시는 편인가요? (dry)
