# Korean zodiac FLUX 7-style rollout and safety gates (2026-11-22)

## Scope
- Seven original art families chosen by Asia/Seoul calendar date: Monday STYLE_01 to Sunday STYLE_07.
- Twelve distinct Korean zodiac mascot specifications. East Asian dragon without wings; friendly rat and snake.
- Six-image background generation uses existing HomeCode `generate_with_fallback` (local FLUX.2 Klein → configured, verified no-extra-charge included provider). Paid attempts are forced to zero.
- Existing `zodiac_cardnews_tpl.py` remains the renderer. Strict geometry tracking is enabled **only** for new manifests containing `style_id`. Old verified FLUX bundles and legacy background sets retain existing layout paths.
- Actual PIL text bounding boxes are compared against **authored composition protection boxes**, not an ML-detected face mask. This distinction matters.
- Strict FLUX promotion requires six verified image hashes and six PASS layout reports. Incomplete/corrupted bundles HOLD; existing social receipts prohibit replacement.
- Reels and Threads video publication reuse existing scheduling, tokens, URL validation and duplicate receipts. FLUX days additionally check local 9:16 MP4 codec/duration and three sampled frames before promotion/publication.
- Missing approved fallback templates trigger HOLD rather than solid-color cards.

## Local read-only validation
```bash
python -m pytest -q test_flux_first_card_assets.py test_card_flux_promotion.py test_zodiac_seven_style_layout.py
python scripts/zodiac_preview_suite.py --sources /tmp/zodiac-seven-styles-real --output /tmp/zodiac-seven-styles-review --videos
```
The preview command requires one authentic local-FLUX source per style **and** a SHA-256 provenance receipt. If any is missing, the result is HOLD; no placeholder image may be labeled FLUX. After all seven images exist, it produces 21 individual 9:16 JPEG sample previews, seven short MP4 examples and one contact sheet. The resulting `preview_report.json` distinguishes these offline samples from actual social publication.

## Release requirements
Before merging or enabling a scheduled rollout, independently verify:
1. All seven **actual** local-FLUX styles have been generated and are visually distinct.
2. The cover actually depicts all twelve animals without crop/duplicates. Review dragon, rat, snake and face locations.
3. Every preview passes text geometry and mobile safe-area checks. Composition contracts alone do not prove model compliance.
4. 21 previews and seven MP4 samples exist and pass quality checks.
5. Existing prepublisher conflicts with concurrent commits do not lose image assets. No force pushes.
6. No paid API calls or unexpected provider switches, and publishing receipts preserved.
7. CI is green and a pilot unpublished date renders without incident. Check actual next schedule's successful posting receipt afterwards.

## Operations and rollback
- Work on feature branch, not the existing dirty local `main` in `C:\\cardnews\\_push`.
- Never change account tokens, schedules, existing published files or billing.
- If release checks fail: **do not merge**; keep workflow untouched and report a HOLD reason.
- If unexpected problems appear after release: disable/revert only the new small changes; do not re-run past dates.

## New strict independent species audit gate
Styled FLUX publication requires `assets/zodiac_semantic_qa/YYYY-MM-DD.json`,
with six image-specific exact SHA-256 entries and exact distinct species list.
A real independent reviewer or a verified local vision model must record
`cropped_faces=false`, `malformed_anatomy=false`, `text_artifacts=false`,
`duplicate_species_count=0`, and `status=PASS` for every image.
Synthetic test fixtures bypass this audit only inside pytest using monkeypatch;
**the actual publishing pipeline has no such bypass.**
The new gate currently produces HOLD for real output if no independent audit
is available, because prompt compliance is not proof of twelve correct signs.

## Verified one-animal atlas (structural fix for duplicated species)
The first actual FLUX cover samples contain duplicated/misidentified animals.
Do not approve those covers. New optional, non-destructive atlas route:
scripts/zodiac_mascot_atlas.py

1. For each weekday style, run stage_atlas_sources(day,root,max_new=1..12).
   Only one independent single-species portrait is generated at a time from
   the same local FLUX broker with explicit square dimensions and paid OFF.
   Crash/resume uses SHA-256 and a PENDING_QA manifest.
2. Twelve unique files rat.jpg, ox.jpg, ... pig.jpg must be independently
   visually audited. No generated file is self-approved. Record one identified
   species per file, no cropped face, no malformed anatomy, no text artifacts,
   verification method/reference and exact SHA in
   assets/zodiac_mascot_atlas/STYLE_XX/manifest.json.
3. With a verified atlas manifest present, existing FLUX preparation prefers
   deterministic PIL composition over multi-animal text-to-image generation.
   Six 9:16 backgrounds are atomically produced and identified by atlas SHA.
4. Existing card ensure/verify accepts audited atlas provenance as semantic
   evidence and still checks all six rendered text layouts.
5. Without a verified atlas, direct free FLUX images remain under a strict
   independent per-day semantic QA gate; otherwise publication HOLD.

The atlas route has synthetic unit/integration tests only; actual 84 portraits
(12 species x 7 styles) are NOT yet generated and independently approved.
