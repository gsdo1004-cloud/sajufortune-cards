# TRIE Threads Intelligence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a recommendation-only Threads intelligence layer that normalizes allowed performance signals, derives reusable content patterns, scores growth/revenue potential deterministically, emits `trie-recommendation-v1` JSON, and records feedback without gaining live publishing authority.

**Architecture:** Add a new `trie` package beside existing Threads/RCE code. TRIE is a pure advisory pipeline: Scout -> Pattern aggregation -> Ranker -> Planner -> Feedback. Existing `threads-growth`, public-saju publishers, queue canary, and RCE remain authoritative for their current responsibilities and are not imported by TRIE's default execution path.

**Tech Stack:** Python 3.11+, standard library (`dataclasses`, `datetime`, `hashlib`, `json`, `pathlib`, `typing`, `unittest`), GitHub Actions. No new runtime dependency in phase 1.

**Spec:** `docs/superpowers/specs/2026-10-06-trie-threads-intelligence-design.md`

## Global Constraints

- Phase 1 is recommendation-only with **zero live publishing allocation**.
- TRIE must not read `THREADS_ACCESS_TOKEN`, `THREADS_USER_ID`, API keys, signing private keys, or any live publisher secret in its default pipeline/canary.
- Do not add browser scraping or browser automation as a fallback.
- Do not persist full copied third-party post text, downloaded creator images/videos, creator-specific imitation prompts, or public-saju commenter personal data.
- Allowed source classes and trust factors are fixed: `owned_official=1.0`, `internal_attribution=0.8`, `public_research=0.6`.
- Growth weights are fixed: interaction `0.20`, conversation `0.35`, amplification `0.25`, view velocity `0.20`.
- Revenue weights are fixed: click `0.30`, conversion `0.45`, revenue efficiency `0.25`.
- Missing signals are excluded and remaining weights are renormalized; no evidence in a score family yields `null`, never fabricated zero.
- Confidence is `min(1.0, sample_size / 10.0) * freshness_weight * source_trust_factor`.
- Planner eligibility defaults: `sample_size >= 3`, `confidence >= 0.25`, at least one score family non-null, and no blocking risk flag.
- Recommendation packets are advisory artifacts, never publication receipts or implicit approval.
- Existing public-saju privacy behavior and existing RCE signed approval/receipt behavior must remain unchanged.
- Existing live publisher files are not modified in phase 1 unless a later separately reviewed adapter is required; this plan does not require one.

## File Structure

- Create `trie/__init__.py` — stable public exports only.
- Create `trie/models.py` — dataclasses, schema validation, deterministic IDs.
- Create `trie/io.py` — strict/atomic JSON I/O.
- Create `trie/scout.py` — source-policy validation and normalization.
- Create `trie/patterns.py` — deterministic feature grouping, freshness, aggregation.
- Create `trie/ranker.py` — deterministic weighted scoring and confidence.
- Create `trie/planner.py` — pure eligibility/ranking/recommendation generation.
- Create `trie/feedback.py` — recommendation outcome attachment with unknown-preserving semantics.
- Create `trie/pipeline.py` — orchestration only; no network or publishing calls.
- Create `trie/canary.py` — CLI wrapper for read-only/dry-run pipeline execution.
- Create `trie_config.json` — fixed phase-1 defaults and blocking risk flags.
- Create `trie_canary_input.json` — synthetic, non-personal, derived-pattern-only fixture.
- Generate `trie_pattern_memory.json` and `trie_recommendations.json` only from explicit pipeline runs.
- Create `test_trie_models.py`, `test_trie_scout.py`, `test_trie_patterns.py`, `test_trie_ranker.py`, `test_trie_planner.py`, `test_trie_feedback.py`, `test_trie_pipeline.py`.
- Create `.github/workflows/trie-canary.yml` — read-only permissions, no Threads secrets, no live flag.
- Do **not** modify `threads_growth.py`, `threads_fortune_public.py`, `rce_pilot_publish.py`, `rce_pilot_insights.py`, or existing Threads workflows in phase 1.

## Review Focus

