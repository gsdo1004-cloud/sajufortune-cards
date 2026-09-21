import threads_publish_queue as q


def isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(q, "STATE", tmp_path / "queue.jsonl")
    monkeypatch.setattr(q, "AUDIT", tmp_path / "audit.jsonl")


def test_enqueue_is_persistent_and_dedupes(tmp_path, monkeypatch):
    isolate(tmp_path, monkeypatch)
    first = q.enqueue("zodiac:2026-09-22", "2026-09-21T12:00:00+00:00",
                      "zodiac_carousel", "2026-09-22")
    second = q.enqueue("zodiac:2026-09-22", "2026-09-21T12:00:00+00:00",
                       "zodiac_carousel", "2026-09-22")
    assert first["ok"] is True
    assert second == {"ok": False, "reason": "duplicate_active_key",
                      "key": "zodiac:2026-09-22"}
    assert len(q.load()) == 1


def test_dry_run_has_no_queue_mutation_or_external_call(tmp_path, monkeypatch):
    isolate(tmp_path, monkeypatch)
    q.enqueue("zodiac:2026-09-22", "2026-09-21T00:00:00+00:00",
              "zodiac_carousel", "2026-09-22")
    before = q.STATE.read_bytes()
    result = q.dry_run("2026-09-22T00:00:00+00:00")
    after = q.STATE.read_bytes()
    assert result["would_publish"] == ["zodiac:2026-09-22"]
    assert result["external_calls"] == 0
    assert result["queue_mutations"] == 0
    assert before == after


def test_future_item_is_not_due(tmp_path, monkeypatch):
    isolate(tmp_path, monkeypatch)
    q.enqueue("future", "2099-01-01T00:00:00+00:00", "text", "future")


def test_claim_and_complete(tmp_path, monkeypatch):
    isolate(tmp_path, monkeypatch)
    q.enqueue("a", "2026-09-21T00:00:00+00:00", "text", "a")
    claimed = q.claim("a", "2026-09-21T01:00:00+00:00", 300)
    assert claimed["item"]["status"] == "RUNNING"
    assert q.complete("a", "threads-123", "2026-09-21T01:01:00+00:00")["ok"]
    row = q.load()[0]
    assert row["status"] == "PUBLISHED"
    assert row["threads_id"] == "threads-123"


def test_expired_lease_recovers_after_crash(tmp_path, monkeypatch):
    isolate(tmp_path, monkeypatch)
    q.enqueue("a", "2026-09-21T00:00:00+00:00", "text", "a")
    q.claim("a", "2026-09-21T01:00:00+00:00", 60)
    result = q.recover_expired("2026-09-21T01:02:00+00:00")
    assert result["recovered"] == ["a"]
    assert q.load()[0]["status"] == "RETRY"


def test_failure_retries_then_terminal_failure(tmp_path, monkeypatch):
    isolate(tmp_path, monkeypatch)
    q.enqueue("a", "2026-09-21T00:00:00+00:00", "text", "a")
    for attempt in range(3):
        assert q.claim("a", f"2026-09-21T0{attempt+1}:00:00+00:00")["ok"]
        result = q.fail("a", "simulated", f"2026-09-21T0{attempt+1}:01:00+00:00")
    assert result["item"]["status"] == "FAILED"
    assert result["item"]["retry_count"] == 3


def test_running_item_cannot_be_double_claimed(tmp_path, monkeypatch):
    isolate(tmp_path, monkeypatch)
    q.enqueue("a", "2026-09-21T00:00:00+00:00", "text", "a")
    assert q.claim("a", "2026-09-21T01:00:00+00:00")["ok"]
    assert q.claim("a", "2026-09-21T01:00:01+00:00")["reason"] == "not_claimable"


