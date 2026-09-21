# Threads Queue Canary

This workflow is intentionally non-publishing.

- Schedule: 11:37 UTC (20:37 KST), separated from the existing zodiac publish at 12:10 UTC.
- No Threads token or user-id secret is exposed to the job.
- No --live flag is present.
- THREADS_QUEUE_LIVE is explicitly empty.
- Existing threads-zodiac-evening.yml remains the only zodiac publishing schedule.
- Promotion to live requires a separate reviewed change; do not silently add live flags/secrets here.
