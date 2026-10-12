import instagram_insights as ii


def test_primary_keeps_existing_output_path(monkeypatch, tmp_path):
    monkeypatch.setattr(ii, "BASE", tmp_path)
    monkeypatch.delenv("INSTAGRAM_ACCOUNT_KEY", raising=False)
    assert ii.output_path().name == "instagram_insights.json"


def test_legacy_uses_account_scoped_output_path(monkeypatch, tmp_path):
    monkeypatch.setattr(ii, "BASE", tmp_path)
    monkeypatch.setenv("INSTAGRAM_ACCOUNT_KEY", "sajufortune.kr")
    assert ii.output_path().name == "instagram_insights_sajufortune_kr.json"


def test_merge_history_appends_samples_and_caps_per_media():
    existing = {"account_key": "gsdo10042026", "media": {"m1": {"timestamp": "2026-10-14T00:00:00+0000", "samples": []}}}
    for i in range(20):
        payload = {"collected_at": f"2026-10-{14 + (i // 10):02d}T{i%10:02d}:00:00", "media": [{"id": "m1", "timestamp": "2026-10-14T00:00:00+0000", "metrics": {"views": i}}]}
        existing = ii.merge_history(existing, payload, "gsdo10042026", max_samples=16)
    samples = existing["media"]["m1"]["samples"]
    assert len(samples) == 16
    assert samples[-1]["metrics"]["views"] == 19
