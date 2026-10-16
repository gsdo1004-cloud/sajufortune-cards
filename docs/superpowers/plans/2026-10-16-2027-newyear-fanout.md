# 2027 New-Year Fortune Fanout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a safe, independent daily Threads + YouTube Shorts fanout for the 60 approved 2027 Naver fortune posts without altering existing today-fortune publication behavior.

**Architecture:** Prebuild a deterministic 60-item `newyear_2027` bundle from approved Naver packages, then run a small local dispatcher that gates on the confirmed Naver receipt and triggers a dispatch-only GitHub Actions workflow. The workflow uses platform-specific two-phase receipts and isolated publish steps; the existing Threads account lock and YouTube channel-locking credentials are reused without invoking the existing daily pipeline.

**Tech Stack:** Python 3, pytest, Pillow, ffmpeg/ffprobe, existing `typecast_tts` (Supertonic/Edge), GitHub Actions, Threads Graph API, YouTube Data API, GitHub CLI, Windows Task Scheduler.

**Spec:** `docs/superpowers/specs/2027-newyear-fanout.md`

## Global Constraints
- Existing Naver/today-fortune files, schedules, locks, receipts, and workflow concurrency groups must remain unchanged.
- New lane namespace is `newyear_2027`.
- Naver `PUBLISHED`+`success`+`rss_seen` receipt gate is mandatory before remote fanout.
- Two-phase `PUBLISHING`→`PUBLISHED` platform receipts; unresolved `PUBLISHING` never auto-reposts.
- Threads and YouTube failures are isolated.
- Daily execution has no LLM dependency.
- Threads <=500 chars; Shorts 25–40 seconds; six-format rotation.
- No new paid dependency.
- Dispatch window ends at 14:00 KST.

## Review Focus
- Crash after remote publish but before final receipt: next run must HOLD rather than duplicate.
- A source article changes after bundle generation: source hash mismatch must HOLD rather than silently publish stale copy.
- Duplicate/missing KST publish dates: selector must reject ambiguity and not pick the wrong item.
- One platform fails while the other succeeds: successful platform must remain idempotently complete and existing daily workflows unaffected.
- Windows lock already exists or belongs to another process: a failed acquisition must never delete the foreign lock.

---

### Task 1: Source Gate, Content Bundle, and Idempotency Core

**Files:**
- Create: `newyear_2027_runner.py`
- Create: `test_newyear_2027_runner.py`
- Create: `newyear_2027/README.md`

**Interfaces:**
- Produces: `load_manifest(path)`, `select_manifest_item(manifest, date_iso)`, `validate_naver_receipt(path)`, `source_gate(item, source_root)`, `OwnedFileLock`, `prepare_intent(receipt_path, ...)`, `finalize_receipt(...)`, `build_entry(post_dir)`.
- Later tasks consume the stable manifest item fields and receipt helpers.

- [ ] Write failing tests for Naver receipt acceptance/rejection, duplicate dates, source hash mismatch, foreign-lock preservation, fixed publish keys, unresolved `PUBLISHING`, Threads copy bounds/CTA, Shorts source grounding and six-format rotation.
- [ ] Run `python3 -m pytest -q test_newyear_2027_runner.py` and verify RED because `newyear_2027_runner` does not exist.
- [ ] Implement the minimal pure/data-layer code in `newyear_2027_runner.py`; do not add remote side effects yet.
- [ ] Run `python3 -m pytest -q test_newyear_2027_runner.py` and verify GREEN.
- [ ] Commit Task 1.

### Task 2: Isolated Shorts Renderer and Platform Adapters

**Files:**
- Modify: `newyear_2027_runner.py`
- Modify: `test_newyear_2027_runner.py`

**Interfaces:**
- Consumes: manifest entries and receipt helpers from Task 1.
- Produces: `render_short(item, bundle_root, out_path)`, `publish_threads_text(...)`, `publish_youtube(...)`, `publish_youtube_private_canary(...)`.

- [ ] Add failing tests that mock Threads/YouTube network calls, verify account/channel guard delegation, verify `PUBLISHING` is required before remote calls, verify one platform exception does not alter the other receipt, and verify private-canary request omits `publishAt`.
- [ ] Run targeted tests and confirm RED.
- [ ] Implement isolated adapters using existing `_threads_uid`/`_post` and `youtube_upload` credentials/channel identity; normal YouTube uses existing uploader, canary performs true private upload with no `publishAt`.
- [ ] Implement a three-scene 1080x1920 renderer using the bundled hero asset, existing TTS, Pillow, ffmpeg; enforce ffprobe duration 25–40s and no upload if out of range.
- [ ] Run targeted tests GREEN and render one offline sample; verify ffprobe duration.
- [ ] Commit Task 2.

### Task 3: Dispatch-Only Workflow and Local Gate Dispatcher

**Files:**
- Create: `.github/workflows/newyear-2027-fanout.yml`
- Modify: `newyear_2027_runner.py`
- Modify: `test_newyear_2027_runner.py`

**Interfaces:**
- Consumes: Task 1 gate/idempotency + Task 2 renderer/adapters.
- Produces: `dispatch` CLI command and a workflow that is `workflow_dispatch` only with unique concurrency.

- [ ] Add failing static/behavior tests: workflow has no `schedule`, uses unique `newyear-2027` concurrency, platform steps are isolated, and dry-run dispatch never invokes `gh`; live dispatch includes exact date and `send=true` only inside KST window after source gate.
- [ ] Run targeted tests and confirm RED.
- [ ] Implement workflow inputs for date, send, and canary mode; add two-phase receipt commits around each platform side effect.
- [ ] Implement local `dispatch` command with Naver gate, source hash validation, owner-safe lock, 14:00 cutoff, status JSONL, and `gh workflow run` invocation.
- [ ] Run targeted tests GREEN.
- [ ] Commit Task 3.

### Task 4: Build 60-Item Bundle, Review, Canary, and Safe Enablement

**Files:**
- Create: `newyear_2027/content.json`
- Create: `newyear_2027/assets/*`
- Create outside repo only after canary: `D:\automation_control\runtimes\newyear_2027\*` and a new independent Task Scheduler entry.

**Interfaces:**
- Consumes all prior task interfaces.
- Produces the production bundle and independent daily trigger.

- [ ] Generate the 60-item bundle from `D:\blog_auto_work\output\2027_naver_60`; assert 60 unique dates/content IDs, source hashes, assets, Threads bounds, Shorts basis, and six-format distribution.
- [ ] Run targeted tests plus full existing suite; record the known baseline-only `_publish_runtime` path issue separately if still present.
- [ ] Run a fresh GPT-6 Astra whole-branch review using the diff and test evidence; fix any Critical/Important finding with RED→GREEN tests.
- [ ] Commit and push the verified branch; integrate only the new files/workflow without touching the dirty operating checkout.
- [ ] Run GitHub workflow dry-run, then one true-private YouTube canary, then one Threads canary; verify remote IDs/account/content and re-run no-op behavior.
- [ ] Copy the verified dispatcher to `D:\automation_control\runtimes\newyear_2027` and create only a new `Hanbak_2027_SocialFanout` daily 12:20 KST task. Do not modify existing tasks.
- [ ] Re-query `HanbakBlog_2027_Series`, `Zodiac_DailyPipeline`, and `HanbakBlog_DailyDual_Zodiac`; verify actions/times remain unchanged.
