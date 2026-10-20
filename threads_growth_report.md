# Threads 성장 자동화 보고 — 2026-10-21

- 실행: 실제 발송
- PAUSED: False
- 오늘 카운트: `{"external": 0, "inbound": 2, "nested": 0, "total": 2, "per_target": {}, "external_measured": 0, "external_engaged": 0, "external_replies": 0, "external_likes": 0, "external_errors": 0, "external_safety_stops": 0, "external_insight_failures": 0}`
- 외부 대화 단계: `{"stage_index": 0, "daily_cap": 8, "promoted": false, "stage_started_kst": "2026-10-11", "sent": 0, "measured": 0, "engaged": 0, "errors": 0, "safety_stops": 0, "insight_failures": 0, "engagement_rate": 0.0, "error_rate": 0.0, "insight_failure_rate": 0.0, "telemetry_available": true, "unresolved": 0}`
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

- inbound @heya_0712: 정확하게 보려면 성별(남/여)만 알려주세요. 이미 적어주신 생년정보는 답글에 다시 쓰지 않을게요. (sent)
- inbound @shabet_yj: 양띠 직장 흐름은 오늘은 무진일, 오늘 기운과 같은 흙의 흐름을 나란히 타는 무난한 날 — 하던 일을 꾸준히. (sent)
