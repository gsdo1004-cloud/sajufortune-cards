import threads_publish_queue as q
import threads_queue_watchdog as w


def isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(q, "STATE", tmp_path / "queue.jsonl")
    monkeypatch.setattr(q, "AUDIT", tmp_path / "audit.jsonl")


def test_watchdog_default_is_safe_dry_run(tmp_path, monkeypatch):
    isolate(tmp_path, monkeypatch)
    q.enqueue("a", "2000-01-01T00:00:00+00:00", "text", "a")
    calls = []
    monkeypatch.setattr(w.adapter, "publish_job", lambda item: calls.append(item) or "id")
    result = w.run(live=False, cards_root=tmp_path / "cards")
    assert result["worker"]["mode"] == "DRY_RUN"
    assert result["worker"]["external_calls"] == 0
    assert calls == []


def test_watchdog_reconciles_existing_receipt_before_worker(tmp_path, monkeypatch):
    isolate(tmp_path, monkeypatch)
    q.enqueue("zodiac:2026-09-22", "2000-01-01T00:00:00+00:00",
              "zodiac_carousel", "2026-09-22")
    marker = tmp_path / "cards" / "2026-09-22" / "threads_pub_carousel.json"
    marker.parent.mkdir(parents=True)
    marker.write_text('{"post_id":"existing-id"}', encoding="utf-8")
    calls = []
    monkeypatch.setattr(w.adapter, "publish_job", lambda item: calls.append(item) or "new-id")
    result = w.run(live=False, cards_root=tmp_path / "cards")
    assert result["reconciled"] == ["zodiac:2026-09-22"]
    assert result["worker"]["processed"] == 0
    assert calls == []
    assert q.load()[0]["threads_id"] == "existing-id"


def test_live_flag_still_needs_environment_gate(tmp_path, monkeypatch):
    isolate(tmp_path, monkeypatch)
    monkeypatch.delenv("THREADS_QUEUE_LIVE", raising=False)
    q.enqueue("a", "2000-01-01T00:00:00+00:00", "text", "a")
    result = w.run(live=True, cards_root=tmp_path / "cards")
    assert result["worker"]["reason"] == "live_gate_disabled"
    assert q.load()[0]["status"] == "PENDING"
