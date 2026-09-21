from pathlib import Path

import threads_publish_queue as q
import threads_publisher_adapter as a


def isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(q, "STATE", tmp_path / "queue.jsonl")
    monkeypatch.setattr(q, "AUDIT", tmp_path / "audit.jsonl")
    monkeypatch.setattr(a.zc, "__file__", str(tmp_path / "zodiac_cardnews.py"))
    monkeypatch.setattr(a.zc, "RAW_BASE", "https://example.invalid/main")
    monkeypatch.setattr(a.zc, "date_full", lambda d: d)


def make_cards(tmp_path):
    d = tmp_path / "cards" / "2026-09-22"
    d.mkdir(parents=True)
    (d / "card_01.png").write_bytes(b"x")
    (d / "card_02.png").write_bytes(b"x")


def test_adapter_builds_payload_without_network(tmp_path, monkeypatch):
    isolate(tmp_path, monkeypatch)
    make_cards(tmp_path)
    calls = []
    monkeypatch.setattr(a.zc, "publish_carousel",
                        lambda *args: calls.append(args) or "should-not-run")
    payload = a.build_zodiac_payload({"kind":"zodiac_carousel","target":"2026-09-22"})
    assert len(payload["urls"]) == 2
    assert calls == []


def test_worker_adapter_e2e_dry_run_has_zero_publish_calls(tmp_path, monkeypatch):
    isolate(tmp_path, monkeypatch)
    make_cards(tmp_path)
    calls = []
    monkeypatch.setattr(a.zc, "publish_carousel",
                        lambda *args: calls.append(args) or "id")
    q.enqueue("zodiac:2026-09-22", "2026-09-21T00:00:00+00:00",
              "zodiac_carousel", "2026-09-22")
    result = q.run_worker_once(a.publish_job, "2026-09-21T01:00:00+00:00")
    assert result["mode"] == "DRY_RUN"
    assert result["external_calls"] == 0
    assert calls == []


def test_worker_adapter_mock_live_calls_existing_publisher_once(tmp_path, monkeypatch):
    isolate(tmp_path, monkeypatch)
    make_cards(tmp_path)
    monkeypatch.setenv("THREADS_QUEUE_LIVE", "1")
    calls = []
    monkeypatch.setattr(a.zc, "publish_carousel",
                        lambda urls, caption, target: calls.append((urls, caption, target)) or "mock-id")
    q.enqueue("zodiac:2026-09-22", "2026-09-21T00:00:00+00:00",
              "zodiac_carousel", "2026-09-22")
    result = q.run_worker_once(a.publish_job, "2026-09-21T01:00:00+00:00", live=True)
    assert result["threads_id"] == "mock-id"
    assert len(calls) == 1
    assert q.load()[0]["status"] == "PUBLISHED"


def test_adapter_refuses_when_receipt_exists(tmp_path, monkeypatch):
    isolate(tmp_path, monkeypatch)
    make_cards(tmp_path)
    marker = tmp_path / "cards" / "2026-09-22" / "threads_pub_carousel.json"
    marker.write_text('{"post_id":"already"}', encoding="utf-8")
    try:
        a.build_zodiac_payload({"kind":"zodiac_carousel","target":"2026-09-22"})
    except RuntimeError as e:
        assert "receipt already exists" in str(e)
    else:
        raise AssertionError("existing receipt was not blocked")
