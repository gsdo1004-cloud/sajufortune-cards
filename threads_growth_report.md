# Threads 성장 자동화 보고 — 2026-10-20

- 실행: 실제 발송
- PAUSED: False
- 오늘 카운트: `{"external": 0, "inbound": 5, "nested": 3, "total": 8, "per_target": {}, "external_measured": 0, "external_engaged": 0, "external_replies": 0, "external_likes": 0, "external_errors": 0, "external_safety_stops": 0, "external_insight_failures": 0}`
- 외부 대화 단계: `{"stage_index": 0, "daily_cap": 8, "promoted": false}`
- 외부 댓글 성과측정: `{"attempted": 0, "measured": 0, "failed": 0, "skipped": 0}`

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

- nested @98o2o9: 현재 연애 중이시라면 지금 만나는 분과의 궁합이나 연애 흐름을 집중적으로 봐드릴 수 있어요. 사주 정보와 함께 연애 고민을 자세히 남겨주세요. (sent)
- nested @jang_e_un80: 감사합니다. 재물운을 보려면 게시글에 적힌 필수 정보가 필요하니, 정보와 함께 댓글 남겨주시면 자세히 봐드릴게요! (sent)
