# TRIE Threads Intelligence Design

## Status
Approved architecture baseline for implementation planning.

## Goal
Add a Threads-specific intelligence layer that discovers high-performing patterns, turns them into reusable abstract features, ranks content opportunities for growth and revenue, and emits recommendations to existing publishing systems without owning live publishing credentials or replacing current Threads workflows.

## Why this exists
The repository already has three separate operational responsibilities:

1. `threads-growth.py` and `.github/workflows/threads-growth.yml` handle official-API growth activity such as inbound/outbound reply loops and safety gates.
2. RCE pilot files such as `rce_pilot_publish.py`, `rce_pilot_insights.py`, and their workflows handle tightly controlled revenue-oriented pilot publication, signed approval, receipts, and insight collection.
3. `threads-queue-canary.yml` and `THREADS_QUEUE_CANARY.md` provide a deliberately non-publishing canary path with no Threads secrets and no live flag.

TRIE must not duplicate or collapse those boundaries. Its role is intelligence and recommendation only.

## Non-goals
TRIE will not:

- own or read Threads publishing secrets in its default scout/miner/ranker workflow;
- publish posts directly;
- replace `threads-growth.py`;
- replace RCE approval/signature/receipt logic;
- scrape private data or bypass official API capability gates;
- copy another creator's full post, image, video, or distinctive creative expression into the local corpus;
- add browser automation as a fallback for unavailable Threads API capabilities;
- restructure unrelated AutoBrain workflows.

## Architecture

```text
High-performance public/owned signals
        |
        v
+--------------------+
| TRIE Scout         |
| source normalization|
+--------------------+
        |
        v
+--------------------+
| Pattern Miner      |
| abstract features  |
+--------------------+
        |
        v
+--------------------+
| Ranker             |
| growth/revenue/conf|
+--------------------+
        |
        v
+--------------------+
| Pattern Memory     |
| versioned JSON     |
+--------------------+
        |
        v
+--------------------+
| Planner            |
| recommendation JSON|
+--------------------+
        |
        +----------------------+----------------------+
        |                      |                      |
        v                      v                      v
existing fortune flow   shopping/content flow      existing RCE
        |                      |                      |
        +----------------------+----------------------+
                               |
                               v
                    existing Threads publishers
                               |
                               v
                   official insights/click/revenue
                               |
                               v
                       TRIE feedback update
```

## Component boundaries

### 1. Scout
Responsibility: ingest only allowed source records and normalize them into a common schema.

Initial supported source classes:

- `owned_official`: owned Threads performance records from official insight data;
- `internal_attribution`: internal content metadata and click/conversion attribution records;
- `public_research`: manually supplied public research records containing metadata or short analytical excerpts, never copied full creative assets.

Every normalized record must contain `source_type`, `source_ref`, `observed_at`, `lane`, and `metrics`. The Scout must preserve provenance and reject records that do not meet source policy.

Source trust factors are fixed for phase 1:

- `owned_official`: `1.0`;
- `internal_attribution`: `0.8`;
- `public_research`: `0.6`.

### 2. Pattern Miner
Responsibility: convert normalized source records into abstract reusable features.

Allowed pattern features include:

- `hook_type`;
- `sentence_shape`;
- `opening_length_bucket`;
- `question_style`;
- `cta_type`;
- `content_lane`;
- `visual_type`;
- `video_opening_type`;
- `proof_style`;
- `offer_style`;
- `posting_time_bucket`;
- `engagement_shape`.

The miner stores derived patterns, not source creative payloads. Full copied body text, downloaded creator images, downloaded creator video, and creator-specific imitation instructions are out of scope.

For deterministic phase-1 ranking, each aggregated pattern may carry normalized 0.0-1.0 signal fields when evidence exists:

Growth signals:

- `interaction_rate_score`;
- `conversation_rate_score`;
- `amplification_rate_score`;
- `view_velocity_score`.

Revenue signals:

- `click_rate_score`;
- `conversion_rate_score`;
- `revenue_efficiency_score`.

Signal normalization is performed before ranking and must be deterministic for the same corpus/configuration.

### 3. Ranker
Responsibility: score candidate patterns separately for growth and revenue.

Phase-1 default growth weights:

- interaction rate: `0.20`;
- conversation rate: `0.35`;
- amplification rate: `0.25`;
- view velocity: `0.20`.

Phase-1 default revenue weights:

- click rate: `0.30`;
- conversion rate: `0.45`;
- revenue efficiency: `0.25`.

A score is the weighted mean of available normalized signals. Missing signals are excluded and remaining weights are renormalized. If no signal in a score family exists, that score is `null`, not zero.

