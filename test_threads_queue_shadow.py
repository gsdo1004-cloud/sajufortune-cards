import json
import threads_publish_queue as q
import threads_queue_shadow as s

def setup(monkeypatch, tmp_path, status="PENDING"):
    monkeypatch.setattr(q, "STATE", tmp_path / "queue.jsonl")
    monkeypatch.setattr(q, "AUDIT", tmp_path / "audit.jsonl")
    q.save([{"key":"z:2026-09-22","target":"2026-09-22","kind":"zodiac_carousel",
             "status":status,"scheduled_at":"2026-09-22T12:10:00+00:00"}])

def test_waiting_read_only(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path)
    before=q.STATE.read_text(encoding="utf-8")
    out=s.observe(tmp_path/"cards")
    assert out["mode"]=="SHADOW_READ_ONLY"
    assert out["external_calls"]==0 and out["queue_mutations"]==0
    assert out["by_shadow_state"]=={"WAITING_RECEIPT":1}
    assert q.STATE.read_text(encoding="utf-8")==before

def test_receipt_match_read_only(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path, "RETRY")
    marker=tmp_path/"cards"/"2026-09-22"/"threads_pub_carousel.json"
    marker.parent.mkdir(parents=True)
    marker.write_text(json.dumps({"post_id":"threads-123"}),encoding="utf-8")
    before=q.STATE.read_text(encoding="utf-8")
    out=s.observe(tmp_path/"cards")
    assert out["ok"] is True and out["by_shadow_state"]=={"RECEIPT_MATCH":1}
    assert out["observations"][0]["threads_id"]=="threads-123"
    assert q.STATE.read_text(encoding="utf-8")==before

def test_invalid_receipt(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path, "RUNNING")
    marker=tmp_path/"cards"/"2026-09-22"/"threads_pub_carousel.json"
    marker.parent.mkdir(parents=True)
    marker.write_text("{}",encoding="utf-8")
    out=s.observe(tmp_path/"cards")
    assert out["ok"] is False and out["by_shadow_state"]=={"INVALID_RECEIPT":1}
