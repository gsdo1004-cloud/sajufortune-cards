# TRIE Phase 1 Operator Guide

TRIE Phase 1 is a **recommendation-only** Threads intelligence layer. It does not publish content, hold publishing credentials, create approvals, or replace existing Threads growth/public-saju/RCE workflows.

## Synthetic canary

Run the built-in derived-data-only fixture:

```bash
python3 -m trie.canary \
  --input trie_canary_input.json \
  --config trie_config.json \
  --memory-out /tmp/trie-pattern-memory.json \
  --recommendations-out /tmp/trie-recommendations.json
```

The synthetic fixture uses `observed_at: "$NOW"` only on `synthetic:` source references. Production/sanitized records must use real timezone-aware ISO-8601 timestamps.

## Sanitized input

Provide a JSON array whose records contain only the allowed source/provenance fields, derived pattern features, normalized signals, and risk flags. Example source classes are `owned_official`, `internal_attribution`, and `public_research`.

```bash
python3 -m trie.canary \
  --input /path/to/sanitized-records.json \
  --config trie_config.json \
  --memory-out /tmp/trie-pattern-memory.json \
  --recommendations-out /tmp/trie-recommendations.json
```

## Output meanings

- Pattern memory records use schema `trie-pattern-memory-v1`.
- Recommendation records use schema `trie-recommendation-v1`.
- `growth_score` and `revenue_score` are independent. Missing evidence remains JSON `null`; it is never fabricated as zero.
- `confidence` is deterministic from sample size, freshness, and source trust.
- `canary: true` means only **eligible for downstream canary selection**. It is not permission to publish.
- `source_policy: derived_patterns_only` confirms the recommendation came from derived/aggregate strategy features.

TRIE outputs are not publication receipts and carry no signature, approval, publish command, or live authority.

## Prohibited source data

Do not provide or persist:

- full copied third-party post bodies;
- downloaded creator images or videos;
- creator-specific imitation instructions;
- public-saju commenter birth date/time, gender, or personal questions;
- access tokens, API keys, signing private keys, or publisher secrets.

Scout validation fails closed when prohibited field names are found, including nested fields.

## Failure behavior

The pipeline validates and computes in memory before replacing output files. Invalid/corrupt input exits non-zero. Existing output files are not replaced when input parsing or record validation fails. No alternate browser or publisher fallback is attempted.

## CI canary

`.github/workflows/trie-canary.yml` runs once daily at 23:47 KST and on manual dispatch. It has read-only repository permissions, receives no publishing credentials, runs all TRIE unit tests, and writes generated validation artifacts only under `/tmp`.

## Rollback

1. Disable/remove `.github/workflows/trie-canary.yml`.
2. Remove any future downstream reader of TRIE recommendation artifacts.
3. Leave existing `threads-growth`, public-saju, queue-canary, and RCE workflows unchanged.

Because Phase 1 is advisory only, disabling TRIE does not stop existing Threads publishing or reply workflows.

## Deferred live rollout

A future live-integration phase may evaluate a 30% TRIE-recommended / 70% existing-strategy control allocation. That allocation is **not implemented in Phase 1** and requires a separate reviewed change before any live use.