1. **NaN/Infinity/out-of-range numeric inputs:** validation must reject them instead of serializing unstable scores. Covered in Task 1 tests.
2. **Forbidden PII/creative fields nested inside `features` or metadata:** Scout must fail closed rather than strip-and-continue silently. Covered in Task 2 tests.
3. **Timezone-naive/future timestamps:** normalization must reject naive timestamps and clamp small clock skew only through an explicit `now` supplied by caller; records materially in the future are invalid. Covered in Task 3 tests.
4. **All signals missing after aggregation:** Ranker/Planner must produce no eligible recommendation and must not treat `None` as `0`. Covered in Tasks 4-5 tests.
5. **Corrupt existing memory/output file:** pipeline must fail before writing replacement artifacts; atomic I/O must leave the previous valid file untouched. Covered in Tasks 1 and 7 tests.

---

### Task 1: Core Models, Config, and Atomic JSON I/O

**Files:**
- Create: `trie/__init__.py`
- Create: `trie/models.py`
- Create: `trie/io.py`
- Create: `trie_config.json`
- Test: `test_trie_models.py`

**Interfaces:**
- Produces `SOURCE_TRUST: dict[str, float]` with exact values from the spec.
- Produces `PATTERN_FEATURE_KEYS: tuple[str, ...]` containing: `topic`, `hook_type`, `sentence_shape`, `opening_length_bucket`, `question_style`, `cta_type`, `content_lane`, `format`, `visual_type`, `visual_pattern`, `video_opening_type`, `proof_style`, `offer_style`, `posting_time_bucket`, `engagement_shape`.
- Produces dataclasses `NormalizedRecord`, `PatternAggregate`, `RankedPattern`, `Recommendation`, `FeedbackRecord`.
- Produces `validate_unit_interval(value: float | None, field: str) -> float | None`.
- Produces `deterministic_id(prefix: str, parts: list[str]) -> str` using SHA-256 and a stable uppercase prefix.
- Produces `load_config(path: str | Path = "trie_config.json") -> dict[str, Any]`.
- Produces `read_json(path: str | Path) -> Any` and `atomic_write_json(path: str | Path, value: Any) -> None`.

- [ ] **Step 1: Write failing model/config tests**

Add tests asserting:
- valid scores `0.0`, `0.5`, `1.0`, and `None` are accepted;
- `-0.01`, `1.01`, `NaN`, `Infinity` raise `ValueError`;
- exact source trust factors are `1.0`, `0.8`, `0.6`;
- config contains the exact growth/revenue weights and planner thresholds from the spec;
- identical deterministic-ID inputs produce the same ID and changed input changes the ID;
- `atomic_write_json` followed by `read_json` round-trips UTF-8 Korean text;
- when serializing an invalid/non-JSON value fails, an existing destination remains unchanged.

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m unittest -v test_trie_models.py`
Expected: FAIL because `trie` package/interfaces do not exist.

- [ ] **Step 3: Implement the minimal core types/config/I/O**

Implement the interfaces above. `trie_config.json` must include:
- the exact phase-1 weights;
- `min_sample_size: 3`;
- `min_confidence: 0.25`;
- trust factors;
- configurable blocking risk flags, initially `privacy`, `copied_creative`, `unsupported_source`, `policy_block`;
- freshness buckets used by Task 3: `0-7 days=1.0`, `8-30=0.8`, `31-90=0.6`, `91-180=0.4`, `>180=0.2`.

Use temporary sibling files plus `os.replace()` for atomic writes.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `python -m unittest -v test_trie_models.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add trie/__init__.py trie/models.py trie/io.py trie_config.json test_trie_models.py
git commit -m "feat: add TRIE core models and config"
```

---

### Task 2: Source Policy and Scout Normalization

**Files:**
- Create: `trie/scout.py`
- Test: `test_trie_scout.py`

**Interfaces:**
- Consumes `NormalizedRecord`, `PATTERN_FEATURE_KEYS`, `SOURCE_TRUST` from Task 1.
- Produces `normalize_record(raw: dict[str, Any]) -> NormalizedRecord`.
- Produces `normalize_records(raw_records: list[dict[str, Any]]) -> list[NormalizedRecord]`.

**Accepted raw top-level fields:** `source_type`, `source_ref`, `observed_at`, `lane`, `features`, `signals`, `risk_flags`.

**Accepted signal fields:** `interaction_rate_score`, `conversation_rate_score`, `amplification_rate_score`, `view_velocity_score`, `click_rate_score`, `conversion_rate_score`, `revenue_efficiency_score`.

**Forbidden field names at any nesting depth:** `full_text`, `body`, `raw_post`, `image_bytes`, `video_bytes`, `downloaded_image`, `downloaded_video`, `birth_date`, `birth_time`, `gender`, `personal_question`, `access_token`, `api_key`, `private_key`.

- [ ] **Step 1: Write failing Scout tests**

Add tests asserting:
- all three allowed source classes normalize successfully and retain provenance;
- unsupported source type raises `ValueError` with no fallback behavior;
- only whitelisted pattern keys survive in `features`;
- a forbidden key anywhere in the object raises `ValueError` rather than being silently dropped;
- personal-saju fields are rejected;
- third-party full creative payload fields are rejected;
- every supplied signal is validated as `0.0-1.0` or `None`;
- source trust factor on the normalized record equals the fixed mapping.

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m unittest -v test_trie_scout.py`
Expected: FAIL because `trie.scout` does not exist.