def test_receipt_reconcile_marks_published(tmp_path, monkeypatch):
    isolate(tmp_path, monkeypatch)
    q.enqueue("zodiac:2026-09-22", "2026-09-21T00:00:00+00:00",
              "zodiac_carousel", "2026-09-22")
    marker = tmp_path / "cards" / "2026-09-22" / "threads_pub_carousel.json"
    marker.parent.mkdir(parents=True)
    marker.write_text('{"post_id":"real-threads-id"}', encoding="utf-8")
    result = q.reconcile_zodiac_receipts(tmp_path / "cards", "2026-09-21T02:00:00+00:00")
    assert result["published"] == ["zodiac:2026-09-22"]
    row = q.load()[0]
    assert row["status"] == "PUBLISHED"
    assert row["threads_id"] == "real-threads-id"


def test_invalid_receipt_does_not_mutate_queue(tmp_path, monkeypatch):
    isolate(tmp_path, monkeypatch)
    q.enqueue("zodiac:2026-09-22", "2026-09-21T00:00:00+00:00",
              "zodiac_carousel", "2026-09-22")
    marker = tmp_path / "cards" / "2026-09-22" / "threads_pub_carousel.json"
    marker.parent.mkdir(parents=True)
    marker.write_text('{"post_id":""}', encoding="utf-8")
    result = q.reconcile_zodiac_receipts(tmp_path / "cards")
    assert result["invalid_receipts"] == ["zodiac:2026-09-22"]
    assert q.load()[0]["status"] == "PENDING"


def test_receipt_reconcile_is_idempotent(tmp_path, monkeypatch):
    isolate(tmp_path, monkeypatch)
    q.enqueue("zodiac:2026-09-22", "2026-09-21T00:00:00+00:00",
              "zodiac_carousel", "2026-09-22")
    marker = tmp_path / "cards" / "2026-09-22" / "threads_pub_carousel.json"
    marker.parent.mkdir(parents=True)
    marker.write_text('{"post_id":"id-1"}', encoding="utf-8")
    first = q.reconcile_zodiac_receipts(tmp_path / "cards")
    second = q.reconcile_zodiac_receipts(tmp_path / "cards")
    assert first["published"] == ["zodiac:2026-09-22"]
    assert second["published"] == []


def test_worker_default_is_dry_run_and_never_calls_publisher(tmp_path, monkeypatch):
    isolate(tmp_path, monkeypatch)
    q.enqueue("a", "2026-09-21T00:00:00+00:00", "text", "a")
    calls = []
    result = q.run_worker_once(lambda item: calls.append(item) or "x",
                               "2026-09-21T01:00:00+00:00")
    assert result["mode"] == "DRY_RUN"
    assert result["external_calls"] == 0
    assert calls == []
    assert q.load()[0]["status"] == "PENDING"


def test_live_worker_requires_environment_gate(tmp_path, monkeypatch):
    isolate(tmp_path, monkeypatch)
    monkeypatch.delenv("THREADS_QUEUE_LIVE", raising=False)
    q.enqueue("a", "2026-09-21T00:00:00+00:00", "text", "a")
    result = q.run_worker_once(lambda item: "id", "2026-09-21T01:00:00+00:00", live=True)
    assert result["reason"] == "live_gate_disabled"
    assert q.load()[0]["status"] == "PENDING"


def test_live_worker_success_with_injected_publisher(tmp_path, monkeypatch):
    isolate(tmp_path, monkeypatch)
    monkeypatch.setenv("THREADS_QUEUE_LIVE", "1")
    q.enqueue("a", "2026-09-21T00:00:00+00:00", "text", "a")
    result = q.run_worker_once(lambda item: "threads-xyz",
                               "2026-09-21T01:00:00+00:00", live=True)
    assert result["threads_id"] == "threads-xyz"
    assert q.load()[0]["status"] == "PUBLISHED"


def test_live_worker_failure_moves_to_retry(tmp_path, monkeypatch):
    isolate(tmp_path, monkeypatch)
    monkeypatch.setenv("THREADS_QUEUE_LIVE", "1")
    q.enqueue("a", "2026-09-21T00:00:00+00:00", "text", "a")
    def boom(item):
        raise RuntimeError("simulated publisher failure")
    result = q.run_worker_once(boom, "2026-09-21T01:00:00+00:00", live=True)
    assert result["status"] == "RETRY"
    assert q.load()[0]["retry_count"] == 1
