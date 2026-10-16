# 2027 New-Year Fortune Fanout Spec

## Goal
Preserve every existing today-fortune and Naver publication job unchanged while adding one independent daily lane that republishes the already-approved 60 Naver 2027 fortune packages as Threads-native posts and YouTube Shorts.

## Binding safety requirements
- Never modify or invoke the existing today-fortune pipeline, its task definitions, locks, receipts, or concurrency groups.
- The new lane must use only a 2027 package whose `meta.publish_date` matches KST today, whose source package passes the existing read-only readiness checks, and whose `naver_publish.json` is definitively `success=true`, `status=PUBLISHED`, `rss_seen=true`, with a non-empty URL and category `2027 신년운세`.
- Missing, corrupt, PUBLISHING, VERIFY_FAILED, conflicting, stale, or ambiguous source state must HOLD only the new lane.
- Use a `newyear_2027` namespace for content, assets, render output, locks, status, workflow concurrency, and platform receipts.
- New lock ownership is exclusive and only the process that created the lock may remove it.
- A stable `content_id + platform + account` identifies a publication. Article/output hashes are audit fields and must never create a second publication key.
- Use a two-phase platform receipt: `PUBLISHING` is persisted before the remote side effect; `PUBLISHED` with the remote ID is persisted afterward. An unresolved `PUBLISHING` state blocks automatic reposting.
- Threads and YouTube failures are isolated. One platform succeeding must not make the other platform rerun or prevent the existing daily pipelines from running.
- Daily runtime must not depend on an LLM. All 60 Threads texts and Shorts scripts are generated and quality-checked ahead of time from the already-approved source packages.
- Threads copy must be native: first two lines hook/result + curiosity, one problem/one answer, comment/save CTA, <= 500 characters.
- Shorts scripts must be materially distinct across a six-format rotation, grounded in the source's 2027/명리 basis, and render to 25–40 seconds.
- Normal YouTube upload reuses the existing channel-locking uploader for `운명과학TV`; canary must support true private upload with no `publishAt`.
- New daily schedule runs after the 10:30 Naver job and finishes before the existing 19:00/20:00 evening automation. Target local dispatch is 12:20 KST, Threads immediately after dispatch, YouTube public reservation at 13:00 KST, with no automatic catch-up after 14:00.
- No new paid dependency. Prefer existing Supertonic local TTS, then Edge fallback.

## Canary and rollout
1. Offline bundle/render/idempotency tests.
2. One true-private YouTube canary without `publishAt`.
3. One Threads canary and remote ID/body/account verification.
4. Verify re-run is a no-op and existing scheduled task definitions are unchanged.
5. Enable the independent daily local dispatcher only after those checks pass.

## GPT-6 Astra review basis
A read-only GPT-6 Astra review returned HOLD for immediate full live, but approved the separated architecture once the source receipt gate, owner-safe lock, two-phase idempotency, platform failure isolation, mocked regression tests, and one-item canary are satisfied.