Required rank output dimensions:

- `growth_score`: `0.0-1.0` or `null` when no growth evidence exists;
- `revenue_score`: `0.0-1.0` or `null` when no revenue evidence exists;
- `confidence`: `0.0-1.0`;
- `sample_size`;
- `freshness_weight`;
- `risk_flags`.

Phase-1 confidence is deterministic:

```text
sample_factor = min(1.0, sample_size / 10.0)
confidence = sample_factor * freshness_weight * source_trust_factor
```

`freshness_weight` must be a normalized `0.0-1.0` value derived by the normalization layer. For an aggregate with multiple source types, `source_trust_factor` is the sample-count-weighted mean of the fixed source trust factors above.

LLM-generated hidden scores are not authoritative. Model assistance may later enrich features, but final ranking inputs, weights, and outputs must remain serializable and testable.

### 4. Pattern Memory
Responsibility: store versioned aggregated pattern records and their observed outcomes.

The first implementation uses repository JSON files, not a new database.

Required properties:

- deterministic identifiers;
- schema versioning;
- source-count aggregation;
- recency timestamps;
- no authentication secrets;
- no personal birth data from public-saju commenters;
- no raw copied third-party creative assets.

### 5. Planner
Responsibility: produce recommendation packets for existing downstream systems.

Canonical recommendation schema:

```json
{
  "schema": "trie-recommendation-v1",
  "recommendation_id": "TRIE-...",
  "generated_at": "2026-10-06T00:00:00+09:00",
  "lane": "fortune_engagement",
  "topic": "재물운",
  "hook_pattern": "unexpected_prediction",
  "format": "text_image",
  "visual_pattern": "single_focus_card",
  "cta": "comment",
  "growth_score": 0.82,
  "revenue_score": null,
  "confidence": 0.72,
  "sample_size": 12,
  "canary": true,
  "source_policy": "derived_patterns_only"
}
```

`growth_score` or `revenue_score` may be `null` only when the corresponding evidence family is absent. The planner must not convert unknown evidence into `0.0`.

The planner is a pure function from pattern-memory data plus planning constraints to recommendation objects.

Phase-1 eligibility defaults:

- `sample_size >= 3`;
- `confidence >= 0.25`;
- at least one of `growth_score` or `revenue_score` is non-null;
- no blocking `risk_flags`.

### 6. Feedback updater
Responsibility: attach observed outcomes back to recommendation IDs without republishing anything.

Initial feedback inputs:

- official Threads post insights when a downstream publisher maps `recommendation_id` to `post_id`;
- site click/conversion attribution when a compatible internal record exists;
- explicit failure states such as publish rejection or missing metrics.

Feedback collection must fail closed: missing metrics produce an incomplete outcome record, not invented zeros treated as real performance.

## Existing systems integration

### `threads-growth`
TRIE may provide topic or response-priority recommendations in the future, but phase 1 does not modify reply execution. The current official-API capability gates remain authoritative.

### Fortune publishing
Phase 1 integration is advisory. Existing fortune content generators may consume a recommendation JSON file. They remain responsible for copy generation, platform checks, and live publication.

The existing public-saju schedule and privacy behavior remain unchanged. TRIE must not place commenter birth information into pattern memory.

### Shopping/content automation
TRIE may emit `shopping_revenue` recommendations with hook/format/CTA patterns. Existing shopping short-form and product pipelines remain responsible for product eligibility, copy, disclosure, media generation, and publishing.

### RCE
RCE remains the controlled publication path for revenue pilots that need explicit approval/signature/receipt semantics. TRIE can propose an RCE candidate, but it cannot generate a valid publish approval by itself.

The current pilot insight collector is hard-coded to a specific pilot. Phase 1 may extract a reusable, read-only Threads insights client, but the existing RCE pilot behavior must remain backward-compatible.

### Queue canary
The existing non-publishing queue canary remains non-publishing. TRIE gets its own dry-run/canary validation and must not silently add Threads secrets, `--live`, or equivalent publication authority to the existing canary workflow.

## Canary policy
Phase 1 is recommendation-only and has zero live publishing allocation.

A recommendation packet may include `"canary": true`, but that means only "eligible for downstream canary selection"; it is not permission to publish.

A future separately reviewed live-integration phase may start with:

- 30% TRIE-recommended candidates;
- 70% existing strategy/control.

Promotion beyond 30% requires another reviewed change. No automatic promotion based on a single high-performing post is allowed.

## Data and privacy rules