- [ ] **Step 3: Implement Scout**

`normalize_record()` must fail closed. It must not fetch URLs, call Threads, inspect browser state, or import existing publisher modules.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `python -m unittest -v test_trie_scout.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add trie/scout.py test_trie_scout.py
git commit -m "feat: add TRIE source policy scout"
```

---

### Task 3: Deterministic Pattern Aggregation and Freshness

**Files:**
- Create: `trie/patterns.py`
- Test: `test_trie_patterns.py`

**Interfaces:**
- Consumes `NormalizedRecord`, `PatternAggregate`, config freshness buckets.
- Produces `freshness_weight(observed_at: str, now: datetime, config: dict[str, Any]) -> float`.
- Produces `pattern_key(record: NormalizedRecord) -> tuple[str, ...]` using the ordered pattern feature keys plus lane.
- Produces `aggregate_patterns(records: list[NormalizedRecord], *, now: datetime, config: dict[str, Any]) -> list[PatternAggregate]`.

Aggregation rules:
- deterministic ordering by pattern ID;
- `sample_size` is the record count in the aggregate;
- source trust factor is sample-count-weighted mean of record trust factors;
- aggregate `freshness_weight` is the arithmetic mean of per-record freshness weights;
- each signal is the arithmetic mean over records where that signal is known; absent across all records stays `None`;
- risk flags are the sorted union;
- `source_counts` is a deterministic mapping of source type to count.

- [ ] **Step 1: Write failing aggregation tests**

Add tests asserting:
- same records in different input order produce byte-equivalent serialized aggregate data;
- exact freshness buckets: `<=7:1.0`, `<=30:0.8`, `<=90:0.6`, `<=180:0.4`, older `0.2`;
- timezone-naive `observed_at` raises `ValueError`;
- a timestamp more than 5 minutes after supplied `now` raises `ValueError`;
- a timestamp within 5 minutes of future clock skew uses the freshest bucket;
- source trust weighted mean is correct for mixed source types;
- missing signals remain `None` instead of zero;
- no raw source creative content appears in aggregate serialization.

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m unittest -v test_trie_patterns.py`
Expected: FAIL because aggregation functions do not exist.

- [ ] **Step 3: Implement deterministic aggregation**

Use only normalized inputs. `pattern_id` must be derived from canonical feature values via Task 1 `deterministic_id("TRIEPAT", ...)`.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `python -m unittest -v test_trie_patterns.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add trie/patterns.py test_trie_patterns.py
git commit -m "feat: aggregate TRIE content patterns"
```

---

### Task 4: Deterministic Growth/Revenue Ranker

**Files:**
- Create: `trie/ranker.py`
- Test: `test_trie_ranker.py`

**Interfaces:**
- Consumes `PatternAggregate`, `RankedPattern`, `trie_config.json`.
- Produces `weighted_available_mean(signals: dict[str, float | None], weights: dict[str, float]) -> float | None`.
- Produces `rank_pattern(pattern: PatternAggregate, config: dict[str, Any]) -> RankedPattern`.
- Produces `rank_patterns(patterns: list[PatternAggregate], config: dict[str, Any]) -> list[RankedPattern]`.

- [ ] **Step 1: Write failing ranker tests**

Add tests asserting:
- growth score uses exact weights `0.20/0.35/0.25/0.20`;
- revenue score uses exact weights `0.30/0.45/0.25`;
- if one signal is missing, remaining weights are renormalized rather than treating the signal as zero;
- if every growth signal is missing, `growth_score is None`;
- if every revenue signal is missing, `revenue_score is None`;
- confidence exactly follows `min(1, sample/10) * freshness * trust`;
- confidence never exceeds `1.0`;
- a pattern with no evidence in either family is retained as a ranked object but remains ineligible for Task 5;
- output order is deterministic.

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m unittest -v test_trie_ranker.py`
Expected: FAIL because `trie.ranker` does not exist.

