# PR #25 — offline continuation QA (2026-11-23 KST)

**Release status: HOLD. This is a Draft PR; do not merge, deploy, publish or use paid image APIs.**

## Commit split
- Previous baseline SHA: a9842fce4418db083b1313ea9a5896fd68837aac
- Changes in the next commit apply to FLUX safety, CI dependencies, mobile summary/zoom and optional fail-closed Hanbok avatar requirement.
- Original STYLE_06 source manifest remains PENDING_QA, SHA-256 5cdcbc5117c3621d5684ebe917ae7b50e8a1db7e6b72caff25dcf565c3afa372.
- Real image/media QA artifacts stay on an isolated workstation; none are production assets.

## Tests and observed evidence
- Baseline local suite 40/40 PASS; modified five-file regression suite **49/49 PASS**, compile and manifest checks PASS.
- Prior GitHub FLUX CI run 45065574263 on baseline SHA FAILED (3 failures due to missing requests). This change installs requests and adds Hanbok fail-closed tests; new SHA needs a fresh GitHub CI run.
- Negative tests: arbitrary reviewer references, tampered review proof hashes, per-animal review SHA mismatch, and missing review proof all rejected.
- Hash-bound local proof verifies evidence presence and file integrity, **not cryptographic reviewer identity**. Independent review remains a release requirement.
- Isolated real STYLE_06: 12 individually inspected portraits PASS after regeneration of only original HOLD rat/monkey using local FLUX. Original sources preserved and never auto-approved. Other six styles / **72 portraits not independently QAed**.
- Six real STYLE_06 1080×1920 cards technical/layout PASS. Summary has two rows of six larger portraits. Complete 80.831s H264/AAC local Supertonic TTS video, ~79s phone-size sample shows all portraits without zoom clipping.
- Male and female original Hanbok PNGTuber assets separately composed into 5s genuine local TTS clips, displayed in independent left rail without text/subject overlay. **Full-length Shorts avatar remains to be verified**.
- Unpublished-day positive canary: two full card+TTS+video runs both technical PASS, input image/proof/card SHA unchanged, observed SNS calls 0 and paid provider calls 0. **Exact bitwise replay HOLD:** output video/audio hashes and certain decoded frame hashes differ between runs.
- Old 21 previews remain unapproved evidence: underlay heuristic 6 PASS / 15 HOLD; semantic publication approval 0. Seven 2s still-frame videos are not substitutes for complete narrated videos.
- Synthetic offline negative checks covered receipt protection, concurrent generation and SHA tamper.

## Release blockers
1. New-SHA CI PASS and formal independent PR code review.
2. Accountable reviewer proof authenticity; independent real image QA of all 84 assets.
3. Full-length Shorts Hanbok/voice/scene validation and smartphone readability.
4. Investigate differing TTS/video hashes in positive canary reruns.
5. Render/review all six remaining styles and regenerate/review 21 previews, complete cards/videos.
6. Keep Draft; forbid merge/deploy/SNS publication and paid image fallbacks.

## 2026-11-23 offline deterministic TTS continuation
- Supertonic-3 stochastic sampling confirmed in core.py: NumPy random diffusion latent. Without a fixed seed two complete prior canary MP4 and decoded audio SHA differed, not because inputs were corrupted.
- New opt-in SUPERTONIC_DETERMINISTIC_QA=1 derives a stable SHA-256 seed from model, voice, speed, and text; holds a lock and restores original NumPy RNG state. Legacy default is unchanged.
- Four new unit tests and 53 full local regression checks PASS.
- Two separate completed full 80.831-second 1080x1920 H264/AAC TTS MP4 videos for unpublished 2026-11-28, with opt-in deterministic mode, were byte-for-byte identical: SHA-256 96a5ac8e4b6e6a59f243b028bf2cecd2f39404cab63dd5b6eb172f81e8e1cc8c.
- Inputs and audit proof hashes unchanged; observed external social calls 0, paid image API calls 0.
- This resolves bitwise-replay HOLD only for opt-in offline QA; default production audio remains stochastic.
- STYLE_07 initial local FLUX-only source generation is independent of this code commit, remains PENDING_QA, and never authorizes publishing.