1. Do not store Threads access tokens, user IDs used as secrets, API keys, or signing private keys in TRIE output files.
2. Do not store public-saju commenter birth date/time, gender, free-text personal questions, or other user-level consultation data in TRIE pattern memory.
3. Do not download and retain third-party images/videos for training or cloning.
4. Store only aggregate or derived pattern features needed to rank content strategy.
5. Preserve source provenance so low-trust sources can be excluded later.
6. Recommendation files are not publication receipts and must never be interpreted as proof of publication.

## Error handling

- Invalid input schema: reject record and report a validation error.
- Unsupported source type: reject without fallback scraping.
- Empty corpus: return no recommendation with explicit reason.
- Insufficient sample size: mark ineligible rather than manufacture certainty.
- Missing revenue attribution: keep revenue evidence unknown, not zero.
- Missing official Threads metrics: mark feedback incomplete.
- Corrupt pattern-memory JSON: fail the TRIE job without invoking downstream publishers.
- Downstream consumer unavailable: keep the recommendation artifact; do not publish through an alternate channel automatically.

## Files planned for phase 1

New focused files are preferred over enlarging existing publishers:

- `trie/__init__.py` — public package surface;
- `trie/models.py` — typed record/recommendation structures and validation helpers;
- `trie/scout.py` — normalization and source-policy checks;
- `trie/patterns.py` — derived feature extraction/aggregation;
- `trie/ranker.py` — deterministic scoring;
- `trie/planner.py` — recommendation generation;
- `trie/feedback.py` — outcome attachment and confidence updates;
- `trie/io.py` — atomic JSON read/write helpers;
- `trie_config.json` — weights, lane thresholds, sample-size rules;
- `trie_pattern_memory.json` — generated aggregate state;
- `trie_recommendations.json` — generated advisory output;
- `test_trie_models.py`;
- `test_trie_scout.py`;
- `test_trie_ranker.py`;
- `test_trie_planner.py`;
- `test_trie_feedback.py`;
- `.github/workflows/trie-canary.yml` — no publishing secrets, dry-run only.

Potential compatibility extraction, only if required by tests:

- a reusable read-only Threads insights helper extracted from `rce_pilot_insights.py`, while preserving current RCE CLI behavior.

No phase-1 changes are planned to live publisher code unless a small adapter is required for reading `trie_recommendations.json`; any such change must remain opt-in and default off.

## Testing strategy

Implementation follows TDD.

Minimum behavior coverage:

1. schema validation accepts valid nullable scores and rejects scores outside `0.0-1.0`;
2. source policy rejects raw third-party creative payload storage;
3. source trust factors are exactly `1.0`, `0.8`, and `0.6` for the three phase-1 source classes;
4. pattern extraction/normalization is deterministic for the same input and config;
5. ranker applies exact default weights and renormalizes around missing signals;
6. no evidence yields `null`, never fabricated zero;
7. low sample size lowers confidence and `sample_size < 3` is ineligible;
8. planner emits no recommendation from an empty or ineligible corpus;
9. feedback preserves unknown metrics as unknown;
10. no TRIE dry-run workflow exposes Threads publishing secrets or live flags;
11. corrupt state fails without touching publisher paths;
12. RCE pilot tests continue to pass if insight-helper extraction occurs.

## Success criteria

Phase 1 is complete when:

- TRIE can ingest allowed historical/internal performance records;
- it stores only derived/aggregate pattern information;
- it produces deterministic `trie-recommendation-v1` JSON;
- output contains separate growth, revenue, and confidence fields with unknown evidence represented as `null`;
- feedback can update recommendation outcomes without publishing;
- all new unit tests pass;
- existing Threads growth/public-saju/RCE tests pass unchanged;
- `trie-canary.yml` runs without Threads publication secrets or live flags;
- disabling or deleting TRIE artifacts does not stop existing Threads workflows.

## Rollback

Rollback is file-level and low-risk because TRIE is advisory by default:

1. disable/remove `.github/workflows/trie-canary.yml`;
2. stop downstream readers of `trie_recommendations.json` if any were enabled;
3. leave existing `threads-growth`, public-saju, queue-canary, and RCE workflows unchanged;
4. retain historical TRIE JSON only if useful for audit, otherwise remove generated artifacts.

## Future phases explicitly deferred

The following are not part of phase 1:

- automated live publishing directly from TRIE;
- 30/70 live traffic allocation itself;
- adaptive multi-armed-bandit traffic allocation;
- vector database or external database introduction;
- automatic browser research/scraping fallback;
- creator-style imitation models;
- autonomous campaign budget changes;
- global cross-platform replacement of AutoBrain planners.