- [ ] **Step 3: Implement ranker**

Do not use an LLM, random numbers, network state, or current wall clock inside ranking functions.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `python -m unittest -v test_trie_ranker.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add trie/ranker.py test_trie_ranker.py
git commit -m "feat: add deterministic TRIE ranker"
```

---

### Task 5: Pure Planner and Recommendation Schema

**Files:**
- Create: `trie/planner.py`
- Test: `test_trie_planner.py`

**Interfaces:**
- Consumes `RankedPattern`, `Recommendation`, planner thresholds from config.
- Produces `is_eligible(pattern: RankedPattern, config: dict[str, Any]) -> tuple[bool, str]`.
- Produces `plan_recommendations(patterns: list[RankedPattern], *, generated_at: datetime, config: dict[str, Any], objective: str = "balanced", limit: int = 10) -> list[Recommendation]`.

Objective ordering:
- `growth`: non-null `growth_score` descending, then confidence, then pattern ID;
- `revenue`: non-null `revenue_score` descending, then confidence, then pattern ID;
- `balanced`: arithmetic mean of available growth/revenue scores, then confidence, then pattern ID. A missing family is excluded from the mean, not treated as zero.

Recommendation mapping:
- `lane <- content_lane/lane`;
- `topic <- topic`;
- `hook_pattern <- hook_type`;
- `format <- format`;
- `visual_pattern <- visual_pattern` falling back to `visual_type`;
- `cta <- cta_type`;
- `canary = true` means advisory canary eligibility only;
- `source_policy = "derived_patterns_only"`;
- recommendation ID is deterministic for `(pattern_id, generated_at ISO date-time, objective)`.

- [ ] **Step 1: Write failing planner tests**

Add tests asserting:
- `sample_size=2` is rejected even with high scores;
- `confidence=0.24` is rejected;
- all scores `None` is rejected;
- any configured blocking risk flag is rejected;
- empty input returns an empty list with no exception;
- eligible pattern maps to exact `trie-recommendation-v1` fields;
- unknown revenue remains JSON `null`;
- `canary=true` is present but no publish/receipt/approval fields exist;
- objective sort rules are deterministic;
- invalid objective raises `ValueError`.

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m unittest -v test_trie_planner.py`
Expected: FAIL because `trie.planner` does not exist.

- [ ] **Step 3: Implement planner**

Planner must be a pure function. It must not write files, read environment secrets, or import publishing modules.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `python -m unittest -v test_trie_planner.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add trie/planner.py test_trie_planner.py
git commit -m "feat: add TRIE recommendation planner"
```

---

### Task 6: Feedback Attachment Without Invented Metrics

**Files:**
- Create: `trie/feedback.py`
- Test: `test_trie_feedback.py`

**Interfaces:**
- Consumes `Recommendation`, `FeedbackRecord`.
- Produces `normalize_feedback(raw: dict[str, Any]) -> FeedbackRecord`.
- Produces `attach_feedback(recommendations: list[Recommendation], feedback: list[FeedbackRecord]) -> list[dict[str, Any]]`.

Feedback schema fields:
- required: `recommendation_id`, `status`, `observed_at`;
- optional mapping: `post_id`, `views`, `likes`, `replies`, `reposts`, `quotes`, `shares`, `clicks`, `conversions`, `revenue`, `error_code`;
- absent metrics stay `None`/omitted according to serialized schema, never coerced to zero;
- `status` allowed values: `published`, `rejected`, `metrics_incomplete`, `complete`.

- [ ] **Step 1: Write failing feedback tests**

Add tests asserting:
- feedback attaches only to an existing recommendation ID;
- unknown recommendation ID raises `ValueError`;
- missing metrics remain unknown, not `0`;
- explicit metric value `0` remains a real zero and is distinguishable from unknown;
- negative counts/revenue raise `ValueError`;
- rejected publication can carry `error_code` without fake performance metrics;
- attaching feedback does not create any publish command, URL call, approval, or receipt field.

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m unittest -v test_trie_feedback.py`
Expected: FAIL because `trie.feedback` does not exist.

