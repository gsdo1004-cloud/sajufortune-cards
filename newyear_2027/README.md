# newyear_2027

Isolated derivative lane for the approved 60-post 2027 Naver series.

- `content.json`: deterministic prebuilt Threads/Shorts copy and immutable content IDs.
- `assets/`: one approved source visual per content item.
- `rendered/`: runtime-only Shorts output (not a source of publication identity).
- `receipts/YYYY-MM-DD/{threads,youtube}.json`: two-phase `PUBLISHING` → `PUBLISHED` idempotency records.

This lane never calls the existing daily zodiac pipeline and never changes the Naver source packages. A local dispatcher must first confirm the source package readiness and its RSS-confirmed `naver_publish.json` before triggering any remote fanout.