- [ ] **Step 3: Implement feedback normalization/attachment**

Keep this read/transform only. No official Threads API call is part of phase 1; existing RCE insight collection remains untouched.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `python -m unittest -v test_trie_feedback.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add trie/feedback.py test_trie_feedback.py
git commit -m "feat: attach TRIE performance feedback"
```

---

### Task 7: Read-Only Pipeline, Synthetic Canary, and Failure Isolation

**Files:**
- Create: `trie/pipeline.py`
- Create: `trie/canary.py`
- Create: `trie_canary_input.json`
- Create: `test_trie_pipeline.py`
- Create: `.github/workflows/trie-canary.yml`

**Interfaces:**
- Consumes all Tasks 1-6.
- Produces `run_pipeline(raw_records: list[dict[str, Any]], *, now: datetime, config: dict[str, Any], objective: str = "balanced", limit: int = 10) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]` returning serialized pattern memory and recommendations.
- Produces CLI: `python -m trie.canary --input <path> --config <path> --memory-out <path> --recommendations-out <path> [--objective balanced]`.

Pipeline rules:
- normalize all inputs before writing anything;
- aggregate/rank/plan completely in memory;
- if any input/state error occurs, exit non-zero and write no replacement output;
- write memory first to a temp file, recommendations second to a temp file, then replace destinations only after both payloads serialize successfully;
- never import or invoke Threads publisher code;
- synthetic canary input contains only derived features/signals and no user-level data.

Workflow rules:
- `permissions: contents: read`;
- Python `3.11`;
- no `secrets.*` references;
- no `THREADS_ACCESS_TOKEN`, `THREADS_USER_ID`, `THREADS_QUEUE_LIVE`, `--live`, `threads_publish`, or browser tool invocation;
- scheduled once daily at `47 14 * * *` (23:47 KST) plus `workflow_dispatch`;
- run all TRIE unit tests;
- run the synthetic canary into `/tmp/trie_pattern_memory.json` and `/tmp/trie_recommendations.json` so scheduled validation never commits generated state;
- assert output schemas and that the pipeline performed zero external calls by construction.

- [ ] **Step 1: Write failing pipeline/safety tests**

Add tests asserting:
- synthetic input produces deterministic memory and at least one eligible recommendation;
- running twice with the same `now` produces identical JSON data;
- corrupt JSON input causes non-zero CLI exit and leaves pre-existing output files byte-for-byte unchanged;
- invalid record in a batch prevents partial output;
- workflow text contains none of the forbidden secret/live/publish strings;
- workflow permissions are read-only;
- pipeline source does not import `requests`, `threads_growth`, `threads_fortune_public`, `rce_pilot_publish`, or a browser package.

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m unittest -v test_trie_pipeline.py`
Expected: FAIL because pipeline/canary/workflow do not exist.

- [ ] **Step 3: Implement pipeline and canary workflow**

Keep generated repository files out of the scheduled canary path; `/tmp` outputs are sufficient for CI validation. Repository-level `trie_pattern_memory.json` and `trie_recommendations.json` are created only when an explicit operator or future downstream integration requests them.

- [ ] **Step 4: Run all TRIE tests and verify GREEN**

Run:

```bash
python -m unittest -v \
  test_trie_models.py \
  test_trie_scout.py \
  test_trie_patterns.py \
  test_trie_ranker.py \
  test_trie_planner.py \
  test_trie_feedback.py \
  test_trie_pipeline.py
```

Expected: PASS.

- [ ] **Step 5: Run existing Threads regression tests**

Run:

```bash
python -m unittest -v test_threads_growth.py test_threads_fortune_public.py
```

Expected: PASS unchanged.

If `pytest` is already available in the implementation environment, also run the existing queue/shadow suite used by `threads-queue-canary.yml`:

```bash
python -m pytest -q \
  test_threads_publish_queue.py \
  test_threads_publisher_adapter.py \
  test_threads_queue_watchdog.py \
  test_threads_queue_shadow.py
```

Expected: PASS unchanged.

- [ ] **Step 6: Verify no live publisher/RCE files changed**

Run:

```bash
git diff --name-only HEAD~1..HEAD
```

and confirm phase-1 changes do not include `threads_growth.py`, `threads_fortune_public.py`, `rce_pilot_publish.py`, `rce_pilot_insights.py`, `.github/workflows/threads-growth.yml`, `.github/workflows/threads-public-saju.yml`, `.github/workflows/rce-pilot-publish.yml`, or `.github/workflows/rce-pilot-insights.yml`.

- [ ] **Step 7: Commit**

```bash
git add trie/pipeline.py trie/canary.py trie_canary_input.json test_trie_pipeline.py .github/workflows/trie-canary.yml
git commit -m "feat: add TRIE read-only canary pipeline"
```

---

### Task 8: Final Verification and Phase-1 Operator Notes

**Files:**
- Create: `TRIE_PHASE1.md`
- Modify only if needed to export stable package symbols: `trie/__init__.py`

**Interfaces:**
- Documents the explicit advisory command, artifact meanings, failure behavior, and the fact that `canary=true` is not publish authorization.

- [ ] **Step 1: Write operator notes**

Document:
- how to run the synthetic canary;
- how to run against an explicit sanitized input file;
- output schema names;
- that outputs have no publishing authority;
- prohibited source data;
- rollback: disable `.github/workflows/trie-canary.yml` and remove downstream readers only;
- live 30/70 allocation is deferred to a separately reviewed phase.

- [ ] **Step 2: Run complete verification**

Run:

```bash
python -m unittest -v \
  test_trie_models.py \
  test_trie_scout.py \
  test_trie_patterns.py \
  test_trie_ranker.py \
  test_trie_planner.py \
  test_trie_feedback.py \
  test_trie_pipeline.py \
  test_threads_growth.py \
  test_threads_fortune_public.py
python -m trie.canary \
  --input trie_canary_input.json \
  --config trie_config.json \
  --memory-out /tmp/trie-pattern-memory.json \
  --recommendations-out /tmp/trie-recommendations.json
```

Expected: all tests PASS; canary exits 0; output is recommendation-only.

- [ ] **Step 3: Inspect generated artifacts**

Confirm:
- `schema` values are versioned;
- no secret/PII/third-party raw creative fields are present;
- missing revenue evidence appears as JSON `null` where applicable;
- recommendations carry `source_policy: derived_patterns_only`;
- no artifact contains `approval_id`, signature, receipt, or publish command semantics.

- [ ] **Step 4: Commit**

```bash
git add TRIE_PHASE1.md trie/__init__.py
git commit -m "docs: add TRIE phase 1 operator guide"
```

## Self-Review Results

- **Spec coverage:** Scout, derived-only storage, deterministic aggregation, exact rank weights, nullable evidence, confidence, planner thresholds, feedback, canary safety, rollback, and existing-system isolation are all mapped to tasks.
- **Scope:** No live publisher adapter, RCE refactor, browser research, vector DB, adaptive traffic allocation, or 30/70 live rollout is included.
- **Type consistency:** Task flow is `NormalizedRecord -> PatternAggregate -> RankedPattern -> Recommendation -> FeedbackRecord`; later tasks consume only interfaces defined earlier.
- **Failure isolation:** validation and full in-memory pipeline completion happen before atomic output replacement; existing publisher paths are not invoked.
- **Review-focus coverage:** all five identified failure classes have explicit tests in the owning task.
